"""性能测试执行记录 API"""
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, status, Body, Depends, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.models.perf import PerfRecord, PerfScene
from app.core.auth import require_permissions
from app.core.notification import NotificationService
from app.core.permissions import PERF_RECORD_VIEW
from app.routers.perf.report_utils import build_report_payload

router = APIRouter(prefix="/records", tags=["性能测试记录"])


@router.get("", summary="执行记录列表")
async def get_records(
    project_id: int = Query(..., description="项目ID"),
    status: Optional[str] = Query(None, description="状态筛选"),
    scene_name: Optional[str] = Query(None, description="场景名称关键字"),
    start_date: Optional[str] = Query(None, description="开始日期(YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期(YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=5000)
):
    """获取性能测试执行记录列表（支持按场景名称、状态、时间范围筛选）"""
    query = PerfRecord.filter(project_id=project_id)

    if status:
        query = query.filter(status=status)

    if scene_name:
        # 通过 scene_id 关联查询场景名称
        scenes = await PerfScene.filter(project_id=project_id, name__contains=scene_name, is_del=False).all()
        scene_ids = [s.id for s in scenes]
        if scene_ids:
            query = query.filter(scene_id__in=scene_ids)
        else:
            # 无匹配场景，返回空结果
            return {"data": [], "total": 0, "page": page, "size": size}

    if start_date:
        query = query.filter(started_at__gte=start_date)
    if end_date:
        query = query.filter(started_at__lte=end_date)

    total = await query.count()
    records = await query.order_by("-id").offset((page - 1) * size).limit(size).all()
    
    result = []
    for record in records:
        scene = await record.scene
        result.append({
            "id": record.id,
            "scene_id": record.scene_id,
            "scene_name": scene.name if scene else "未知场景",
            "project_id": record.project_id,
            "status": record.status,
            "trigger_type": record.trigger_type,
            "config_snapshot": record.config_snapshot,
            "mode": record.config_snapshot.get("mode", "fixed") if record.config_snapshot else "fixed",
            "total_requests": record.total_requests,
            "success_count": record.success_count,
            "fail_count": record.fail_count,
            "qps": record.qps,
            "avg_response_time": record.avg_response_time,
            "error_rate": record.error_rate,
            "median_response_time": record.median_response_time,
            "p90_response_time": record.p90_response_time,
            "std_dev_response_time": record.std_dev_response_time,
            "received_kb_per_sec": record.received_kb_per_sec,
            "sent_kb_per_sec": record.sent_kb_per_sec,
            "duration": record.duration,
            "started_at": record.started_at.strftime("%Y-%m-%d %H:%M:%S") if record.started_at else None,
            "ended_at": record.ended_at.strftime("%Y-%m-%d %H:%M:%S") if record.ended_at else None,
            "run_by": record.run_by
        })
    
    return {"data": result, "total": total, "page": page, "size": size}


@router.get("/{record_id}", summary="执行记录详情")
async def get_record_detail(record_id: int):
    """获取性能测试执行记录详情"""
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    scene = await record.scene
    previous = await PerfRecord.filter(
        scene_id=record.scene_id,
        id__lt=record.id,
        status__in=["success", "failed", "stopped"],
    ).order_by("-id").first()

    return build_report_payload(record, scene, previous)


@router.post("/batch-delete", summary="批量删除执行记录", status_code=status.HTTP_204_NO_CONTENT)
async def batch_delete_records(record_ids: List[int]):
    """批量删除性能测试执行记录"""
    if not record_ids:
        raise HTTPException(status_code=400, detail="请选择要删除的记录")
    
    deleted = 0
    for rid in record_ids:
        record = await PerfRecord.get_or_none(id=rid)
        if record:
            await record.delete()
            deleted += 1
    
    return None


@router.post("/{record_id}/send-report", summary="发送性能测试报告邮件", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permissions(PERF_RECORD_VIEW))])
async def send_perf_report(record_id: int):
    """手动发送性能测试报告邮件"""
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    try:
        await NotificationService.send_perf_report(
            project_id=record.project_id,
            record_id=record_id,
        )
        return {"detail": "报告邮件已发送"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {e}")


@router.get("/{record_id}/export", summary="导出性能测试报告(HTML)")
async def export_perf_report(record_id: int):
    """导出性能测试报告为 HTML"""
    record = await PerfRecord.get_or_none(id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    
    scene = await record.scene
    html_content = _generate_perf_html_report(record, scene)
    filename = f"perf_report_{record_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    return HTMLResponse(
        content=html_content,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/{record_id}/report", summary="执行报告数据")
async def get_record_report(record_id: int):
    """获取性能测试报告数据（用于前端 echarts）"""
    return await get_record_detail(record_id)


def _generate_perf_html_report(record: PerfRecord, scene) -> str:
    """生成性能测试 HTML 报告"""
    scene_name = scene.name if scene else "未知场景"
    mode = record.config_snapshot.get("mode", "fixed") if record.config_snapshot else "fixed"
    mode_label = {"fixed": "固定模式", "loop": "循环模式", "stepping": "梯度模式"}.get(mode, mode)
    dist_mode = record.config_snapshot.get("distribution_mode", "weighted_random") if record.config_snapshot else "weighted_random"
    dist_label = "固定比例" if dist_mode == "fixed_ratio" else "随机权重"
    
    status_class = "status-success" if record.status == "success" else "status-fail" if record.status == "failed" else "status-running"
    status_text = {"success": "成功", "failed": "失败", "running": "执行中", "stopped": "已停止", "pending": "等待中"}.get(record.status, record.status)
    
    generate_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    started = record.started_at.strftime('%Y-%m-%d %H:%M:%S') if record.started_at else '-'
    ended = record.ended_at.strftime('%Y-%m-%d %H:%M:%S') if record.ended_at else '-'
    
    # 构建趋势数据表格行
    ts_rows = ""
    for point in (record.time_series_data or [])[:60]:  # 最多显示60个时间点
        ts_rows += f"""
        <tr>
            <td>{point.get('timestamp', 0)}s</td>
            <td>{point.get('qps', 0)}</td>
            <td>{point.get('avg_rt', 0)} ms</td>
            <td>{point.get('error_rate', 0)}%</td>
            <td>{point.get('total_req', 0)}</td>
        </tr>"""
    
    if not ts_rows:
        ts_rows = '<tr><td colspan="5" style="text-align:center;color:#999;">无趋势数据</td></tr>'
    
    # 构建接口维度表格
    case_rows = ""
    for cid, agg in (record.case_aggregations or {}).items():
        case_rows += f"""
        <tr>
            <td>{agg.get('name', '未知')}</td>
            <td>{agg.get('total', 0)}</td>
            <td>{agg.get('success', 0)}</td>
            <td>{agg.get('fail', 0)}</td>
            <td style="color:{'#f56c6c' if agg.get('error_rate', 0) > 5 else '#67c23a'}">{agg.get('error_rate', 0)}%</td>
            <td>{agg.get('avg_rt', 0)}</td>
            <td>{agg.get('min_rt', 0)}</td>
            <td>{agg.get('max_rt', 0)}</td>
            <td>{agg.get('median_rt', 0)}</td>
            <td>{agg.get('p90_rt', 0)}</td>
            <td>{agg.get('p95_rt', 0)}</td>
            <td>{agg.get('p99_rt', 0)}</td>
            <td>{agg.get('std_dev', 0)}</td>
        </tr>"""
    
    if not case_rows:
        case_rows = '<tr><td colspan="13" style="text-align:center;color:#999;">无接口数据</td></tr>'
    
    # 构建错误分类表格
    err_type_rows = ""
    bd = record.error_breakdown or {}
    by_type = bd.get("by_type", {})
    total_fail = record.fail_count or 1
    type_map = {
        "timeout": "请求超时", "connection_error": "连接错误", "network_error": "网络错误",
        "server_error": "服务端错误(5xx)", "client_error": "客户端错误(4xx)",
        "assertion_failed": "断言失败", "unknown": "未知错误"
    }
    for etype, count in sorted(by_type.items(), key=lambda x: -x[1]):
        pct = round(count / total_fail * 100, 1) if total_fail > 0 else 0
        err_type_rows += f"""
        <tr>
            <td>{type_map.get(etype, etype)}</td>
            <td>{count}</td>
            <td>{pct}%</td>
        </tr>"""
    
    if not err_type_rows:
        err_type_rows = '<tr><td colspan="3" style="text-align:center;color:#999;">无错误数据</td></tr>'
    
    # 失败采样
    sample_rows = ""
    samples = bd.get("failed_samples", [])[:50]
    for idx, s in enumerate(samples, 1):
        sample_rows += f"""
        <tr>
            <td>{idx}</td>
            <td>{s.get('case_name', '未知')}</td>
            <td>{s.get('status_code', 0)}</td>
            <td>{round(s.get('response_time', 0), 2)} ms</td>
            <td style="color:#f56c6c;max-width:400px;overflow:hidden;text-overflow:ellipsis;">{s.get('error_msg', '') or '-'}</td>
        </tr>"""
    
    if not sample_rows:
        sample_rows = '<tr><td colspan="5" style="text-align:center;color:#999;">无失败采样</td></tr>'
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>性能测试报告 - {scene_name}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; background:#f0f2f5; color:#333; line-height:1.6; }}
.container {{ max-width:1400px; margin:0 auto; padding:20px; }}
.header {{ background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); color:white; padding:30px; border-radius:12px; margin-bottom:20px; box-shadow:0 4px 12px rgba(0,0,0,0.1); }}
.header h1 {{ font-size:28px; margin-bottom:10px; }}
.header .meta {{ opacity:0.9; font-size:14px; margin-top:8px; }}
.status-badge {{ display:inline-block; padding:4px 14px; border-radius:12px; font-size:13px; font-weight:bold; }}
.status-success {{ background:#52c41a; color:white; }}
.status-fail {{ background:#ff4d4f; color:white; }}
.status-running {{ background:#1890ff; color:white; }}
.section {{ background:white; border-radius:10px; padding:24px; margin-bottom:20px; box-shadow:0 2px 8px rgba(0,0,0,0.06); }}
.section h2 {{ font-size:18px; margin-bottom:16px; color:#1a1a1a; border-left:4px solid #667eea; padding-left:12px; }}
.metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:20px; }}
.metric-card {{ background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); border-radius:10px; padding:18px; color:white; text-align:center; }}
.metric-card.success {{ background:linear-gradient(135deg,#11998e 0%,#38ef7d 100%); }}
.metric-card.warning {{ background:linear-gradient(135deg,#f093fb 0%,#f5576c 100%); }}
.metric-card.info {{ background:linear-gradient(135deg,#4facfe 0%,#00f2fe 100%); }}
.metric-card.danger {{ background:linear-gradient(135deg,#ff416c 0%,#ff4b2b 100%); }}
.metric-value {{ font-size:24px; font-weight:700; }}
.metric-label {{ font-size:12px; margin-top:4px; opacity:0.9; }}
.mini-metrics {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; }}
.mini {{ padding:14px; }}
.mini .metric-value {{ font-size:16px; }}
.mini .metric-label {{ font-size:11px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ padding:10px 12px; text-align:center; border-bottom:1px solid #f0f0f0; }}
th {{ background:#f8f9fa; font-weight:600; color:#666; }}
tr:hover {{ background:#fafafa; }}
.config-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
.config-item {{ background:#f8f9fa; padding:12px 16px; border-radius:8px; }}
.config-item .label {{ font-size:12px; color:#999; margin-bottom:4px; }}
.config-item .value {{ font-size:15px; font-weight:600; color:#333; }}
.footer {{ text-align:center; color:#999; font-size:12px; margin-top:30px; padding:20px; }}
@media print {{ body {{ background:white; }} .section {{ box-shadow:none; border:1px solid #eee; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📈 性能测试报告 — {scene_name}</h1>
    <div class="meta">
      <span class="status-badge {status_class}">{status_text}</span>
      &nbsp;&nbsp;模式：{mode_label} &nbsp;|&nbsp; 分配：{dist_label}
      &nbsp;|&nbsp; 执行人：{record.run_by or '-'} &nbsp;|&nbsp; 生成时间：{generate_time}
    </div>
    <div class="meta">开始：{started} &nbsp;|&nbsp; 结束：{ended} &nbsp;|&nbsp; 时长：{round(record.duration, 2)}s</div>
  </div>

  <div class="section">
    <h2>核心指标</h2>
    <div class="metrics">
      <div class="metric-card"><div class="metric-value">{round(record.qps, 2)}</div><div class="metric-label">QPS</div></div>
      <div class="metric-card success"><div class="metric-value">{round(record.avg_response_time, 2)} ms</div><div class="metric-label">平均响应时间</div></div>
      <div class="metric-card warning"><div class="metric-value">{round(record.p95_response_time, 2)} ms</div><div class="metric-label">P95 响应时间</div></div>
      <div class="metric-card {'danger' if record.error_rate > 5 else 'info'}"><div class="metric-value">{round(record.error_rate, 2)}%</div><div class="metric-label">错误率</div></div>
    </div>
    <div class="mini-metrics">
      <div class="metric-card mini"><div class="metric-value">{record.total_requests}</div><div class="metric-label">总请求</div></div>
      <div class="metric-card mini"><div class="metric-value">{record.success_count}</div><div class="metric-label">成功</div></div>
      <div class="metric-card mini"><div class="metric-value">{record.fail_count}</div><div class="metric-label">失败</div></div>
      <div class="metric-card mini"><div class="metric-value">{round(record.min_response_time, 2)} ms</div><div class="metric-label">Min RT</div></div>
      <div class="metric-card mini"><div class="metric-value">{round(record.max_response_time, 2)} ms</div><div class="metric-label">Max RT</div></div>
      <div class="metric-card mini"><div class="metric-value">{round(record.median_response_time, 2)} ms</div><div class="metric-label">Median RT</div></div>
      <div class="metric-card mini"><div class="metric-value">{round(record.p90_response_time, 2)} ms</div><div class="metric-label">P90 RT</div></div>
      <div class="metric-card mini"><div class="metric-value">{round(record.p99_response_time, 2)} ms</div><div class="metric-label">P99 RT</div></div>
      <div class="metric-card mini"><div class="metric-value">{round(record.std_dev_response_time, 2)} ms</div><div class="metric-label">StdDev RT</div></div>
      <div class="metric-card mini"><div class="metric-value">{round(record.received_kb_per_sec, 2)} KB/s</div><div class="metric-label">Received</div></div>
      <div class="metric-card mini"><div class="metric-value">{round(record.sent_kb_per_sec, 2)} KB/s</div><div class="metric-label">Sent</div></div>
      <div class="metric-card mini"><div class="metric-value">{round(record.duration, 2)} s</div><div class="metric-label">执行时长</div></div>
    </div>
  </div>

  <div class="section">
    <h2>配置信息</h2>
    <div class="config-grid">
      <div class="config-item"><div class="label">并发用户数</div><div class="value">{record.config_snapshot.get('concurrent_users', '-') if record.config_snapshot else '-'}</div></div>
      <div class="config-item"><div class="label">Ramp-up</div><div class="value">{record.config_snapshot.get('ramp_up_seconds', 0)}s</div></div>
      <div class="config-item"><div class="label">目标Host</div><div class="value">{record.config_snapshot.get('target_host', '默认') if record.config_snapshot else '默认'}</div></div>
      <div class="config-item"><div class="label">持续时间/循环</div><div class="value">{record.config_snapshot.get('duration_seconds', record.config_snapshot.get('loop_count', '-')) if record.config_snapshot else '-'}{'s' if mode == 'fixed' else '次' if mode == 'loop' else ''}</div></div>
      <div class="config-item"><div class="label">分配模式</div><div class="value">{dist_label}</div></div>
    </div>
  </div>

  <div class="section">
    <h2>性能趋势（每秒采样）</h2>
    <table>
      <thead><tr><th>时间(s)</th><th>QPS</th><th>平均RT(ms)</th><th>错误率(%)</th><th>累计请求</th></tr></thead>
      <tbody>{ts_rows}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>接口维度详情</h2>
    <table>
      <thead><tr><th>用例名称</th><th>总请求</th><th>成功</th><th>失败</th><th>错误率</th><th>Avg</th><th>Min</th><th>Max</th><th>Median</th><th>P90</th><th>P95</th><th>P99</th><th>StdDev</th></tr></thead>
      <tbody>{case_rows}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>错误分类统计</h2>
    <table>
      <thead><tr><th>错误类型</th><th>次数</th><th>占比</th></tr></thead>
      <tbody>{err_type_rows}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>失败请求采样（前{len(samples)}条）</h2>
    <table>
      <thead><tr><th>#</th><th>用例名称</th><th>状态码</th><th>响应时间</th><th>错误详情</th></tr></thead>
      <tbody>{sample_rows}</tbody>
    </table>
  </div>

  <div class="footer">BrickCore 性能测试报告 &nbsp;|&nbsp; 生成时间：{generate_time}</div>
</div>
</body>
</html>'''
    return html


class CompareRequest(BaseModel):
    record_ids: List[int]


@router.post("/compare", summary="报告对比")
async def compare_records(req: CompareRequest):
    """选择两次执行记录，并排对比 QPS/RT/错误率变化"""
    record_ids = req.record_ids
    if len(record_ids) < 2:
        raise HTTPException(status_code=400, detail="请至少选择两条记录进行对比")

    records = await PerfRecord.filter(id__in=record_ids).all()
    if len(records) < 2:
        raise HTTPException(status_code=404, detail="记录不存在")

    result = []
    for r in records:
        scene = await r.scene
        result.append({
            "id": r.id,
            "scene_name": scene.name if scene else "未知场景",
            "status": r.status,
            "started_at": r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else None,
            "ended_at": r.ended_at.strftime("%Y-%m-%d %H:%M:%S") if r.ended_at else None,
            "duration": r.duration,
            "total_requests": r.total_requests,
            "qps": r.qps,
            "avg_response_time": r.avg_response_time,
            "min_response_time": r.min_response_time,
            "max_response_time": r.max_response_time,
            "median_response_time": r.median_response_time,
            "p90_response_time": r.p90_response_time,
            "p95_response_time": r.p95_response_time,
            "p99_response_time": r.p99_response_time,
            "error_rate": r.error_rate,
            "time_series_data": r.time_series_data,
            "case_aggregations": r.case_aggregations,
            "config_snapshot": r.config_snapshot
        })

    # 计算变化百分比（以后一条为基准对比前一条）
    if len(result) == 2:
        a, b = result[0], result[1]
        changes = {}
        for key in ["qps", "avg_response_time", "error_rate", "total_requests"]:
            va = a.get(key, 0) or 0
            vb = b.get(key, 0) or 0
            if va == 0:
                changes[key] = {"from": va, "to": vb, "change_pct": 0 if vb == 0 else 100}
            else:
                changes[key] = {"from": va, "to": vb, "change_pct": round((vb - va) / va * 100, 2)}
        return {"records": result, "changes": changes}

    return {"records": result}
