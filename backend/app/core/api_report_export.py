"""
API 测试报告导出功能
支持导出 HTML 格式的测试报告，包含请求/响应详情、断言结果、变量提取
"""

from ast import literal_eval
from datetime import datetime
from typing import Dict, Any, List, Optional
import json


def resolve_case_response_body(item: Dict[str, Any]) -> Any:
    """从用例结果中解析响应 Body（兼容 response_detail / retry_info）"""
    body = item.get("response_body")
    if body is not None and body != "":
        return body

    response_detail = item.get("response_detail") or {}
    if isinstance(response_detail, dict) and response_detail.get("body") is not None:
        return response_detail.get("body")

    attempts = []
    request_detail = item.get("request_detail") or {}
    if isinstance(request_detail, dict):
        retry_info = request_detail.get("retry_info") or {}
        attempts = retry_info.get("attempts") or []
    if not attempts:
        retry_info = item.get("retry_info") or {}
        attempts = retry_info.get("attempts") or []
    if attempts:
        last = attempts[-1]
        if last.get("response_body") is not None:
            return last.get("response_body")
    return None


def resolve_http_response_time(item: Dict[str, Any]) -> Optional[float]:
    """解析单条用例的纯 HTTP 耗时(ms)"""
    if not isinstance(item, dict):
        return None
    if item.get("http_response_time") is not None:
        return float(item["http_response_time"])
    response_detail = item.get("response_detail") or {}
    if isinstance(response_detail, dict) and response_detail.get("http_time") is not None:
        return float(response_detail["http_time"])
    request_detail = item.get("request_detail") or {}
    if isinstance(request_detail, dict):
        stage = request_detail.get("stage_timings") or {}
        if isinstance(stage, dict) and stage.get("request_ms") is not None:
            return float(stage["request_ms"])
    return None


def sum_http_response_time_ms(case_results: List[Dict[str, Any]]) -> float:
    """汇总多条用例的纯 HTTP 耗时(ms)"""
    total = 0.0
    for cr in case_results or []:
        if not isinstance(cr, dict):
            continue
        t = resolve_http_response_time(cr)
        if t is not None:
            total += float(t)
    return round(total, 2)


def sum_plan_item_results_http_ms(item_results: List[Dict[str, Any]]) -> float:
    """汇总计划 item_results 中所有用例的 HTTP 耗时(ms)"""
    total = 0.0
    for item in item_results or []:
        if not isinstance(item, dict):
            continue
        total += sum_http_response_time_ms(item.get("case_results") or [])
    return round(total, 2)


def resolve_case_response_headers(item: Dict[str, Any]) -> Any:
    """从用例结果中解析响应 Headers"""
    headers = item.get("response_headers")
    if headers:
        return headers
    response_detail = item.get("response_detail") or {}
    if isinstance(response_detail, dict) and response_detail.get("headers"):
        return response_detail.get("headers")
    return {}


def format_display_json(data: Any) -> str:
    """格式化为缩进 JSON 文本；兼容 dict/list、JSON 字符串、Python 字面量字符串"""
    if data is None or data == "":
        return ""
    if isinstance(data, (dict, list)):
        return json.dumps(data, ensure_ascii=False, indent=2)
    if isinstance(data, str):
        s = data.strip()
        if not s:
            return ""
        try:
            return json.dumps(json.loads(s), ensure_ascii=False, indent=2)
        except Exception:
            try:
                parsed = literal_eval(s)
                if isinstance(parsed, (dict, list)):
                    return json.dumps(parsed, ensure_ascii=False, indent=2)
            except Exception:
                pass
        return s
    return str(data)


def generate_api_html_report(
    suite_record: Dict[str, Any],
    case_results: List[Dict[str, Any]],
    plan_items: List[Dict[str, Any]] = None,
    report_type: str = "suite"
) -> str:
    """
    生成 API 测试 HTML 报告

    Args:
        suite_record: 套件/计划执行记录
        case_results: 用例执行结果列表
        plan_items: 计划 item 列表（计划报告用）
        report_type: 报告类型 suite/plan
    """
    total = suite_record.get('total_cases', 0) or len(case_results)
    success = suite_record.get('success_cases', 0)
    failed = suite_record.get('failed_cases', 0)
    skipped = suite_record.get('skipped_cases', 0)
    error = suite_record.get('error_cases', 0) or 0

    success_percent = round(success / total * 100, 2) if total > 0 else 0
    fail_percent = round(failed / total * 100, 2) if total > 0 else 0
    skip_percent = round(skipped / total * 100, 2) if total > 0 else 0

    status = suite_record.get('status', '未知')
    if status == 'success':
        status_class = 'status-success'
        status_text = '成功'
    elif status == 'failed':
        status_class = 'status-fail'
        status_text = '失败'
    elif status == 'running':
        status_class = 'status-running'
        status_text = '执行中'
    else:
        status_class = 'status-partial'
        status_text = status

    title = suite_record.get('suite_name', 'API 测试报告')
    start_time = format_time(suite_record.get('start_time'))
    end_time = format_time(suite_record.get('end_time'))
    duration = round(suite_record.get('duration', 0), 2)
    http_duration = suite_record.get('http_duration')
    if http_duration is None:
        if report_type == "plan" and plan_items:
            http_duration = sum_plan_item_results_http_ms(plan_items)
        else:
            http_duration = sum_http_response_time_ms(case_results)
    http_duration = round(float(http_duration or 0), 2)
    username = suite_record.get('run_by', '未知')
    env_name = suite_record.get('env_name', '未知')
    generate_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 报告类型标签
    type_badge = "📋 套件报告" if report_type == "suite" else "📑 计划报告"

    html_parts = []

    # HTML 头部
    html_parts.append(f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API 测试报告 - {title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #f5f7fa; color: #333; line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(135deg, #1a73e8 0%, #4285f4 100%);
            color: white; padding: 30px; border-radius: 10px;
            margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 15px; color: white; text-shadow: 0 1px 2px rgba(0,0,0,0.2); }}
        .header .subtitle {{ color: rgba(255,255,255,0.95); font-size: 14px; margin-bottom: 10px; }}
        .status-badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; }}
        .status-success {{ background: #52c41a; color: white; }}
        .status-fail {{ background: #ff4d4f; color: white; }}
        .status-running {{ background: #1890ff; color: white; }}
        .status-partial {{ background: #faad14; color: white; }}
        .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 15px; margin-bottom: 20px; }}
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
        .case-block {{ margin-bottom: 15px; border: 1px solid #e8e8e8; border-radius: 8px; overflow: hidden; }}
        .case-header {{ padding: 12px 15px; background: #fafafa; display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; transition: background 0.2s; }}
        .case-header:hover {{ background: #f0f0f0; }}
        .case-header.success {{ border-left: 4px solid #52c41a; }}
        .case-header.fail {{ border-left: 4px solid #ff4d4f; }}
        .case-header.skip {{ border-left: 4px solid #8c8c8c; }}
        .case-header.running {{ border-left: 4px solid #1890ff; }}
        .case-name-text {{ font-weight: 500; color: #333; font-size: 15px; display: flex; align-items: center; gap: 8px; }}
        .case-status-badge {{ padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: bold; }}
        .case-status-success {{ background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }}
        .case-status-fail {{ background: #fff2f0; color: #ff4d4f; border: 1px solid #ffa39e; }}
        .case-status-skip {{ background: #f5f5f5; color: #8c8c8c; border: 1px solid #d9d9d9; }}
        .case-status-running {{ background: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }}
        .case-content {{ padding: 15px; display: none; background: white; }}
        .case-content.expanded {{ display: block; }}
        .toggle-icon {{ font-size: 12px; color: #666; transition: transform 0.3s; display: inline-block; width: 12px; }}
        .toggle-icon.collapsed {{ transform: rotate(-90deg); }}
        .info-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 15px; padding-top: 15px; border-top: 1px solid rgba(255,255,255,0.3); }}
        .info-item {{ display: flex; justify-content: space-between; }}
        .info-item .label {{ color: rgba(255,255,255,0.85); font-size: 14px; }}
        .info-item .value {{ color: white; font-weight: 500; font-size: 14px; }}
        .detail-block {{ margin-bottom: 15px; }}
        .detail-title {{ font-weight: 600; font-size: 13px; color: #333; margin-bottom: 8px; padding-left: 8px; border-left: 3px solid #409eff; }}
        .detail-content {{ background: #f6f8fa; border-radius: 4px; padding: 12px; font-family: 'Courier New', monospace; font-size: 13px; overflow: auto; max-height: 480px; white-space: pre; word-break: normal; color: #333; }}
        .http-method {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 8px; }}
        .method-get {{ background: #e6f7ff; color: #1890ff; }}
        .method-post {{ background: #f6ffed; color: #52c41a; }}
        .method-put {{ background: #fffbe6; color: #faad14; }}
        .method-delete {{ background: #fff2f0; color: #ff4d4f; }}
        .method-patch {{ background: #f0f0f0; color: #666; }}
        .assertion-table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }}
        .assertion-table th, .assertion-table td {{ border: 1px solid #e8e8e8; padding: 8px; text-align: left; }}
        .assertion-table th {{ background: #fafafa; font-weight: 600; }}
        .assertion-table td.actual-cell {{ max-width: 280px; word-break: break-all; vertical-align: top; line-height: 1.45; }}
        .assertion-pass {{ color: #52c41a; }}
        .assertion-fail {{ color: #ff4d4f; }}
        .vars-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }}
        .var-item {{ background: #f6f8fa; padding: 8px 12px; border-radius: 4px; }}
        .var-key {{ font-weight: 600; color: #1890ff; font-size: 12px; }}
        .var-value {{ color: #333; font-size: 13px; word-break: break-all; }}
        .error-alert {{ background: #fff2f0; border: 1px solid #ffa39e; color: #ff4d4f; padding: 12px; border-radius: 4px; margin-bottom: 15px; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; margin-top: 20px; }}
        .no-logs {{ color: #999; text-align: center; padding: 30px; font-style: italic; }}
        .tab-nav {{ display: flex; border-bottom: 1px solid #e8e8e8; margin-bottom: 12px; }}
        .tab-item {{ padding: 8px 16px; cursor: pointer; font-size: 13px; border-bottom: 2px solid transparent; }}
        .tab-item.active {{ border-bottom-color: #1890ff; color: #1890ff; font-weight: 500; }}
        .tab-panel {{ display: none; }}
        .tab-panel.active {{ display: block; }}
        .plan-item-block {{ margin-bottom: 20px; border: 1px solid #e8e8e8; border-radius: 8px; overflow: hidden; }}
        .plan-item-header {{ padding: 14px 16px; background: #f0f5ff; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; border-bottom: 1px solid #e8e8e8; }}
        .plan-item-order {{ background: #1890ff; color: white; padding: 2px 10px; border-radius: 11px; font-size: 12px; font-weight: 600; }}
        .plan-item-type {{ background: #e6f7ff; color: #1890ff; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
        .plan-item-name {{ font-weight: 600; font-size: 15px; color: #333; flex: 1; }}
        .plan-item-meta {{ font-size: 12px; color: #666; }}
        .plan-item-cases {{ padding: 12px 16px; background: #fafafa; }}
        .plan-item-cases .case-block {{ margin-bottom: 12px; }}
        .plan-item-cases .case-block:last-child {{ margin-bottom: 0; }}
        .hooks-block {{ margin-bottom: 12px; padding: 12px; background: #fafafa; border-radius: 6px; border: 1px solid #e8e8e8; }}
        .hooks-block h4 {{ font-size: 14px; margin-bottom: 8px; color: #333; }}
        .hooks-log {{ font-family: 'Courier New', monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌐 {title}</h1>
            <div class="subtitle">
                <span class="status-badge {status_class}">{status_text}</span>
                <span style="margin-left: 15px;">{type_badge}</span>
                <span style="margin-left: 15px;">开始时间：{start_time}</span>
                <span style="margin-left: 15px;">结束时间：{end_time}</span>
                <span style="margin-left: 15px;">执行总耗时：{duration / 1000:.2f}s ({duration:.0f}ms)</span>
                <span style="margin-left: 15px;">接口总耗时：{http_duration:.0f}ms</span>
            </div>
            <div class="info-grid">
                <div class="info-item">
                    <span class="label">执行人：</span>
                    <span class="value">{username}</span>
                </div>
                <div class="info-item">
                    <span class="label">执行环境：</span>
                    <span class="value">{env_name}</span>
                </div>
                <div class="info-item">
                    <span class="label">总用例数：</span>
                    <span class="value">{total}</span>
                </div>
                <div class="info-item">
                    <span class="label">成功率：</span>
                    <span class="value">{success_percent}%</span>
                </div>
            </div>
        </div>

        <div class="summary-cards">
            <div class="card info"><div class="number">{total}</div><div class="label">用例总数</div></div>
            <div class="card success"><div class="number">{success}</div><div class="label">成功</div></div>
            <div class="card fail"><div class="number">{failed}</div><div class="label">失败</div></div>
            <div class="card warning"><div class="number">{skipped}</div><div class="label">跳过</div></div>
            <div class="card"><div class="number" style="color:#67c23a;">{http_duration:.0f}</div><div class="label">接口总耗时(ms)</div></div>
            <div class="card"><div class="number">{duration:.0f}</div><div class="label">执行总耗时(ms)</div></div>
        </div>

        <div class="progress-section">
            <h3 style="margin-bottom: 15px; color: #333;">执行进度</h3>
            <div class="progress-bar">
                <div class="progress-segment progress-success" style="width: {success_percent}%"></div>
                <div class="progress-segment progress-fail" style="width: {fail_percent}%"></div>
                <div class="progress-segment progress-skip" style="width: {skip_percent}%"></div>
            </div>
            <div class="progress-info">
                <span>成功率：{success_percent}%</span>
                <span>失败率：{fail_percent}%</span>
            </div>
        </div>''')

    hooks_result = suite_record.get("hooks_result") or {}
    hooks_html = generate_hooks_result_section(hooks_result)
    if hooks_html:
        html_parts.append(f'''
        <div class="section">
            <div class="section-header"><h2>🗄️ 数据工厂 Hooks</h2></div>
            {hooks_html}
        </div>''')

    # 计划报告：先展示套件/用例分组
    if report_type == "plan" and plan_items:
        html_parts.append('''
        <div class="section">
            <div class="section-header">
                <h2>📑 计划执行概览</h2>
            </div>
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                <thead><tr style="background:#fafafa;">
                    <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:60px;">#</th>
                    <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:80px;">类型</th>
                    <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #e8e8e8;">名称</th>
                    <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:80px;">状态</th>
                    <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:100px;">用例统计</th>
                    <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:80px;">耗时</th>
                </tr></thead>
                <tbody>''')
        for idx, item in enumerate(plan_items):
            item_type = item.get('item_type', 'suite')
            item_name = item.get('name', '未知')
            item_status = item.get('status', 'unknown')
            item_total = item.get('total', 0)
            item_success = item.get('success', 0)
            item_failed = item.get('failed', 0)
            item_duration = item.get('duration', 0)
            status_color = '#52c41a' if item_status == 'success' else '#ff4d4f'
            type_label = '套件' if item_type == 'suite' else '用例'
            html_parts.append(f'''<tr>
                <td style="padding:10px 12px;border-bottom:1px solid #e8e8e8;">{idx + 1}</td>
                <td style="padding:10px 12px;border-bottom:1px solid #e8e8e8;"><span style="background:#e6f7ff;color:#1890ff;padding:2px 8px;border-radius:4px;font-size:12px;">{type_label}</span></td>
                <td style="padding:10px 12px;border-bottom:1px solid #e8e8e8;font-weight:500;">{escape_html(item_name)}</td>
                <td style="padding:10px 12px;border-bottom:1px solid #e8e8e8;color:{status_color};font-weight:600;">{item_status}</td>
                <td style="padding:10px 12px;border-bottom:1px solid #e8e8e8;font-size:12px;">共{item_total} 成<span style="color:#52c41a;">{item_success}</span> 败<span style="color:#ff4d4f;">{item_failed}</span></td>
                <td style="padding:10px 12px;border-bottom:1px solid #e8e8e8;font-size:12px;">{item_duration:.0f}ms</td>
            </tr>''')
        html_parts.append('</tbody></table></div>')

    # 用例结果部分
    section_title = "📋 用例执行详情" if report_type == "suite" else "📋 套件/用例执行详情"
    html_parts.append(f'''
        <div class="section">
            <div class="section-header">
                <h2>{section_title}</h2>
                <div class="control-buttons">
                    <button class="btn btn-primary" onclick="expandAll()">📂 全部展开</button>
                    <button class="btn btn-default" onclick="collapseAll()">📁 全部收起</button>
                </div>
            </div>''')

    if report_type == "plan" and plan_items:
        for idx, plan_item in enumerate(plan_items):
            html_parts.append(generate_plan_item_html(idx, plan_item))
    elif case_results:
        for item in case_results:
            html_parts.append(generate_case_html(item))
    else:
        html_parts.append('<div class="no-logs">暂无执行数据</div>')

    html_parts.append('</div>')

    # 页脚和脚本
    html_parts.append(f'''
        <div class="footer">
            <p>BrickCore - 测试报告</p>
            <p>生成时间：{generate_time}</p>
        </div>
    </div>

    <script>
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

        function expandAll() {{
            document.querySelectorAll('.case-content').forEach(function(el) {{ el.classList.add('expanded'); }});
            document.querySelectorAll('.toggle-icon').forEach(function(el) {{ el.classList.remove('collapsed'); }});
        }}

        function collapseAll() {{
            document.querySelectorAll('.case-content').forEach(function(el) {{ el.classList.remove('expanded'); }});
            document.querySelectorAll('.toggle-icon').forEach(function(el) {{ el.classList.add('collapsed'); }});
        }}

        function switchTab(btn, panelId) {{
            const parent = btn.parentElement.parentElement;
            parent.querySelectorAll('.tab-item').forEach(function(t) {{ t.classList.remove('active'); }});
            parent.querySelectorAll('.tab-panel').forEach(function(p) {{ p.classList.remove('active'); }});
            btn.classList.add('active');
            parent.querySelector('#' + panelId).classList.add('active');
        }}
    </script>
</body>
</html>''')

    return ''.join(html_parts)


def generate_plan_item_html(idx: int, plan_item: Dict[str, Any]) -> str:
    """生成计划内单个套件/用例分组 HTML"""
    item_type = plan_item.get('item_type', 'suite')
    item_name = plan_item.get('name', '未知')
    item_status = plan_item.get('status', 'unknown')
    item_total = plan_item.get('total', 0)
    item_success = plan_item.get('success', 0)
    item_failed = plan_item.get('failed', 0)
    item_duration = plan_item.get('duration', 0) or 0
    item_error = plan_item.get('error')
    case_results = plan_item.get('case_results') or []

    status_color = '#52c41a' if item_status == 'success' else '#ff4d4f'
    status_text = '通过' if item_status == 'success' else ('失败' if item_status == 'failed' else item_status)
    type_label = '套件' if item_type == 'suite' else '用例'

    parts = [
        '<div class="plan-item-block">',
        '<div class="plan-item-header">',
        f'<span class="plan-item-order">#{idx + 1}</span>',
        f'<span class="plan-item-type">{type_label}</span>',
        f'<span class="plan-item-name">{escape_html(item_name)}</span>',
        f'<span class="plan-item-meta" style="color:{status_color};font-weight:600;">{status_text}</span>',
        f'<span class="plan-item-meta">共{item_total}个用例, 成功{item_success}, 失败{item_failed}</span>',
        f'<span class="plan-item-meta">{item_duration:.0f}ms</span>',
        '</div>',
    ]
    if item_error:
        parts.append(f'<div class="error-alert" style="margin:12px 16px 0;">{escape_html(str(item_error))}</div>')
    parts.append('<div class="plan-item-cases">')
    if case_results:
        for case_item in case_results:
            parts.append(generate_case_html(case_item))
    else:
        parts.append('<div class="no-logs">暂无用例数据</div>')
    parts.append('</div></div>')
    return ''.join(parts)


def generate_case_html(item: Dict[str, Any]) -> str:
    """生成单个用例 HTML"""
    case_name = item.get('case_name', '未知用例')
    status = item.get('status', 'pending')
    response_time = item.get('response_time')
    response_status = item.get('response_status')
    request_detail = item.get('request_detail') or {}

    status_map = {
        'success': ('success', '成功'),
        'failed': ('fail', '失败'),
        'pending': ('skip', '跳过'),
        'skip': ('skip', '跳过'),
        'running': ('running', '执行中'),
    }
    status_class, status_text = status_map.get(status, ('skip', status))

    method = (request_detail.get('method') or 'GET').upper()
    method_class = f"method-{method.lower()}"
    url_final = request_detail.get('url', {}).get('final', item.get('request_url', '-'))
    url_original = request_detail.get('url', {}).get('original', '-')

    req_headers = request_detail.get('headers', {}).get('final', item.get('request_headers', {}))
    req_params = request_detail.get('params', {}).get('final')
    req_body = item.get('request_body', '')
    if not req_body:
        req_body = request_detail.get('body', {}).get('final')
    if not req_body and request_detail.get('body_fields', {}).get('final'):
        req_body = request_detail.get('body_fields', {}).get('final')
    resp_headers = resolve_case_response_headers(item)
    resp_body = resolve_case_response_body(item)
    assertions = item.get('assertions', []) or item.get('assertions_result', [])
    extracted_vars = item.get('extracted_vars', {})
    extracted_meta = item.get('extracted_meta', {})
    extractor_results = item.get('extractor_results') or (request_detail.get('extractor_results') if isinstance(request_detail, dict) else []) or []
    error_msg = item.get('error_msg', '')

    html_parts = []
    html_parts.append(f'<div class="case-block">')
    html_parts.append(f'<div class="case-header {status_class}" onclick="toggleCase(this)">')
    html_parts.append(f'<div class="case-name-text"><span class="toggle-icon collapsed">▼</span><span>{case_name}</span></div>')
    html_parts.append(f'<div style="display:flex;align-items:center;gap:12px;">')
    http_time = resolve_http_response_time(item)
    if http_time is not None:
        html_parts.append(
            f'<span style="font-size:12px;color:#67c23a;font-weight:600;">接口 {http_time:.0f}ms</span>'
        )
    if response_time is not None:
        html_parts.append(f'<span style="font-size:12px;color:#909399;">总 {response_time:.0f}ms</span>')
    if response_status:
        html_parts.append(f'<span style="font-size:12px;color:#666;">HTTP {response_status}</span>')
    html_parts.append(f'<span class="case-status-badge case-status-{status_class}">{status_text}</span>')
    html_parts.append('</div></div>')
    html_parts.append('<div class="case-content">')

    # 错误信息
    if error_msg:
        html_parts.append(f'<div class="error-alert">❌ {escape_html(str(error_msg))}</div>')

    stage_timings = request_detail.get("stage_timings") if isinstance(request_detail, dict) else None
    if stage_timings and isinstance(stage_timings, dict) and any(
        v for k, v in stage_timings.items() if k != "total_ms" and v
    ):
        html_parts.append(generate_stage_timings_html(stage_timings, http_time, response_time))

    # 请求概览
    html_parts.append(f'''
        <div class="detail-block">
            <div class="detail-title">请求信息</div>
            <div class="detail-content">
                <div style="margin-bottom:8px;"><span class="http-method {method_class}">{method}</span><span>{escape_html(str(url_final))}</span></div>
                {f'<div style="font-size:12px;color:#999;margin-top:4px;">原始URL: {escape_html(str(url_original))}</div>' if url_original and url_original != url_final else ''}
            </div>
        </div>''')

    # Tab 切换：请求/响应/断言/变量
    tab_id_base = f"case_{item.get('record_id', id(item))}"
    html_parts.append(f'''
        <div class="detail-block">
            <div class="tab-nav">
                <div class="tab-item active" onclick="switchTab(this, '{tab_id_base}_req')">请求</div>
                <div class="tab-item" onclick="switchTab(this, '{tab_id_base}_resp')">响应</div>
                <div class="tab-item" onclick="switchTab(this, '{tab_id_base}_assert')">断言 ({len(assertions)})</div>
                <div class="tab-item" onclick="switchTab(this, '{tab_id_base}_vars')">提取变量 ({len(extracted_vars)})</div>
                <div class="tab-item" onclick="switchTab(this, '{tab_id_base}_extract')">提取详情 ({len(extractor_results)})</div>
                <div class="tab-item" onclick="switchTab(this, '{tab_id_base}_var_ref')">变量引用 ({len(request_detail.get('replacements', []))})</div>
            </div>
            <div id="{tab_id_base}_req" class="tab-panel active">
                {generate_json_block('请求 Headers', req_headers)}
                {generate_json_block('请求参数', req_params) if req_params else ''}
                {generate_raw_block('请求 Body', req_body)}
            </div>
            <div id="{tab_id_base}_resp" class="tab-panel">
                {generate_json_block('响应 Headers', resp_headers)}
                {generate_raw_block('响应 Body', resp_body)}
            </div>
            <div id="{tab_id_base}_assert" class="tab-panel">
                {generate_assertions_table(assertions)}
            </div>
            <div id="{tab_id_base}_vars" class="tab-panel">
                {generate_vars_grid(extracted_vars, extracted_meta)}
            </div>
            <div id="{tab_id_base}_extract" class="tab-panel">
                {generate_extractor_results_table(extractor_results)}
            </div>
            <div id="{tab_id_base}_var_ref" class="tab-panel">
                {generate_var_references_table(request_detail.get('replacements', []))}
            </div>
        </div>''')

    html_parts.append('</div></div>')
    return ''.join(html_parts)


def generate_stage_timings_html(
    stage_timings: Dict[str, Any],
    http_time: Optional[float] = None,
    total_time: Optional[float] = None,
) -> str:
    """生成阶段耗时分解 HTML"""
    label_map = {
        "load_case_ms": "加载用例/环境",
        "merge_vars_ms": "变量合并",
        "pre_script_ms": "前置脚本",
        "build_request_ms": "构建请求",
        "request_ms": "HTTP 请求",
        "assertion_ms": "断言执行",
        "schema_validate_ms": "Schema 校验",
        "extract_vars_ms": "变量提取",
        "post_script_ms": "后置脚本",
    }
    total = stage_timings.get("total_ms") or total_time or 1
    rows = []
    for key, value in stage_timings.items():
        if key == "total_ms" or not value:
            continue
        name = label_map.get(key, key)
        pct = min(100, round(float(value) / float(total) * 100)) if total else 0
        color = "#67c23a" if key == "request_ms" else "#409eff"
        if key in ("load_case_ms", "merge_vars_ms", "build_request_ms"):
            color = "#909399"
        rows.append(
            f'<tr><td style="padding:6px 10px;border-bottom:1px solid #eee;">{name}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;'
            f'font-weight:{"600" if key == "request_ms" else "normal"};color:{color};">{float(value):.1f}ms</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;">'
            f'<div style="background:#f0f0f0;border-radius:4px;height:8px;">'
            f'<div style="width:{pct}%;background:{color};height:8px;border-radius:4px;"></div></div></td></tr>'
        )
    http_label = f"{http_time:.1f}ms" if http_time is not None else "-"
    total_label = f"{float(total):.0f}ms" if total else "-"
    hint = (
        f'<p style="margin:8px 0 0;font-size:12px;color:#909399;">'
        f"接口耗时（{http_label}）为纯 HTTP 网络时间；用例总耗时（{total_label}）含断言、变量提取、脚本及重试等待。"
        f"</p>"
    )
    return (
        '<div class="detail-block" style="margin-bottom:12px;">'
        '<div class="detail-title">⏱️ 阶段耗时分解</div>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:8px;">'
        '<thead><tr style="background:#fafafa;">'
        '<th style="padding:8px 10px;text-align:left;border-bottom:1px solid #e8e8e8;width:140px;">阶段</th>'
        '<th style="padding:8px 10px;text-align:right;border-bottom:1px solid #e8e8e8;width:90px;">耗时</th>'
        '<th style="padding:8px 10px;text-align:left;border-bottom:1px solid #e8e8e8;">占比</th>'
        "</tr></thead><tbody>"
        + "".join(rows)
        + f'<tr style="font-weight:600;"><td style="padding:8px 10px;">总耗时</td>'
        f'<td style="padding:8px 10px;text-align:right;color:#409eff;">{float(total):.1f}ms</td><td></td></tr>'
        "</tbody></table>"
        + hint
        + "</div>"
    )


def generate_json_block(title: str, data: Any) -> str:
    """生成 JSON 展示块"""
    if data is None or data == '' or data == {} or data == []:
        return f'<div style="color:#999;font-size:12px;padding:8px 0;">无 {title}</div>'
    text = format_display_json(data)
    if not text:
        return f'<div style="color:#999;font-size:12px;padding:8px 0;">无 {title}</div>'
    return f'<div class="detail-title">{title}</div><pre class="detail-content">{escape_html(text)}</pre>'


def generate_raw_block(title: str, data: Any) -> str:
    """生成原始文本展示块"""
    if data is None or data == '':
        return f'<div style="color:#999;font-size:12px;padding:8px 0;">无 {title}</div>'
    text = format_display_json(data)
    if not text:
        return f'<div style="color:#999;font-size:12px;padding:8px 0;">无 {title}</div>'
    return f'<div class="detail-title">{title}</div><pre class="detail-content">{escape_html(text)}</pre>'


def _format_assertion_actual_for_report(actual: Any, assertion_type: str = "", max_len: int = 120) -> str:
    """断言实际值：表格内仅展示摘要，避免整段响应撑开报告。"""
    if actual is None:
        return "-"
    if isinstance(actual, (dict, list)):
        text = json.dumps(actual, ensure_ascii=False)
    else:
        text = str(actual)
    one_line = " ".join(text.split())
    if len(one_line) <= max_len:
        return escape_html(one_line)
    hint = f"…（共 {len(text)} 字符，完整内容见「响应Body」）"
    return escape_html(one_line[:max_len] + hint)


def generate_assertions_table(assertions: List[Dict]) -> str:
    """生成断言结果表格"""
    if not assertions:
        return '<div style="color:#999;font-size:12px;padding:8px 0;">无断言数据</div>'
    rows = []
    for a in assertions:
        passed = a.get('passed', a.get('result', False))
        result_class = 'assertion-pass' if passed else 'assertion-fail'
        result_text = '通过' if passed else '失败'
        atype = a.get('type', '-')
        target = a.get('target', a.get('name', '-'))
        if atype == 'db' and a.get('sql'):
            target = a.get('sql')
        actual_display = _format_assertion_actual_for_report(a.get('actual'), str(atype))
        rows.append(f'''
            <tr>
                <td>{escape_html(str(atype))}</td>
                <td>{escape_html(str(target))}</td>
                <td>{escape_html(str(a.get('operator', '-')))}</td>
                <td>{escape_html(str(a.get('expected', '-')))}</td>
                <td class="actual-cell">{actual_display}</td>
                <td class="{result_class}">{result_text}</td>
            </tr>''')
    return f'''<table class="assertion-table">
        <tr><th>类型</th><th>目标/SQL</th><th>操作</th><th>预期值</th><th>实际值</th><th>结果</th></tr>
        { "".join(rows) }
    </table>'''


def generate_hooks_result_section(hooks_result: Dict[str, Any]) -> str:
    """生成 setup/teardown/库断言 hooks 报告区块"""
    if not hooks_result or not any(hooks_result.get(k) for k in ("setup", "teardown", "db_assertions")):
        return ""

    parts = []
    success = hooks_result.get("success", True)
    status_html = (
        '<span style="color:#52c41a;font-weight:600;">全部通过</span>'
        if success else '<span style="color:#f5222d;font-weight:600;">存在失败</span>'
    )
    parts.append(f'<p style="margin-bottom:12px;">Hooks 总状态：{status_html}</p>')

    for title, key in (("前置 SQL (Setup)", "setup"), ("后置 SQL (Teardown)", "teardown")):
        logs = hooks_result.get(key) or []
        if not logs:
            continue
        rows = []
        for log in logs:
            ok = log.get("success", True)
            cls = "assertion-pass" if ok else "assertion-fail"
            rows.append(
                f'<tr><td>{escape_html(str(log.get("template_name", log.get("template_id", "-"))))}</td>'
                f'<td class="hooks-log">{escape_html(str(log.get("sql", "-")))}</td>'
                f'<td class="{cls}">{"通过" if ok else "失败"}</td>'
                f'<td>{escape_html(str(log.get("message", log.get("error", ""))))}</td></tr>'
            )
        parts.append(f'''<div class="hooks-block"><h4>{title}</h4>
            <table class="assertion-table">
            <tr><th>模板</th><th>SQL</th><th>结果</th><th>说明</th></tr>{"".join(rows)}</table></div>''')

    db_results = hooks_result.get("db_assertions") or []
    if db_results:
        parts.append(f'<div class="hooks-block"><h4>套件级数据库断言</h4>{generate_assertions_table(db_results)}</div>')

    return "".join(parts)


def generate_extractor_results_table(results: List[Dict]) -> str:
    """生成变量提取规则执行详情表"""
    if not results:
        return '<div style="color:#999;font-size:12px;padding:8px 0;">无提取规则或未记录详情</div>'
    rows = []
    for r in results:
        ok = r.get('success')
        status_html = (
            '<span style="color:#52c41a;font-weight:600;">成功</span>'
            if ok else '<span style="color:#f5222d;font-weight:600;">失败</span>'
        )
        val = r.get('value') if ok else (r.get('error') or '—')
        rows.append(f'''<tr>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;font-weight:600;">{escape_html(str(r.get('name', '')))}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;">{escape_html(str(r.get('source', '')))}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;word-break:break-all;">{escape_html(str(r.get('path', '')))}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;">{status_html}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;word-break:break-all;">{escape_html(str(val))}</td>
        </tr>''')
    return f'''<table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr style="background:#fafafa;">
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;">变量名</th>
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:70px;">来源</th>
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;">路径</th>
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:60px;">状态</th>
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;">值/说明</th>
        </tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table>'''


def generate_vars_grid(vars_dict: Dict[str, Any], extracted_meta: Dict = None) -> str:
    """生成变量提取网格（带引用追踪）"""
    if not vars_dict:
        return '<div style="color:#999;font-size:12px;padding:8px 0;">无提取变量</div>'
    
    rows = []
    for k, v in vars_dict.items():
        meta = (extracted_meta or {}).get(k, {})
        used_by = meta.get('used_by', [])
        used_by_html = ''
        if used_by:
            names = [escape_html(u['case_name']) for u in used_by]
            used_by_html = f'<span style="color:#52c41a;font-size:11px;">被引用: {"、".join(names)}</span>'
        else:
            used_by_html = '<span style="color:#999;font-size:11px;">未被引用</span>'
        
        rows.append(f'''<tr>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;font-weight:600;color:#1890ff;font-size:12px;">{escape_html(str(k))}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;word-break:break-all;">{escape_html(str(v))}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;width:160px;">{used_by_html}</td>
        </tr>''')
    
    return f'''<table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr style="background:#fafafa;">
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:140px;">变量名</th>
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;">值</th>
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:180px;">被引用</th>
        </tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table>'''


def generate_var_references_table(replacements: List[Dict]) -> str:
    """生成变量引用追踪表格"""
    if not replacements:
        return '<div style="color:#999;font-size:12px;padding:8px 0;">无变量引用</div>'
    
    rows = []
    for rep in replacements:
        var_name = escape_html(str(rep.get('key', '-')))
        original = escape_html(str(rep.get('original', '-')))
        replaced = escape_html(str(rep.get('replaced', '-')))
        path = escape_html(str(rep.get('path', '-')))
        source_case = rep.get('source_case_name')
        
        if source_case:
            source_html = f'<span style="color:#fa8c16;font-size:11px;font-weight:600;">↳ {escape_html(source_case)}</span>'
        else:
            source_html = f'<span style="color:#999;font-size:11px;">环境变量</span>'
        
        rows.append(f'''<tr>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;font-weight:600;color:#1890ff;font-size:12px;">{var_name}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;">{source_html}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;"><code style="background:#eee;padding:2px 4px;border-radius:3px;font-size:11px;color:#999;text-decoration:line-through;">{original}</code></td>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;"><code style="background:#e6f7ff;padding:2px 4px;border-radius:3px;font-size:11px;color:#1890ff;">{replaced}</code></td>
            <td style="padding:8px 12px;border-bottom:1px solid #e8e8e8;font-size:12px;color:#666;">{path}</td>
        </tr>''')
    
    return f'''<table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr style="background:#fafafa;">
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:100px;">变量名</th>
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:140px;">来源用例</th>
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;">原始值</th>
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;">替换后</th>
            <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #e8e8e8;width:80px;">位置</th>
        </tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table>'''


def escape_html(text: str) -> str:
    """HTML 转义"""
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def format_time(time_val) -> str:
    """格式化时间"""
    if not time_val:
        return '-'
    if isinstance(time_val, datetime):
        return time_val.strftime('%Y-%m-%d %H:%M:%S')
    return str(time_val)
