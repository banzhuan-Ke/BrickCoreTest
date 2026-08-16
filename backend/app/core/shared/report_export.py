"""
测试报告导出功能
支持导出 HTML 格式的测试报告，包含展开/收起功能
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import copy
import json
import os
import re
import base64
import io
import requests
from PIL import Image
from app.core.platform.config import MINIO_CONFIG
from app.modules.app.app_execution_env import driver_mode_display, trigger_source_label


@dataclass
class ImageExportOptions:
    """图片导出选项"""
    include_images: bool = True      # 是否包含图片
    image_mode: str = "all"          # all-全部, failed-仅失败, none-不包含
    include_video: bool = True       # 是否包含视频


# 邮件 HTML 附件软上限（原文字节；SMTP 再 base64 后约 ×1.37）。可用环境变量覆盖。
EMAIL_HTML_SOFT_LIMIT_BYTES = max(
    1 * 1024 * 1024,
    int(os.getenv("EMAIL_REPORT_HTML_MAX_BYTES", str(8 * 1024 * 1024))),
)


def build_email_html_report(
    record_data: Dict[str, Any],
    record_type: str = "task",
    suite_records: Optional[List[Dict]] = None,
    case_records: Optional[List[Dict]] = None,
) -> Tuple[str, str]:
    """生成邮件附件 HTML：优先内嵌失败用例截图；超限则降级为无图。

    自动邮件不宜用 image_mode=all（大计划可达数十～上百 MB，易被 SMTP 拒收）。
    手动导出报告仍可按需选 all。

    Returns:
        (html, image_mode_used) 其中 image_mode_used 为 failed | none
    """
    last_html = ""
    last_mode = "none"
    for mode in ("failed", "none"):
        opts = ImageExportOptions(
            include_images=(mode != "none"),
            image_mode=mode,
            include_video=False,
        )
        # generate_html_report 会改写 case 内截图字段，每次用深拷贝
        html = generate_html_report(
            record_data,
            record_type,
            copy.deepcopy(suite_records or []),
            copy.deepcopy(case_records or []),
            opts,
        )
        last_html, last_mode = html, mode
        size = len(html.encode("utf-8"))
        if size <= EMAIL_HTML_SOFT_LIMIT_BYTES:
            return html, mode
        print(
            f"[EmailReport] HTML {size} bytes with image_mode={mode} exceeds "
            f"{EMAIL_HTML_SOFT_LIMIT_BYTES}, degrading…"
        )
    return last_html, last_mode


def email_report_attachment_note(image_mode_used: str) -> str:
    """邮件正文里对附件截图策略的说明。"""
    if image_mode_used == "failed":
        return "详细报告（失败步骤含内嵌截图）请查看附件。"
    return "详细报告请查看附件（截图因体积过大未内嵌，请到平台查看）。"


def _should_include_image(img_options: ImageExportOptions, case_status: str) -> bool:
    """根据选项判断是否包含该图片"""
    if not img_options.include_images or img_options.image_mode == "none":
        return False
    if img_options.image_mode == "failed":
        return case_status in ["fail", "error", "failed"]
    return True


def _storage_bucket_marker() -> str:
    bucket = MINIO_CONFIG.get("bucket_name") or ""
    return f"/{bucket}/" if bucket else ""


def _is_storage_media_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    marker = _storage_bucket_marker()
    if marker and marker in url:
        return True
    lowered = url.lower()
    return ":9200/" in url or "minio" in lowered or "192.168." in url or "aliyuncs.com" in lowered


def _storage_object_key(url: str) -> str | None:
    if not url or not isinstance(url, str):
        return None
    import urllib.parse

    marker = _storage_bucket_marker()
    if marker and marker in url:
        return urllib.parse.unquote(url.split(marker, 1)[-1].split("?")[0])
    return urllib.parse.unquote(url.split("/")[-1].split("?")[0])


def _sanitize_env_for_export(env: Any) -> Any:
    if not isinstance(env, dict):
        return env
    sensitive = {"password", "secret", "token", "apk_base64", "base64", "general_password"}
    out: Dict[str, Any] = {}
    for key, value in env.items():
        key_lower = str(key).lower()
        if key_lower in sensitive or "password" in key_lower or key_lower.endswith("_token"):
            out[key] = "******" if value else value
        elif isinstance(value, str) and len(value) > 200:
            out[key] = f"{value[:120]}…（已省略，共 {len(value)} 字符）"
        elif isinstance(value, dict):
            out[key] = _sanitize_env_for_export(value)
        else:
            out[key] = value
    return out




def generate_html_report(
    record_data: Dict[str, Any], 
    record_type: str = "task", 
    suite_records: List[Dict] = None, 
    case_records: List[Dict] = None,
    img_options: Optional[ImageExportOptions] = None
) -> str:
    """
    生成 HTML 格式的测试报告
    
    Args:
        img_options: 图片导出选项，默认全部包含
    """
    # 默认选项
    if img_options is None:
        img_options = ImageExportOptions()
    
    # 根据选项处理图片和视频：能内嵌则转 base64；否则清空外链，避免邮件/离线 HTML 裂图
    image_cache = {}
    if case_records:
        if img_options.include_images or img_options.include_video:
            _collect_and_download_images(case_records, image_cache, img_options)
        case_records = _replace_images_with_base64(case_records, image_cache, img_options)
    
    # 计算百分比（使用 case_count 而不是 all）
    all_count = record_data.get('case_count', 0) or record_data.get('all', 0)
    if all_count > 0:
        success_percent = round(record_data.get('success', 0) / all_count * 100, 2)
        fail_percent = round(record_data.get('fail', 0) / all_count * 100, 2)
        error_percent = round(record_data.get('error', 0) / all_count * 100, 2)
        skip_percent = round(record_data.get('skip', 0) / all_count * 100, 2)
    else:
        success_percent = fail_percent = error_percent = skip_percent = 0
    
    # 状态样式
    status = record_data.get('status', '未知')
    if status == '执行完成':
        status_class = 'status-success'
    elif status == '执行中':
        status_class = 'status-running'
    else:
        status_class = 'status-fail'
    
    # 获取环境信息
    env = record_data.get('env', {})
    if isinstance(env, str):
        try:
            env = json.loads(env)
        except:
            env = {}
    
    is_app_engine = isinstance(env, dict) and env.get("engine_type") == "app"
    browser_type = env.get('browser_type', 'chromium') if isinstance(env, dict) else 'chromium'
    browser_map = {'chromium': '谷歌浏览器', 'firefox': '火狐浏览器', 'webkit': 'Safari'}
    
    # 生成环境数据部分
    env_section = generate_env_section(env)
    
    # 更新套件记录中的all字段（兼容前端显示）
    if suite_records:
        for suite in suite_records:
            if 'all' not in suite or suite['all'] == 0:
                suite['all'] = suite.get('case_count', 0)
    
    # 生成日志部分
    logs_section = generate_logs_section(record_data, suite_records, case_records, img_options)
    
    # 构建 HTML（不使用 f-string 嵌套，避免 JavaScript 大括号冲突）
    title = record_data.get('task_name') or record_data.get('suite_name') or '测试报告'
    start_time = format_time(record_data.get('start_time'))
    duration = round(record_data.get('duration', 0), 2)
    username = record_data.get('username', '未知')
    if is_app_engine:
        runtime_label = "设备 UDID"
        runtime_value = (env.get("device_udid") or record_data.get("device_id") or "未知") if isinstance(env, dict) else "未知"
        env_label = "执行引擎"
        env_value = "App 自动化"
    else:
        runtime_label = "浏览器"
        runtime_value = browser_map.get(browser_type, browser_type)
        env_label = "环境地址"
        env_value = env.get('host', '未知') if isinstance(env, dict) else '未知'
    pass_rate = record_data.get('pass_rate', 0)
    success = record_data.get('success', 0)
    fail = record_data.get('fail', 0)
    error = record_data.get('error', 0)
    skip = record_data.get('skip', 0)
    no_run = record_data.get('no_run', 0)
    generate_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html_parts = []
    
    # HTML 头部
    html_parts.append(f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>测试报告 - {title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #f5f7fa; color: #333; line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(135deg, #1a73e8 0%, #34a853 100%);
            color: white; padding: 30px; border-radius: 10px;
            margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 15px; color: white; text-shadow: 0 1px 2px rgba(0,0,0,0.2); }}
        .header .subtitle {{ color: rgba(255,255,255,0.95); font-size: 14px; margin-bottom: 10px; }}
        .status-badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; }}
        .status-success {{ background: #52c41a; color: white; }}
        .status-fail {{ background: #ff4d4f; color: white; }}
        .status-running {{ background: #1890ff; color: white; }}
        .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 8px; }}
        .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); text-align: center; }}
        .card.filterable {{ cursor: pointer; transition: box-shadow 0.2s, outline 0.2s, transform 0.15s; user-select: none; }}
        .card.filterable:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.1); transform: translateY(-1px); }}
        .card.filterable.active {{ outline: 2px solid #1890ff; box-shadow: 0 0 0 3px rgba(24,144,255,0.15); }}
        .card .number {{ font-size: 32px; font-weight: bold; margin-bottom: 5px; }}
        .card .label {{ color: #666; font-size: 14px; }}
        .card.success .number {{ color: #52c41a; }}
        .card.fail .number {{ color: #ff4d4f; }}
        .card.warning .number {{ color: #faad14; }}
        .card.info .number {{ color: #8c8c8c; }}
        .filter-hint {{ min-height: 20px; margin-bottom: 12px; font-size: 13px; color: #1890ff; }}
        .case-block.filter-hidden, .suite-block.filter-hidden {{ display: none !important; }}
        .progress-section {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
        .progress-bar {{ height: 30px; background: #e4e7ed; border-radius: 15px; overflow: hidden; display: flex; }}
        .progress-segment {{ height: 100%; transition: width 0.3s; }}
        .progress-success {{ background: #52c41a; }}
        .progress-fail {{ background: #ff4d4f; }}
        .progress-error {{ background: #faad14; }}
        .progress-skip {{ background: #8c8c8c; }}
        .progress-info {{ display: flex; justify-content: space-between; margin-top: 10px; font-size: 14px; color: #666; }}
        .section {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
        .section-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
        .section h2 {{ color: #333; font-size: 18px; }}
        .control-buttons {{ display: flex; gap: 10px; }}
        .btn {{ padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; transition: all 0.3s; }}
        .btn-primary {{ background: #1890ff; color: white; }}
        .btn-primary:hover {{ background: #40a9ff; }}
        .btn-default {{ background: #f0f0f0; color: #333; }}
        .btn-default:hover {{ background: #e0e0e0; }}
        .suite-block {{ margin-bottom: 15px; border: 1px solid #e8e8e8; border-radius: 8px; overflow: hidden; }}
        .suite-header {{ background: #f5f5f5; padding: 12px 15px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; transition: background 0.2s; }}
        .suite-header:hover {{ background: #e8e8e8; }}
        .suite-title {{ display: flex; align-items: center; gap: 10px; }}
        .suite-name {{ font-weight: bold; color: #333; font-size: 15px; }}
        .toggle-icon {{ font-size: 12px; color: #666; transition: transform 0.3s; display: inline-block; width: 12px; }}
        .toggle-icon.collapsed {{ transform: rotate(-90deg); }}
        .suite-content {{ padding: 15px; display: none; }}
        .suite-content.expanded {{ display: block; }}
        .suite-stats {{ display: flex; gap: 15px; font-size: 12px; color: #666; }}
        .stat-success {{ color: #52c41a; }}
        .stat-fail {{ color: #ff4d4f; }}
        .stat-total {{ color: #1890ff; }}
        .case-block {{ margin-bottom: 12px; border: 1px solid #e8e8e8; border-radius: 6px; overflow: hidden; }}
        .case-header {{ padding: 10px 12px; background: #fafafa; display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; transition: background 0.2s; }}
        .case-header:hover {{ background: #f0f0f0; }}
        .case-header.success {{ border-left: 4px solid #52c41a; }}
        .case-header.fail {{ border-left: 4px solid #ff4d4f; }}
        .case-header.error {{ border-left: 4px solid #faad14; }}
        .case-header.skip {{ border-left: 4px solid #8c8c8c; }}
        .case-name-text {{ font-weight: 500; color: #333; font-size: 14px; display: flex; align-items: center; gap: 8px; }}
        .case-status-badge {{ padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold; }}
        .case-status-success {{ background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }}
        .case-status-fail {{ background: #fff2f0; color: #ff4d4f; border: 1px solid #ffa39e; }}
        .case-status-error {{ background: #fffbe6; color: #faad14; border: 1px solid #ffe58f; }}
        .case-status-skip {{ background: #f5f5f5; color: #8c8c8c; border: 1px solid #d9d9d9; }}
        .case-content {{ padding: 12px; display: none; background: white; }}
        .case-content.expanded {{ display: block; }}
        .log-item {{ padding: 10px 12px; border-left: 3px solid #ddd; margin-bottom: 8px; background: #fafafa; border-radius: 0 4px 4px 0; font-size: 13px; }}
        .log-item.success {{ border-left-color: #52c41a; background: #f6ffed; }}
        .log-item.fail {{ border-left-color: #ff4d4f; background: #fff2f0; }}
        .log-item.error {{ border-left-color: #faad14; background: #fffbe6; }}
        .log-item.info {{ border-left-color: #1890ff; background: #e6f7ff; }}
        .log-item .time {{ color: #8c8c8c; font-size: 11px; margin-bottom: 3px; }}
        .log-item .message {{ color: #333; white-space: pre-wrap; word-break: break-all; line-height: 1.5; }}
        .log-item .screenshot {{ margin-top: 8px; }}
        .log-item .screenshot img {{ max-width: 100%; max-height: 300px; border: 1px solid #ddd; border-radius: 4px; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; margin-top: 20px; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 15px; padding-top: 15px; border-top: 1px solid rgba(255,255,255,0.3); }}
        .info-item {{ display: flex; justify-content: space-between; }}
        .info-item .label {{ color: rgba(255,255,255,0.85); font-size: 14px; }}
        .info-item .value {{ color: white; font-weight: 500; font-size: 14px; }}
        .env-data {{ background: #f6f8fa; padding: 15px; border-radius: 6px; font-family: 'Courier New', monospace; font-size: 13px; overflow-x: auto; white-space: pre-wrap; word-break: break-all; color: #333; }}
        .no-logs {{ color: #999; text-align: center; padding: 30px; font-style: italic; }}
        .task-logs {{ margin-bottom: 20px; padding: 15px; background: #f6f8fa; border-radius: 6px; }}
        .task-logs-title {{ font-weight: bold; color: #333; margin-bottom: 10px; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📝 {title}</h1>
            <div class="subtitle">
                <span class="status-badge {status_class}">{status}</span>
                <span style="margin-left: 15px;">执行时间：{start_time}</span>
                <span style="margin-left: 15px;">耗时：{duration}秒</span>
            </div>
            <div class="info-grid">
                <div class="info-item">
                    <span class="label">执行人：</span>
                    <span class="value">{username}</span>
                </div>
                <div class="info-item">
                    <span class="label">{runtime_label}：</span>
                    <span class="value">{runtime_value}</span>
                </div>
                <div class="info-item">
                    <span class="label">{env_label}：</span>
                    <span class="value">{env_value}</span>
                </div>
                <div class="info-item">
                    <span class="label">通过率：</span>
                    <span class="value">{pass_rate}%</span>
                </div>
            </div>
        </div>

        <div class="summary-cards">
            <div class="card info filterable active" data-filter="all" onclick="filterByStatus('all')" title="显示全部用例"><div class="number">{all_count}</div><div class="label">用例总数</div></div>
            <div class="card success filterable" data-filter="success" onclick="filterByStatus('success')" title="仅看成功"><div class="number">{success}</div><div class="label">成功</div></div>
            <div class="card fail filterable" data-filter="fail" onclick="filterByStatus('fail')" title="仅看失败"><div class="number">{fail}</div><div class="label">失败</div></div>
            <div class="card warning filterable" data-filter="error" onclick="filterByStatus('error')" title="仅看错误"><div class="number">{error}</div><div class="label">错误</div></div>
            <div class="card info filterable" data-filter="skip" onclick="filterByStatus('skip')" title="仅看跳过"><div class="number">{skip}</div><div class="label">跳过</div></div>
            <div class="card info filterable" data-filter="no_run" onclick="filterByStatus('no_run')" title="仅看未运行"><div class="number">{no_run}</div><div class="label">未运行</div></div>
        </div>
        <div id="status-filter-hint" class="filter-hint"></div>

        <div class="progress-section">
            <h3 style="margin-bottom: 15px; color: #333;">执行进度</h3>
            <div class="progress-bar">
                <div class="progress-segment progress-success" style="width: {success_percent}%"></div>
                <div class="progress-segment progress-fail" style="width: {fail_percent}%"></div>
                <div class="progress-segment progress-error" style="width: {error_percent}%"></div>
                <div class="progress-segment progress-skip" style="width: {skip_percent}%"></div>
            </div>
            <div class="progress-info">
                <span>成功率：{success_percent}%</span>
                <span>失败率：{fail_percent}%</span>
            </div>
        </div>''')
    
    # 环境部分
    html_parts.append(env_section)
    
    # 日志部分
    html_parts.append(logs_section)
    
    # 页脚和脚本
    html_parts.append(f'''
        <div class="footer">
            <p>BrickCore - 测试报告</p>
            <p>生成时间：{generate_time}</p>
        </div>
    </div>

    <script>
        // 切换套件展开/收起
        function toggleSuite(element) {{
            const content = element.nextElementSibling;
            const icon = element.querySelector('.toggle-icon');
            if (content.classList.contains('expanded')) {{
                content.classList.remove('expanded');
                icon.classList.add('collapsed');
            }} else {{
                content.classList.add('expanded');
                icon.classList.remove('collapsed');
            }}
        }}

        // 切换用例展开/收起
        function toggleCase(element) {{
            const content = element.nextElementSibling;
            const icon = element.querySelector('.toggle-icon');
            if (content.classList.contains('expanded')) {{
                content.classList.remove('expanded');
                icon.classList.add('collapsed');
            }} else {{
                content.classList.add('expanded');
                icon.classList.remove('collapsed');
            }}
        }}

        // 按状态筛选用例（点击顶部统计卡片）
        function filterByStatus(status) {{
            document.querySelectorAll('.summary-cards .card.filterable').forEach(function(card) {{
                card.classList.toggle('active', card.getAttribute('data-filter') === status);
            }});
            document.querySelectorAll('.case-block').forEach(function(block) {{
                var s = block.getAttribute('data-status') || '';
                var show = status === 'all' || s === status;
                block.classList.toggle('filter-hidden', !show);
            }});
            document.querySelectorAll('.suite-block').forEach(function(suite) {{
                var cases = suite.querySelectorAll('.case-block');
                if (!cases.length) {{
                    suite.classList.toggle('filter-hidden', status !== 'all');
                    return;
                }}
                var anyVisible = false;
                cases.forEach(function(c) {{
                    if (!c.classList.contains('filter-hidden')) anyVisible = true;
                }});
                suite.classList.toggle('filter-hidden', !anyVisible);
                if (anyVisible && status !== 'all') {{
                    var content = suite.querySelector('.suite-content');
                    var icon = suite.querySelector('.suite-header .toggle-icon');
                    if (content) content.classList.add('expanded');
                    if (icon) icon.classList.remove('collapsed');
                }}
            }});
            var hint = document.getElementById('status-filter-hint');
            if (hint) {{
                var labels = {{ all: '全部', success: '成功', fail: '失败', error: '错误', skip: '跳过', no_run: '未运行' }};
                hint.textContent = status === 'all' ? '' : ('当前筛选：' + (labels[status] || status) + '（点击「用例总数」可清除）');
            }}
        }}

        // 展开所有
        function expandAll() {{
            document.querySelectorAll('.suite-content').forEach(function(el) {{ el.classList.add('expanded'); }});
            document.querySelectorAll('.case-content').forEach(function(el) {{ el.classList.add('expanded'); }});
            document.querySelectorAll('.toggle-icon').forEach(function(el) {{ el.classList.remove('collapsed'); }});
        }}

        // 收起所有
        function collapseAll() {{
            document.querySelectorAll('.suite-content').forEach(function(el) {{ el.classList.remove('expanded'); }});
            document.querySelectorAll('.case-content').forEach(function(el) {{ el.classList.remove('expanded'); }});
            document.querySelectorAll('.toggle-icon').forEach(function(el) {{ el.classList.add('collapsed'); }});
        }}
    </script>
</body>
</html>''')
    
    return ''.join(html_parts)


def generate_env_section(env: Dict[str, Any]) -> str:
    """生成环境数据部分"""
    if not env:
        return ''
    if isinstance(env, str):
        try:
            env = json.loads(env)
        except Exception:
            return ''

    env = _sanitize_env_for_export(env)
    if isinstance(env, dict) and env.get("engine_type") == "app":
        rows = [
            ("执行引擎", "App 自动化"),
            ("驱动模式", driver_mode_display(env.get("driver_mode"))),
            ("设备 UDID", env.get("device_udid") or "—"),
            ("应用包名", env.get("app_id") or "—"),
            ("项目 ID", env.get("project_id", "—")),
            ("环境 ID", env.get("environment_id", "—")),
            ("隐式等待(秒)", env.get("implicit_wait", "—")),
            ("自动授权", "是" if env.get("auto_grant_permissions") else "否"),
            ("录制视频", "是" if env.get("record_video", False) else "否"),
            ("触发来源", trigger_source_label(env.get("trigger_source"))),
        ]
        row_html = "".join(
            f'<tr><td style="padding:8px 12px;border-bottom:1px solid #eee;color:#666;width:140px;">{k}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #eee;">{escape_html(str(v))}</td></tr>'
            for k, v in rows
        )
        return f'''
        <div class="section">
            <h2>⚙️ 执行环境</h2>
            <table style="width:100%;border-collapse:collapse;background:#fafafa;border-radius:6px;overflow:hidden;font-size:13px;">{row_html}</table>
        </div>
        '''

    env_str = escape_html(json.dumps(env, ensure_ascii=False, indent=2))
    return f'''
        <div class="section">
            <h2>⚙️ 执行环境数据</h2>
            <div class="env-data"><pre style="margin:0;white-space:pre-wrap;word-break:break-all;">{env_str}</pre></div>
        </div>
    '''


def generate_logs_section(record_data: Dict, suite_records: List[Dict], case_records: List[Dict], img_options: Optional[ImageExportOptions] = None) -> str:
    """生成日志部分"""
    if img_options is None:
        img_options = ImageExportOptions()
    
    html_parts = []
    html_parts.append('''
        <div class="section">
            <div class="section-header">
                <h2>📋 执行日志</h2>
                <div class="control-buttons">
                    <button class="btn btn-primary" onclick="expandAll()">📂 全部展开</button>
                    <button class="btn btn-default" onclick="collapseAll()">📁 全部收起</button>
                </div>
            </div>''')
    
    # 任务级别日志
    task_logs = record_data.get('execution_log') or []
    if task_logs:
        html_parts.append('<div class="task-logs"><div class="task-logs-title">📌 任务执行日志</div>')
        html_parts.append(parse_and_format_logs(task_logs))
        html_parts.append('</div>')
    
    # 套件和用例日志
    if suite_records:
        for i, suite in enumerate(suite_records):
            suite_name = suite.get('suite_name', f'套件{i+1}')
            suite_logs = suite.get('execution_log') or []
            
            suite_success = suite.get('success', 0)
            suite_fail = suite.get('fail', 0)
            suite_error = suite.get('error', 0)
            suite_all = suite.get('all', 0) or suite.get('case_count', 0)
            
            html_parts.append(f'<div class="suite-block">')
            html_parts.append(f'<div class="suite-header" onclick="toggleSuite(this)">')
            html_parts.append(f'<div class="suite-title"><span class="toggle-icon collapsed">▼</span><span class="suite-name">📦 {suite_name}</span></div>')
            html_parts.append(f'<div class="suite-stats"><span class="stat-total">用例: {suite_all}</span><span class="stat-success">✅ {suite_success}</span><span class="stat-fail">❌ {suite_fail}</span>')
            if suite_error > 0:
                html_parts.append(f'<span style="color: #faad14;">⚠️ {suite_error}</span>')
            html_parts.append('</div></div>')
            html_parts.append('<div class="suite-content">')
            
            # 套件级别日志
            if suite_logs:
                html_parts.append('<div style="margin-bottom: 15px;"><div style="font-weight: bold; color: #666; margin-bottom: 8px; font-size: 13px;">套件日志</div>')
                html_parts.append(parse_and_format_logs(suite_logs))
                html_parts.append('</div>')
            
            # 该套件下的用例日志
            suite_id = suite.get('id')
            if case_records and suite_id:
                suite_cases = [c for c in case_records if c.get('suite_execution_id') == suite_id]
                if suite_cases:
                    html_parts.append('<div style="margin-top: 15px;"><div style="font-weight: bold; color: #666; margin-bottom: 8px; font-size: 13px;">用例执行详情</div>')
                    for case in suite_cases:
                        html_parts.append(generate_case_log_html(case, img_options))
                    html_parts.append('</div>')
            
            html_parts.append('</div></div>')

    has_case_blocks = bool(suite_records)
    if case_records and not suite_records:
        html_parts.append('<div style="margin-top: 15px;"><div style="font-weight: bold; color: #666; margin-bottom: 8px; font-size: 13px;">用例执行详情</div>')
        for case in case_records:
            html_parts.append(generate_case_log_html(case, img_options))
        html_parts.append('</div>')
        has_case_blocks = True
    
    # 如果没有日志
    if not task_logs and not has_case_blocks:
        html_parts.append('<div class="no-logs">暂无日志记录</div>')
    
    html_parts.append('</div>')
    return ''.join(html_parts)


def generate_case_log_html(case: Dict, img_options: Optional[ImageExportOptions] = None) -> str:
    """生成用例日志 HTML"""
    if img_options is None:
        img_options = ImageExportOptions()
    
    case_name = case.get('case_name', '未知用例')
    case_status = case.get('status', 'no_run')
    run_info = case.get('result_data', {})
    
    # 兼容 result_data 为 JSON 字符串的情况
    if isinstance(run_info, str):
        try:
            run_info = json.loads(run_info)
        except:
            run_info = {}
    
    # 状态映射
    status_map = {
        'success': ('success', '成功'),
        'fail': ('fail', '失败'),
        'error': ('error', '错误'),
        'skip': ('skip', '跳过'),
        'no_run': ('skip', '未执行'),
        'running': ('skip', '执行中'),
    }
    status_class, status_text = status_map.get(case_status, ('skip', '未知'))
    filter_status = case_status if case_status in ('success', 'fail', 'error', 'skip', 'no_run', 'running') else 'no_run'
    
    html_parts = []
    html_parts.append(f'<div class="case-block" data-status="{filter_status}">')
    html_parts.append(f'<div class="case-header {status_class}" onclick="toggleCase(this)">')
    html_parts.append(f'<div class="case-name-text"><span class="toggle-icon collapsed">▼</span><span>{case_name}</span></div>')
    html_parts.append(f'<span class="case-status-badge case-status-{status_class}">{status_text}</span>')
    html_parts.append('</div>')
    html_parts.append('<div class="case-content">')
    
    # 显示视频（如果勾选了包含视频）
    if img_options.include_video and isinstance(run_info, dict):
        video_url = run_info.get('video_url', '')
        if video_url:
            if video_url.startswith('data:'):
                video_type = 'video/mp4' if 'mp4' in video_url[:40] else 'video/webm'
                html_parts.append(f'<div class="log-item info"><div class="message">🎬 执行录屏</div><video controls style="max-width:100%;max-height:400px;border-radius:4px;margin-top:8px;"><source src="{video_url}" type="{video_type}"></video></div>')
            elif video_url.startswith('http'):
                # 外部链接视频
                html_parts.append(f'<div class="log-item info"><div class="message">🎬 执行录屏: <a href="{video_url}" target="_blank">点击观看</a></div></div>')
    elif not img_options.include_video and isinstance(run_info, dict) and run_info.get('video_url'):
        # 未勾选视频，但有视频可用时显示提示
        html_parts.append(f'<div class="log-item info" style="background:#e6f7ff;border-left-color:#1890ff;"><div class="message">💡 提示：本次导出未包含执行录屏。如需查看录屏，请在导出时勾选"包含视频"选项。</div></div>')
    
    # 用例级别截图
    if isinstance(run_info, dict) and img_options.include_images and _should_include_image(img_options, case_status):
        case_img = run_info.get('img') or run_info.get('img_url')
        if case_img and isinstance(case_img, str) and case_img.strip():
            if case_img.startswith('data:') or case_img.startswith('http'):
                html_parts.append(f'<div class="log-item info"><div class="message">📸 用例结束截图</div><div class="screenshot"><img src="{case_img}" alt="用例截图"></div></div>')
    
    # 变量快照
    if isinstance(run_info, dict) and run_info.get('variables_snapshot'):
        html_parts.append(generate_variables_snapshot_html(run_info.get('variables_snapshot')))
    
    # 解析用例执行步骤（步骤总是显示，不受图片选项影响）
    if isinstance(run_info, dict):
        steps = run_info.get('steps') or run_info.get('records') or []
        if steps:
            for step in steps:
                html_parts.append(parse_step_to_log_html(step))
        elif run_info.get('log_data'):
            html_parts.append(parse_and_format_logs(run_info.get('log_data')))
        elif run_info.get('error_msg') or run_info.get('error'):
            err = run_info.get('error_msg') or run_info.get('error')
            html_parts.append(f'<div class="log-item fail"><div class="message">{escape_html(str(err))}</div></div>')
        else:
            summary = {k: run_info.get(k) for k in ('id', 'name', 'status', 'duration') if run_info.get(k) is not None}
            if summary:
                info_str = escape_html(json.dumps(summary, ensure_ascii=False, indent=2))
                html_parts.append(f'<div class="log-item info"><pre style="margin:0;font-size:12px;">{info_str}</pre></div>')
            else:
                html_parts.append('<div style="color: #999; padding: 10px;">无执行详情</div>')
    elif isinstance(run_info, list):
        for item in run_info:
            html_parts.append(parse_step_to_log_html(item))
    elif run_info:
        html_parts.append(f'<div class="log-item info">{str(run_info)}</div>')
    else:
        html_parts.append('<div style="color: #999; padding: 10px;">无执行详情</div>')
    
    html_parts.append('</div></div>')
    return ''.join(html_parts)


def parse_step_to_log_html(step: Any) -> str:
    """解析步骤为日志 HTML"""
    if isinstance(step, dict):
        status = step.get('status', 'info')
        status_class = status if status in ['success', 'fail', 'error'] else 'info'
        
        time_str = step.get('time') or step.get('timestamp') or datetime.now().strftime('%H:%M:%S')
        
        message = step.get('message') or step.get('msg') or step.get('content') or ''
        keyword = step.get('keyword', '')
        desc = step.get('desc', '')
        if keyword and desc:
            message = message or f'{keyword} · {desc}'
        elif keyword:
            message = message or keyword
        elif desc:
            message = message or desc
        step_no = step.get('step_index')
        if step_no is not None:
            message = f'步骤 {int(step_no) + 1} · {message}' if message else f'步骤 {int(step_no) + 1}'
        frag = step.get('_from_fragment')
        if isinstance(frag, dict) and frag.get('name'):
            message = f'[片段·{frag["name"]}] {message}'
        if not message and 'name' in step:
            message = step['name']
        if not message:
            message = json.dumps(step, ensure_ascii=False)

        meta_bits = []
        if step.get('locator_type'):
            meta_bits.append(f"定位:{step.get('locator_type')}")
        if step.get('execution_context'):
            meta_bits.append(f"上下文:{step.get('execution_context')}")
        if step.get('webview_page_url'):
            meta_bits.append(f"H5:{step.get('webview_page_url')}")
        if step.get('match_score') is not None:
            try:
                meta_bits.append(f"相似度:{float(step.get('match_score')) * 100:.1f}%")
            except (TypeError, ValueError):
                meta_bits.append(f"相似度:{step.get('match_score')}")
        if meta_bits:
            message = f"{message} [{' · '.join(meta_bits)}]"
        
        screenshot_html = ''
        screenshot = step.get('screenshot') or step.get('image')
        # 只有当screenshot有实际内容（Base64或URL）时才显示
        if screenshot and isinstance(screenshot, str) and screenshot.strip():
            # 如果是Base64图片或有效URL，显示图片
            if screenshot.startswith('data:') or screenshot.startswith('http://') or screenshot.startswith('https://'):
                screenshot_html = f'<div class="screenshot"><img src="{screenshot}" alt="截图"></div>'
        
        return f'<div class="log-item {status_class}"><div class="time">{time_str}</div><div class="message">{message}</div>{screenshot_html}</div>'
    elif isinstance(step, str):
        try:
            parsed = json.loads(step)
            if isinstance(parsed, dict):
                return parse_step_to_log_html(parsed)
        except:
            pass
        return f'<div class="log-item info"><div class="message">{step}</div></div>'
    
    return f'<div class="log-item info"><div class="message">{str(step)}</div></div>'


def generate_variables_snapshot_html(snapshot: Dict) -> str:
    """生成变量快照 HTML"""
    if not snapshot:
        return ''

    case_vars = snapshot.get('case_vars', {})
    dynamic_vars = snapshot.get('dynamic_vars', {})
    global_vars = snapshot.get('global_vars', {})
    usage = snapshot.get('usage', {})

    if not case_vars and not dynamic_vars and not global_vars:
        return ''

    def format_value(v):
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    def var_rows(vars_dict, label, tag_bg, tag_color):
        rows = []
        for name, value in vars_dict.items():
            var_usage = usage.get(name, {})
            write_step = var_usage.get('write_step')
            read_steps = var_usage.get('read_steps', [])
            read_str = '、'.join([f'步骤{s}' for s in read_steps]) if read_steps else '—'
            write_str = f'步骤{write_step}' if write_step else '—'
            val_str = escape_html(format_value(value))
            rows.append(f'''<tr style="border-bottom:1px solid #f0f0f0;">
                <td style="padding:10px 12px;white-space:nowrap;width:82px;">
                    <span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:{tag_bg};color:{tag_color};white-space:nowrap;">{label}</span>
                </td>
                <td style="padding:10px 12px;white-space:nowrap;width:120px;font-weight:600;color:#333;font-size:12px;">{escape_html(name)}</td>
                <td style="padding:10px 12px;max-width:360px;" title="{val_str}">
                    <span style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#555;font-size:12px;font-family:monospace;">{val_str}</span>
                </td>
                <td style="padding:10px 12px;white-space:nowrap;width:72px;color:#999;font-size:11px;">{write_str}</td>
                <td style="padding:10px 12px;white-space:nowrap;width:90px;color:#999;font-size:11px;">{read_str}</td>
            </tr>''')
        return ''.join(rows)

    rows_html = ''
    rows_html += var_rows(global_vars, '全局', '#e6f7ff', '#1890ff')
    rows_html += var_rows(case_vars, '用例', '#fff7e6', '#fa8c16')
    rows_html += var_rows(dynamic_vars, '动态', '#f6ffed', '#52c41a')

    if not rows_html:
        return ''

    return f'''<div style="margin:12px 0;border:1px solid #e8e8e8;border-radius:8px;overflow:hidden;background:#fff;">
        <div style="background:#fafafa;padding:10px 16px;font-weight:600;font-size:13px;border-bottom:1px solid #e8e8e8;color:#333;">📊 变量快照</div>
        <div style="overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed;">
                <thead>
                    <tr style="background:#f8f9fa;">
                        <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;font-weight:600;color:#666;font-size:11px;width:82px;">类型</th>
                        <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;font-weight:600;color:#666;font-size:11px;width:120px;">变量名</th>
                        <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;font-weight:600;color:#666;font-size:11px;">值</th>
                        <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;font-weight:600;color:#666;font-size:11px;width:72px;">提取</th>
                        <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;font-weight:600;color:#666;font-size:11px;width:90px;">引用</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
    </div>'''


def parse_and_format_logs(logs: List) -> str:
    """解析并格式化日志列表"""
    if not logs:
        return '<div style="color: #999; padding: 10px;">无详细日志</div>'
    
    html = ''
    for log in logs:
        html += parse_step_to_log_html(log)
    
    return html if html else '<div style="color: #999; padding: 10px;">无详细日志</div>'


def format_time(time_str) -> str:
    """格式化时间字符串"""
    if not time_str:
        return '未知'
    if isinstance(time_str, datetime):
        return time_str.strftime('%Y-%m-%d %H:%M:%S')
    return str(time_str)


def escape_html(text: str) -> str:
    """HTML 转义"""
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _compress_image(data: bytes, max_width: int = 800, quality: int = 60) -> bytes:
    """压缩图片以减少 base64 后体积"""
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            img = img.resize((max_width, int(h * ratio)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality, optimize=True)
        return buf.getvalue()
    except Exception as e:
        print(f"[Report Export] Image compression failed: {e}, returning original")
        return data


def _collect_and_download_images(case_records: List[Dict], image_cache: Dict[str, str], img_options: ImageExportOptions):
    """收集所有图片/视频 URL 并并发下载转为 Base64，图片会自动压缩以减少体积"""
    from app.core.infra.minio_client import minio_client
    import urllib.parse
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # 1. 提取所有图片/视频 URL
    image_urls = {}
    for case in case_records:
        case_status = case.get('status', '')
        run_info = case.get('result_data', {})
        if isinstance(run_info, str):
            try:
                run_info = json.loads(run_info)
            except:
                continue
        
        if isinstance(run_info, dict):
            # 用例级别截图
            img = run_info.get('img', '')
            if img and _is_storage_media_url(img):
                if _should_include_image(img_options, case_status):
                    image_urls[img] = case_status
            
            # 视频 URL
            video_url = run_info.get('video_url', '')
            if video_url and _is_storage_media_url(video_url):
                if img_options.include_video:
                    image_urls[video_url] = case_status
            
            # 步骤截图
            steps = run_info.get('steps', []) or run_info.get('records', [])
            for step in steps:
                if isinstance(step, dict):
                    img = step.get('screenshot') or step.get('image')
                    if img and _is_storage_media_url(img):
                        if _should_include_image(img_options, case_status):
                            image_urls[img] = case_status
    
    if not image_urls:
        return
    
    # 2. 为所有 URL 预先生成可下载的链接
    download_tasks = {}
    for url in image_urls:
        try:
            if _is_storage_media_url(url):
                filename = _storage_object_key(url)
                presigned = minio_client.get_presigned_url(filename, expires=7200) if filename else None
                download_url = presigned.replace('https://', 'http://') if presigned else url
            else:
                download_url = url
            download_tasks[url] = download_url
        except Exception as e:
            print(f"[Report Export] Failed to prepare URL for {url}: {e}")
    
    # 3. 并发下载并转为 base64
    def _download_one(original_url: str, download_url: str) -> tuple:
        try:
            is_video = original_url.endswith('.webm') or original_url.endswith('.mp4')
            max_raw_size = 200 * 1024 * 1024 if is_video else 20 * 1024 * 1024
            
            # 优先使用 MinIO 内部客户端下载（避免容器内通过公网 IP 回环访问自己导致超时）
            if _is_storage_media_url(original_url):
                filename = _storage_object_key(original_url)
                data = minio_client.download_object(filename) if filename else None
                if data is None:
                    return original_url, None
                if len(data) > max_raw_size:
                    print(f"[Report Export] File too large ({len(data)} bytes), skipped: {original_url}")
                    return original_url, None
            else:
                # 其他来源（如阿里云 OSS）用 HTTP 下载
                timeout = 60 if is_video else 15
                response = requests.get(download_url, timeout=timeout, stream=True)
                if response.status_code != 200:
                    print(f"[Report Export] Download failed {response.status_code}: {original_url}")
                    return original_url, None
                
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > max_raw_size:
                    print(f"[Report Export] File too large ({int(content_length)} bytes), skipped: {original_url}")
                    return original_url, None
                
                content = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    content.extend(chunk)
                    if len(content) > max_raw_size:
                        print(f"[Report Export] File too large during download, skipped: {original_url}")
                        return original_url, None
                
                data = bytes(content)
            
            if is_video:
                b64 = base64.b64encode(data).decode('utf-8')
                content_type = 'video/mp4' if original_url.endswith('.mp4') else 'video/webm'
                return original_url, f"data:{content_type};base64,{b64}"
            else:
                compressed = _compress_image(data, max_width=800, quality=60)
                b64 = base64.b64encode(compressed).decode('utf-8')
                return original_url, f"data:image/jpeg;base64,{b64}"
        except Exception as e:
            print(f"[Report Export] Download error for {original_url}: {e}")
            return original_url, None
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_download_one, url, durl): url for url, durl in download_tasks.items()}
        for future in as_completed(futures):
            orig_url, b64_data = future.result()
            if b64_data:
                image_cache[orig_url] = b64_data


def _replace_images_with_base64(case_records: List[Dict], image_cache: Dict[str, str], img_options: ImageExportOptions) -> List[Dict]:
    """将case_records中的图片URL替换为Base64"""
    import copy
    case_records = copy.deepcopy(case_records)
    
    for case in case_records:
        case_status = case.get('status', '')
        run_info = case.get('result_data', {})
        if isinstance(run_info, str):
            try:
                run_info = json.loads(run_info)
                was_string = True
            except:
                continue
        else:
            was_string = False
        
        if isinstance(run_info, dict):
            # 替换用例级别截图 (img字段)；未能内嵌的外链清空，避免离线/邮件裂图
            if _should_include_image(img_options, case_status):
                img = run_info.get('img', '')
                if img and img in image_cache:
                    run_info['img'] = image_cache[img]
                elif not (isinstance(img, str) and img.startswith('data:')):
                    run_info['img'] = ''
            else:
                run_info['img'] = ''
            
            # 替换视频URL
            if img_options.include_video:
                video_url = run_info.get('video_url', '')
                if video_url and video_url in image_cache:
                    run_info['video_url'] = image_cache[video_url]
                elif not (isinstance(video_url, str) and video_url.startswith('data:')):
                    run_info['video_url'] = ''
            else:
                run_info['video_url'] = ''
            
            # 替换步骤截图
            steps = run_info.get('steps', []) or run_info.get('records', [])
            for step in steps:
                if isinstance(step, dict):
                    if _should_include_image(img_options, case_status):
                        img = step.get('screenshot') or step.get('image')
                        if img and img in image_cache:
                            if 'screenshot' in step:
                                step['screenshot'] = image_cache[img]
                            if 'image' in step:
                                step['image'] = image_cache[img]
                        elif not (isinstance(img, str) and img.startswith('data:')):
                            if 'screenshot' in step:
                                step['screenshot'] = ''
                            if 'image' in step:
                                step['image'] = ''
                    else:
                        # 不导出图片时，清空截图字段
                        if 'screenshot' in step:
                            step['screenshot'] = ''
                        if 'image' in step:
                            step['image'] = ''
        
        if was_string:
            case['result_data'] = json.dumps(run_info, ensure_ascii=False)
        else:
            case['result_data'] = run_info
    
    return case_records
