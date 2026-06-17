"""
测试报告导出功能
支持导出 HTML 格式的测试报告，包含展开/收起功能
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import json
import re
import base64
import io
import requests
from PIL import Image
from app.core.config import MINIO_CONFIG


@dataclass
class ImageExportOptions:
    """图片导出选项"""
    include_images: bool = True      # 是否包含图片
    image_mode: str = "all"          # all-全部, failed-仅失败, none-不包含
    include_video: bool = True       # 是否包含视频


def _should_include_image(img_options: ImageExportOptions, case_status: str) -> bool:
    """根据选项判断是否包含该图片"""
    if not img_options.include_images or img_options.image_mode == "none":
        return False
    if img_options.image_mode == "failed":
        return case_status in ["fail", "error", "failed"]
    return True




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
    
    # 根据选项处理图片和视频
    image_cache = {}
    if case_records and (img_options.include_images or img_options.include_video):
        _collect_and_download_images(case_records, image_cache, img_options)
        if image_cache:
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
    browser = browser_map.get(browser_type, browser_type)
    host = env.get('host', '未知') if isinstance(env, dict) else '未知'
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
        .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); text-align: center; }}
        .card .number {{ font-size: 32px; font-weight: bold; margin-bottom: 5px; }}
        .card .label {{ color: #666; font-size: 14px; }}
        .card.success .number {{ color: #52c41a; }}
        .card.fail .number {{ color: #ff4d4f; }}
        .card.warning .number {{ color: #faad14; }}
        .card.info .number {{ color: #8c8c8c; }}
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
                    <span class="label">浏览器：</span>
                    <span class="value">{browser}</span>
                </div>
                <div class="info-item">
                    <span class="label">环境地址</span>
                    <span class="value">{host}</span>
                </div>
                <div class="info-item">
                    <span class="label">通过率：</span>
                    <span class="value">{pass_rate}%</span>
                </div>
            </div>
        </div>

        <div class="summary-cards">
            <div class="card info"><div class="number">{all_count}</div><div class="label">用例总数</div></div>
            <div class="card success"><div class="number">{success}</div><div class="label">成功</div></div>
            <div class="card fail"><div class="number">{fail}</div><div class="label">失败</div></div>
            <div class="card warning"><div class="number">{error}</div><div class="label">错误</div></div>
            <div class="card info"><div class="number">{skip}</div><div class="label">跳过</div></div>
            <div class="card info"><div class="number">{no_run}</div><div class="label">未运行</div></div>
        </div>

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
    
    env_str = json.dumps(env, ensure_ascii=False, indent=2)
    
    return f'''
        <div class="section">
            <h2>⚙️ 执行环境数据</h2>
            <div class="env-data">{env_str}</div>
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
    
    # 如果没有日志
    if not task_logs and not suite_records:
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
    
    html_parts = []
    html_parts.append(f'<div class="case-block">')
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
                # Base64 嵌入的视频
                html_parts.append(f'<div class="log-item info"><div class="message">🎬 执行录屏</div><video controls style="max-width:100%;max-height:400px;border-radius:4px;margin-top:8px;"><source src="{video_url}" type="video/webm"></video></div>')
            elif video_url.startswith('http'):
                # 外部链接视频
                html_parts.append(f'<div class="log-item info"><div class="message">🎬 执行录屏: <a href="{video_url}" target="_blank">点击观看</a></div></div>')
    elif not img_options.include_video and isinstance(run_info, dict) and run_info.get('video_url'):
        # 未勾选视频，但有视频可用时显示提示
        html_parts.append(f'<div class="log-item info" style="background:#e6f7ff;border-left-color:#1890ff;"><div class="message">💡 提示：本次导出未包含执行录屏。如需查看录屏，请在导出时勾选"包含视频"选项。</div></div>')
    
    # 变量快照
    if isinstance(run_info, dict) and run_info.get('variables_snapshot'):
        html_parts.append(generate_variables_snapshot_html(run_info.get('variables_snapshot')))
    
    # 解析用例执行步骤（步骤总是显示，不受图片选项影响）
    if isinstance(run_info, dict):
        steps = run_info.get('steps') or run_info.get('records') or []
        if steps:
            for step in steps:
                html_parts.append(parse_step_to_log_html(step))
        else:
            info_str = json.dumps(run_info, ensure_ascii=False, indent=2)
            html_parts.append(f'<div class="log-item info"><pre style="margin:0;font-size:12px;">{info_str}</pre></div>')
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
        
        message = step.get('message') or step.get('msg') or step.get('content') or step.get('keyword', '')
        frag = step.get('_from_fragment')
        if isinstance(frag, dict) and frag.get('name'):
            message = f'[片段·{frag["name"]}] {message}'
        if not message and 'name' in step:
            message = step['name']
        if not message:
            message = json.dumps(step, ensure_ascii=False)
        
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
    from app.core.minio_client import minio_client
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
            if img and (':9200/' in img or 'minio' in img or '192.168.' in img or 'aliyuncs.com' in img):
                if _should_include_image(img_options, case_status):
                    image_urls[img] = case_status
            
            # 视频 URL
            video_url = run_info.get('video_url', '')
            if video_url and (':9200/' in video_url or 'minio' in video_url or '192.168.' in video_url or 'aliyuncs.com' in video_url):
                if img_options.include_video:
                    image_urls[video_url] = case_status
            
            # 步骤截图
            steps = run_info.get('steps', []) or run_info.get('records', [])
            for step in steps:
                if isinstance(step, dict):
                    img = step.get('screenshot') or step.get('image')
                    if img and (':9200/' in img or 'minio' in img or '192.168.' in img or 'aliyuncs.com' in img):
                        if _should_include_image(img_options, case_status):
                            image_urls[img] = case_status
    
    if not image_urls:
        return
    
    # 2. 为所有 URL 预先生成可下载的链接
    download_tasks = {}
    for url in image_urls:
        try:
            if ':9200/' in url or 'minio' in url or '192.168.' in url or 'aliyuncs.com' in url:
                if '/' in url:
                    filename = urllib.parse.unquote(url.split('/')[-1].split('?')[0])
                    presigned = minio_client.get_presigned_url(filename, expires=7200)
                    download_url = presigned.replace('https://', 'http://') if presigned else url
                else:
                    download_url = url
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
            is_minio_url = (
                ':9200/' in original_url or 'minio' in original_url 
                or '192.168.' in original_url
            )
            
            if is_minio_url:
                filename = urllib.parse.unquote(original_url.split('/')[-1].split('?')[0])
                data = minio_client.download_object(filename)
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
                content_type = 'video/webm'
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
            # 替换用例级别截图 (img字段)
            if _should_include_image(img_options, case_status):
                img = run_info.get('img', '')
                if img and img in image_cache:
                    run_info['img'] = image_cache[img]
            else:
                run_info['img'] = ''
            
            # 替换视频URL
            if img_options.include_video:
                video_url = run_info.get('video_url', '')
                if video_url and video_url in image_cache:
                    run_info['video_url'] = image_cache[video_url]
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
