"""压测导出 HTML 共用汇报型主题（单次 / 对比 / 合订）。"""
from __future__ import annotations

import re
from html import escape
from typing import Any, Optional


def h(v: Any) -> str:
    return escape("" if v is None else str(v))


def report_css() -> str:
    return """<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif; background:#f5f7fa; color:#333; line-height:1.6; }
.container { max-width:1100px; margin:0 auto; padding:24px; }
.header { background:linear-gradient(135deg,#1a73e8,#0d47a1); color:#fff; padding:40px 48px; border-radius:12px; margin-bottom:28px; }
.header h1 { font-size:26px; margin-bottom:8px; }
.header .meta { opacity:.85; font-size:14px; }
.header .meta span { margin-right:20px; }
.section { background:#fff; border-radius:10px; padding:28px 32px; margin-bottom:22px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
.section h2 { font-size:18px; color:#1a73e8; margin-bottom:14px; padding-bottom:8px; border-bottom:2px solid #e8edf3; }
.section h3 { font-size:15px; color:#444; margin:18px 0 10px; }
.summary-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin-bottom:8px; }
.summary-card { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:14px 16px; text-align:center; }
.summary-card .label { font-size:12px; color:#666; margin-bottom:4px; }
.summary-card .value { font-size:22px; font-weight:700; color:#1a73e8; }
.summary-card .value.danger { color:#e53e3e; }
.summary-card .value.success { color:#38a169; }
.summary-card .value.warning { color:#dd6b20; }
.summary-card .note { font-size:12px; color:#64748b; margin-top:8px; text-align:left; line-height:1.45; }
table { width:100%; border-collapse:collapse; margin-top:8px; font-size:13px; }
th { background:#f1f5f9; color:#475569; font-weight:600; text-align:left; padding:10px 12px; border-bottom:2px solid #e2e8f0; }
td { padding:10px 12px; border-bottom:1px solid #f0f0f0; }
tr:hover td { background:#f8fafc; }
.tag { display:inline-block; padding:2px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.tag-green { background:#c6f6d5; color:#22543d; }
.tag-red { background:#fed7d7; color:#742a2a; }
.tag-orange { background:#feebc8; color:#7b341e; }
.tag-blue { background:#bee3f8; color:#2a4365; }
.status-badge { display:inline-block; padding:4px 12px; border-radius:6px; font-size:12px; font-weight:600; }
.status-success { background:#c6f6d5; color:#22543d; }
.status-fail { background:#fed7d7; color:#742a2a; }
.status-running { background:#bee3f8; color:#2a4365; }
.conclusion-box { background:#f0fdf4; border-left:4px solid #38a169; padding:14px 18px; border-radius:0 8px 8px 0; margin-top:12px; }
.conclusion-box.warn { background:#fffbeb; border-left-color:#dd6b20; }
.conclusion-box ul { margin:8px 0 0 18px; }
.conclusion-box p { margin-bottom:8px; }
.conclusion-box p:last-child { margin-bottom:0; }
.chart-bar { display:flex; align-items:center; margin:6px 0; }
.chart-bar .bar-label { width:160px; font-size:13px; color:#555; flex-shrink:0; }
.chart-bar .bar-track { flex:1; background:#edf2f7; border-radius:4px; height:22px; overflow:hidden; }
.chart-bar .bar-fill { height:100%; border-radius:4px; display:flex; align-items:center; padding-left:8px; font-size:12px; color:#fff; font-weight:600; min-width:40px; }
.bar-fill.blue { background:linear-gradient(90deg,#4299e1,#3182ce); }
.bar-fill.orange { background:linear-gradient(90deg,#ed8936,#dd6b20); }
.bar-fill.red { background:linear-gradient(90deg,#fc8181,#e53e3e); }
.bar-fill.green { background:linear-gradient(90deg,#68d391,#38a169); }
.config-table td:first-child { width:160px; color:#666; }
.kv-table td { vertical-align:top; }
.metric-note-cell { font-size:12px; color:#64748b; max-width:280px; }
.case-note { font-size:12px; color:#64748b; margin-top:4px; }
.chart-box { width:100%; height:420px; }
.chart-toolbar { display:flex; justify-content:flex-end; align-items:center; gap:8px; margin:0 0 6px; }
.chart-enlarge-btn {
  border:1px solid #cbd5e1; background:#fff; color:#2563eb; font-size:12px;
  padding:4px 10px; border-radius:6px; cursor:pointer; line-height:1.4;
}
.chart-enlarge-btn:hover { background:#eff6ff; border-color:#93c5fd; }
.chart-zoom-modal {
  display:none; position:fixed; inset:0; z-index:9999; background:rgba(15,23,42,.45);
  align-items:center; justify-content:center; padding:24px;
}
.chart-zoom-modal.is-open { display:flex; }
.chart-zoom-panel {
  width:min(1200px,96vw); max-height:92vh; background:#fff; border-radius:12px;
  box-shadow:0 20px 50px rgba(15,23,42,.25); padding:16px 18px 18px; display:flex; flex-direction:column;
}
.chart-zoom-head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:8px; }
.chart-zoom-title { font-size:16px; font-weight:600; color:#1e293b; }
.chart-zoom-close {
  border:none; background:#f1f5f9; color:#475569; width:32px; height:32px; border-radius:8px;
  cursor:pointer; font-size:18px; line-height:1;
}
.chart-zoom-close:hover { background:#e2e8f0; }
.chart-zoom-box { width:100%; height:min(78vh,720px); }
.chart-hint { font-size:12px; color:#999; margin-top:8px; text-align:center; }
.chart-ai-note { font-size:13px; color:#334155; background:#f8fafc; border-left:3px solid #3b82f6; padding:10px 14px; margin:0 0 12px; line-height:1.55; }
.glossary-table td:first-child { width:160px; font-weight:600; color:#334155; white-space:nowrap; }
.glossary-table td { font-size:13px; color:#475569; vertical-align:top; line-height:1.5; }
.compare-intro { font-size:13px; color:#475569; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px 14px; margin-bottom:14px; line-height:1.55; }
.overview-panels { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
.overview-panel { border:1px solid #e2e8f0; border-radius:10px; padding:14px 16px; background:#fff; }
.overview-panel.is-ref { border-color:#fcd34d; background:linear-gradient(180deg,#fffbeb 0%,#fff 48px); }
.overview-panel.is-cmp { border-color:#93c5fd; background:linear-gradient(180deg,#eff6ff 0%,#fff 48px); }
.steps-stack { display:flex; flex-direction:column; gap:4px; }
.steps-stack .steps-head { font-weight:600; color:#334155; margin-bottom:2px; }
.steps-stack .step-line {
  font-size:12px; color:#475569; background:#f8fafc; border:1px solid #eef2f7;
  border-radius:6px; padding:4px 8px; line-height:1.4;
}
.stage-summary-block { margin-bottom:14px; }
.stage-summary-label {
  font-size:13px; font-weight:600; color:#334155; margin-bottom:8px;
  padding:8px 12px; background:#f1f5f9; border-radius:8px;
}
.stage-summary-list { display:flex; flex-direction:column; gap:8px; }
.stage-summary-card {
  border:1px solid #e2e8f0; border-radius:10px; padding:12px 14px;
  background:#fff; border-left:4px solid #94a3b8;
}
.stage-summary-card.better { border-left-color:#22c55e; background:#f0fdf4; }
.stage-summary-card.worse { border-left-color:#ef4444; background:#fef2f2; }
.stage-summary-card.flat { border-left-color:#94a3b8; background:#f8fafc; }
.stage-summary-card .stage-sum-title {
  font-size:13px; font-weight:700; color:#1e293b; margin-bottom:8px;
  display:flex; align-items:center; gap:8px; flex-wrap:wrap;
}
.stage-summary-card .stage-sum-title .stage-idx {
  display:inline-flex; align-items:center; justify-content:center;
  min-width:22px; height:22px; padding:0 6px; border-radius:999px;
  background:#1a73e8; color:#fff; font-size:11px; font-weight:700;
}
.stage-summary-card .stage-sum-line {
  font-size:12.5px; color:#334155; line-height:1.55; margin:4px 0;
  display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 8px;
}
.stage-summary-card .stage-sum-meta { color:#64748b; }
.stage-summary-card .stage-sum-deltas {
  margin-top:8px; padding-top:8px; border-top:1px dashed #e2e8f0;
  display:flex; flex-wrap:wrap; gap:8px;
}
.stage-summary-card .delta-chip {
  display:inline-flex; align-items:center; gap:4px;
  font-size:12px; font-weight:600; padding:3px 10px; border-radius:999px;
  background:#fff; border:1px solid #e2e8f0;
}
.stage-detail-head {
  display:flex; flex-wrap:wrap; align-items:center; gap:8px;
  margin:18px 0 10px; padding:10px 12px; border-radius:8px;
  background:#f8fafc; border:1px solid #e2e8f0;
}
.stage-detail-head.better { background:#f0fdf4; border-color:#bbf7d0; }
.stage-detail-head.worse { background:#fef2f2; border-color:#fecaca; }
.stage-detail-head .stage-detail-title { font-size:14px; font-weight:700; color:#1e293b; margin:0; }
.stage-table thead th.round-col-ref { background:#fff7ed; color:#9a3412; }
.stage-table thead th.round-col-cmp { background:#eff6ff; color:#1e40af; }
@media (max-width:768px) { .overview-panels { grid-template-columns:1fr; } }
.delta-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin:12px 0 6px; }
.delta-card { background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:14px 12px; text-align:center; }
.delta-card .delta-label { font-size:12px; color:#64748b; margin-bottom:6px; }
.delta-card .delta-pct { font-size:26px; font-weight:700; line-height:1.2; }
.delta-card .delta-vals { font-size:12px; color:#64748b; margin-top:8px; line-height:1.45; }
.delta-card.better { border-color:#86efac; background:#f0fdf4; }
.delta-card.worse { border-color:#fca5a5; background:#fef2f2; }
.delta-card.flat { border-color:#e2e8f0; background:#f8fafc; }
.delta-card .delta-pct.better { color:#15803d; }
.delta-card .delta-pct.worse { color:#b91c1c; }
.delta-card .delta-pct.flat { color:#64748b; }
.pct-better { color:#15803d !important; font-weight:600; }
.pct-worse { color:#b91c1c !important; font-weight:600; }
.pct-flat { color:#64748b !important; font-weight:600; }
.round-ref { background:#fef3c7; color:#92400e; }
.round-cmp { background:#dbeafe; color:#1e40af; }
.unit { font-size:12px; font-weight:500; color:#94a3b8; margin-left:2px; }
.summary-card .value .unit { font-size:13px; font-weight:500; color:#94a3b8; }
.phase-metric-card.highlight { background:#fffbeb; border-color:#f59e0b; }
.phase-metric-card .label .tag { margin-left:6px; vertical-align:middle; }
/* 用例对照：等宽列 + 中间留白，变化率单独一行避免撑宽 */
.case-cmp-table {
  border-collapse:separate; border-spacing:0; width:100%; table-layout:fixed;
}
.case-cmp-table th, .case-cmp-table td {
  border-bottom:1px solid #eef2f7; padding:10px 10px; vertical-align:middle;
  box-sizing:border-box;
}
.case-cmp-table thead th { font-size:12px; letter-spacing:.02em; }
.case-cmp-table thead th.case-g-ref {
  background:#fffaf0; color:#78350f; border-bottom:2px solid #fbbf24; text-align:center;
}
.case-cmp-table thead th.case-g-cmp {
  background:#f5f9ff; color:#1e3a8a; border-bottom:2px solid #60a5fa; text-align:center;
}
.case-cmp-table thead th.case-g-sub-ref { background:#fffdf7; color:#92400e; font-weight:500; text-align:center; }
.case-cmp-table thead th.case-g-sub-cmp { background:#f8fbff; color:#1d4ed8; font-weight:500; text-align:center; }
.case-cmp-table td.case-g-ref { background:#fffefb; text-align:center; }
.case-cmp-table td.case-g-cmp { background:#fafcff; text-align:center; }
.case-cmp-table th.case-g-gap, .case-cmp-table td.case-g-gap {
  width:12px; min-width:12px; max-width:12px; padding:0 !important;
  background:#f1f5f9; border-left:1px solid #e2e8f0; border-right:1px solid #e2e8f0;
}
.case-cmp-table th.case-m-avg, .case-cmp-table td.case-m-avg,
.case-cmp-table th.case-m-p95, .case-cmp-table td.case-m-p95 { width:11%; }
.case-cmp-table th.case-m-err, .case-cmp-table td.case-m-err { width:9%; }
.case-cmp-table th.case-m-n, .case-cmp-table td.case-m-n { width:7%; }
.case-cmp-table tr:hover td.case-g-ref { background:#fff7ed; }
.case-cmp-table tr:hover td.case-g-cmp { background:#eff6ff; }
.case-cmp-table th.case-name-col, .case-cmp-table td.case-name-col {
  background:#fff; position:sticky; left:0; z-index:1; width:18%;
  text-align:left; border-right:1px solid #eef2f7;
}
.case-cmp-table .num { font-variant-numeric:tabular-nums; }
.case-cmp-table .pct-line { display:block; margin-top:3px; line-height:1.2; }
.case-cmp-table .pct-line .pct-better,
.case-cmp-table .pct-line .pct-worse,
.case-cmp-table .pct-line .pct-flat { font-size:11px; }
.section-fold { margin:16px 0; border:1px solid #e8edf3; border-radius:10px; background:#fff; }
.section-fold summary { cursor:pointer; padding:14px 18px; font-weight:600; color:#334155; }
.footer { text-align:center; color:#999; font-size:12px; padding:20px 0 8px; }
.two-col { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
.edit-toolbar {
  position:sticky; top:0; z-index:1000;
  display:flex; flex-wrap:wrap; align-items:center; gap:10px 14px;
  background:#1e293b; color:#f8fafc; padding:10px 16px; font-size:13px;
  box-shadow:0 2px 8px rgba(0,0,0,.15);
}
.edit-toolbar button {
  border:0; border-radius:6px; padding:6px 12px; cursor:pointer;
  background:#3b82f6; color:#fff; font-size:13px;
}
.edit-toolbar button.secondary { background:#64748b; }
.edit-toolbar label { display:inline-flex; align-items:center; gap:6px; cursor:pointer; user-select:none; }
.edit-toolbar .hint { opacity:.85; flex:1; min-width:200px; }
body.editing #reportRoot { outline:2px dashed rgba(59,130,246,.35); outline-offset:4px; }
#reportRoot[contenteditable="true"] :focus { outline:1px solid rgba(59,130,246,.5); }
@media (max-width:768px) { .two-col { grid-template-columns:1fr; } .container { padding:12px; } }
@media print {
  body { background:#fff; }
  .section { box-shadow:none; border:1px solid #eee; }
  .edit-toolbar { display:none !important; }
  body.editing #reportRoot { outline:none; }
}
</style>"""


def report_edit_chrome() -> str:
    """导出 HTML 顶部工具条：浏览器内编辑 + 另存/打印。"""
    return """
<div class="edit-toolbar" id="editToolbar" contenteditable="false">
  <span class="hint">本报告可在浏览器中直接修改文字与数字；改完后点「保存到本地」。</span>
  <label><input type="checkbox" id="editToggle" checked> 启用编辑</label>
  <button type="button" id="btnSaveHtml">保存到本地</button>
  <button type="button" class="secondary" id="btnPrintHtml">打印</button>
</div>
<script id="reportEditScript">
(function () {
  function reportRoot() { return document.getElementById('reportRoot'); }
  function setEditable(on) {
    var c = reportRoot();
    if (!c) return;
    c.setAttribute('contenteditable', on ? 'true' : 'false');
    document.body.classList.toggle('editing', !!on);
    var t = document.getElementById('editToggle');
    if (t) t.checked = !!on;
  }
  function saveHtml() {
    var root = document.documentElement.cloneNode(true);
    var bar = root.querySelector('#editToolbar');
    if (bar) bar.remove();
    var scr = root.querySelector('#reportEditScript');
    if (scr) scr.remove();
    var c = root.querySelector('#reportRoot');
    if (c) c.setAttribute('contenteditable', 'false');
    var body = root.querySelector('body');
    if (body) body.classList.remove('editing');
    var html = '<!DOCTYPE html>\\n' + root.outerHTML;
    var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    var a = document.createElement('a');
    var title = (document.title || 'perf_report').replace(/[\\\\/:*?"<>|]+/g, '_');
    a.href = URL.createObjectURL(blob);
    a.download = title + '_edited.html';
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }
  document.addEventListener('click', function (e) {
    if (e.target && e.target.id === 'btnSaveHtml') saveHtml();
    if (e.target && e.target.id === 'btnPrintHtml') window.print();
  });
  document.addEventListener('change', function (e) {
    if (e.target && e.target.id === 'editToggle') setEditable(!!e.target.checked);
  });
  setEditable(true);
})();
</script>
"""


def ai_is_done(ai: Optional[dict]) -> bool:
    if not isinstance(ai, dict):
        return False
    return (ai.get("status") == "done") or bool(ai.get("summary") and not ai.get("status"))


def metric_note(ai: Optional[dict], key: str) -> str:
    if not isinstance(ai, dict):
        return ""
    notes = ai.get("metric_notes") or {}
    if not isinstance(notes, dict):
        return ""
    return str(notes.get(key) or "").strip()


# AI metric_notes 键 ↔ 系统 global target key（报告页映射用）
AI_NOTE_TO_TARGET_KEY = {
    "qps": "qps",
    "avg_rt": "avg_response_time",
    "p95": "p95_response_time",
    "error_rate": "error_rate",
    "total_requests": "total_requests",
    "success_qps": "success_qps",
}


def target_item_by_global_key(evaluation: Optional[dict], key: str) -> Optional[dict]:
    if not isinstance(evaluation, dict):
        return None
    for it in evaluation.get("items") or []:
        if isinstance(it, dict) and it.get("scope") == "global" and it.get("key") == key:
            return it
    return None


def target_card_note(
    evaluation: Optional[dict],
    *,
    target_key: str,
    ai: Optional[dict] = None,
    ai_note_key: Optional[str] = None,
) -> tuple[str, str]:
    """返回 (note_text, value_css_class)。

    未配置目标：固定文案，不贴 AI 短评。
    已配置：系统 message 优先；可选附加「AI 解读」。
    """
    ev = evaluation if isinstance(evaluation, dict) else {}
    has_valued = any(
        isinstance(it, dict)
        and it.get("enabled", True)
        and it.get("expected") is not None
        and it.get("status") != "skipped"
        for it in (ev.get("items") or [])
    )
    if not ev.get("enabled") or not has_valued:
        return "未配置性能目标，无法判定是否达标", ""

    item = target_item_by_global_key(ev, target_key)
    if not item:
        return "", ""

    sys_msg = str(item.get("message") or "").strip()
    st = item.get("status") or "unknown"
    css = ""
    if st == "pass":
        css = "success"
    elif st == "warn":
        css = "warning"
    elif st == "fail":
        css = "danger"

    parts = []
    if sys_msg:
        parts.append(sys_msg)
    if ai and ai_note_key:
        ai_txt = metric_note(ai, ai_note_key)
        if ai_txt:
            parts.append(f"AI 解读：{ai_txt}")
    return ("；".join(parts), css)


def render_target_evaluation_section(evaluation: Optional[dict], *, heading: str = "性能目标明细") -> str:
    """HTML：整体验收状态 + 目标明细表。"""
    ev = evaluation if isinstance(evaluation, dict) else {}
    if not ev.get("enabled"):
        return f"""<div class="section">
    <h2>{h(heading)}</h2>
    <p style="color:#64748b;font-size:13px;">未配置性能目标，无法按业务 SLA 判定是否达标。
    （与「基线退化」「错误率熔断」无关；可在场景中配置性能验收目标。）</p>
  </div>"""

    overall = ev.get("overall_status") or "unknown"
    tag_cls = {
        "pass": "tag-green",
        "warn": "tag-orange",
        "fail": "tag-red",
        "unknown": "tag-blue",
    }.get(overall, "tag-blue")
    overall_label = {
        "pass": "通过",
        "warn": "警告",
        "fail": "失败",
        "unknown": "未判定",
    }.get(overall, overall)

    trust = ev.get("trust_level") or "normal"
    warnings = ev.get("trust_warnings") or []
    trust_html = ""
    if trust == "low" or warnings:
        tips = "".join(f"<li>{h(w)}</li>" for w in warnings) or "<li>样本偏少，结论仅供参考</li>"
        trust_html = f'<div class="conclusion-box warn" style="margin-bottom:12px;"><p><strong>可信度：偏低</strong></p><ul>{tips}</ul></div>'

    rows = []
    for it in ev.get("items") or []:
        if not isinstance(it, dict):
            continue
        st = it.get("status") or "unknown"
        st_tag = {
            "pass": ("tag-green", "通过"),
            "warn": ("tag-orange", "警告"),
            "fail": ("tag-red", "失败"),
            "skipped": ("tag-blue", "跳过"),
            "unknown": ("tag-blue", "未判定"),
        }.get(st, ("tag-blue", st))
        op = it.get("op") or ""
        exp = it.get("expected")
        unit = it.get("unit") or ""
        target_s = f"{op} {exp}{(' ' + unit) if unit else ''}" if exp is not None else "—"
        act = it.get("actual")
        act_s = f"{act}{(' ' + unit) if unit and act is not None else ''}" if act is not None else "—"
        rows.append(
            "<tr>"
            f"<td>{h(it.get('label') or it.get('key'))}</td>"
            f"<td>{h(act_s)}</td>"
            f"<td>{h(target_s)}</td>"
            f"<td><span class=\"tag {st_tag[0]}\">{h(st_tag[1])}</span></td>"
            f"<td class=\"metric-note-cell\">{h(it.get('message') or '')}</td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan=\"5\" style=\"color:#999\">无目标项</td></tr>"
    return f"""<div class="section">
    <h2>{h(heading)}</h2>
    <p style="margin-bottom:10px;">整体验收：<span class="tag {tag_cls}">{h(overall_label)}</span></p>
    {trust_html}
    <table>
      <thead><tr><th>指标</th><th>实际值</th><th>目标</th><th>判定</th><th>说明</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
  </div>"""


def case_note_map(ai: Optional[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(ai, dict):
        return out
    for item in ai.get("case_notes") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        note = str(item.get("note") or "").strip()
        if name and note:
            out[name] = note
    return out


def chart_notes_by_label(ai: Optional[dict]) -> dict[str, dict[str, str]]:
    """AI chart_notes → {label: {trend, distribution}}。也兼容单次报告的 trend_note / distribution_note。"""
    out: dict[str, dict[str, str]] = {}
    if not isinstance(ai, dict):
        return out
    for item in ai.get("chart_notes") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or "").strip()
        if not label:
            continue
        trend = str(item.get("trend") or item.get("trend_note") or "").strip()
        dist = str(item.get("distribution") or item.get("distribution_note") or "").strip()
        if trend or dist:
            out[label] = {"trend": trend, "distribution": dist}
    # 单次报告扁平字段 → 默认键
    t = str(ai.get("trend_note") or "").strip()
    d = str(ai.get("distribution_note") or "").strip()
    if t or d:
        out.setdefault("_default", {"trend": t, "distribution": d})
    return out


def render_ai_lists(ai: dict) -> str:
    parts = []
    points = ai.get("conclusion_points") or ai.get("metric_deltas") or []
    if isinstance(points, list) and points:
        lis = []
        for p in points:
            if isinstance(p, str):
                lis.append(f"<li>{h(p)}</li>")
                continue
            if not isinstance(p, dict):
                continue
            label = str(p.get("label") or "").strip()
            text = str(p.get("text") or p.get("note") or "").strip()
            if not text and not label:
                continue
            tone = str(p.get("tone") or "").strip().lower()
            cls = {
                "better": "pct-better",
                "worse": "pct-worse",
                "flat": "pct-flat",
                "improved": "pct-better",
                "degraded": "pct-worse",
            }.get(tone, "")
            body = f"<strong>{h(label)}</strong>：{colorize_pct_in_text(text)}" if label else colorize_pct_in_text(text)
            if cls:
                lis.append(f'<li><span class="{cls}">{body}</span></li>')
            else:
                lis.append(f"<li>{body}</li>")
        if lis:
            parts.append("<p><strong>关键指标对照</strong></p><ul>" + "".join(lis) + "</ul>")
    for label, key in (
        ("关注要点", "highlights"),
        ("风险", "risks"),
        ("瓶颈", "bottleneck_notes"),
        ("建议", "recommendations"),
    ):
        items = ai.get(key) or []
        if items:
            parts.append(
                f"<p><strong>{label}</strong></p><ul>"
                + "".join(f"<li>{colorize_pct_in_text(x)}</li>" for x in items)
                + "</ul>"
            )
    return "".join(parts)


def render_conclusion_box(ai: Optional[dict], *, fallback_html: str = "") -> str:
    ai = ai if isinstance(ai, dict) else {}
    if ai_is_done(ai) and (ai.get("summary") or ai.get("content") or ai.get("markdown") or ai.get("conclusion_points")):
        text = ai.get("summary") or ai.get("content") or ai.get("markdown") or ""
        overview = str(ai.get("overview") or "").strip()
        body = ""
        if overview and overview != text:
            body += f"<p><strong>概览</strong></p><p>{h(overview)}</p>"
        if text:
            body += f"<p><strong>结论</strong></p><p>{h(text)}</p>"
        body += render_ai_lists(ai)
        # 有恶化要点时用 warn 边框，提示领导重点看
        tones = []
        for p in (ai.get("conclusion_points") or ai.get("metric_deltas") or []):
            if isinstance(p, dict):
                tones.append(str(p.get("tone") or "").lower())
        box_cls = "conclusion-box warn" if any(t in ("worse", "degraded") for t in tones) else "conclusion-box"
        return f'<div class="{box_cls}">{body}</div>'
    if ai.get("status") in ("running", "pending"):
        return '<div class="conclusion-box warn"><p>AI 分析进行中，请稍后重新导出。</p></div>'
    if fallback_html:
        return f'<div class="conclusion-box">{fallback_html}</div>'
    return ""


def render_overview_para(ai: Optional[dict]) -> str:
    if not ai_is_done(ai):
        return ""
    text = (ai or {}).get("overview") or ""
    if not text:
        return ""
    return f'<p style="margin-bottom:14px;color:#555">{h(text)}</p>'


def render_metric_glossary(*, heading: str = "附录：指标说明") -> str:
    """导出 HTML 共用指标释义，便于业务同学阅读。"""
    rows = (
        ("QPS", "每秒完成的请求数（Queries Per Second）。HTTP 场景下可近似理解为 TPS。"),
        ("成功 QPS", "仅统计成功请求的每秒吞吐，不含失败请求。"),
        ("平均 RT / Avg", "全部（或标注范围内）请求的平均响应时间，单位毫秒。"),
        ("P50 / Median", "中位数响应时间：50% 的请求不高于该值。"),
        ("P90", "90% 的请求响应时间不高于该值。"),
        ("P95", "95% 的请求响应时间不高于该值，常用来衡量大多数用户体验与长尾。"),
        ("P99", "99% 的请求响应时间不高于该值，更敏感地反映极端慢请求。"),
        ("Min / Max RT", "本次统计窗口内最短 / 最长响应时间。"),
        ("错误率", "失败请求数 ÷ 总请求数 × 100%。失败含 HTTP 异常或断言未通过。"),
        ("总请求 / 成功 / 失败", "压测期间发出的请求总数，以及成功、失败次数。"),
        ("并发用户数", "压测配置的虚拟用户（VU）数量。"),
        ("Ramp-up", "从 0 爬升到目标并发所需秒数，用于缓和加压。"),
        ("预热", "正式计时前的预热秒数，预热期间的请求通常不计入正式指标。"),
        ("实际时长", "压测从开始到结束的墙钟耗时（秒）。"),
        ("阶段耗时（整体/回答/检索等）", "流式或链路场景下各阶段耗时均值/P95，单位秒；越低通常越好。"),
        ("参照轮 / 对比轮", "参照轮是计算变化率时的参照对象；对比轮相对它计算百分比。同名场景请结合执行时间 / 记录号区分。"),
        ("变化率", "（对比轮 − 参照轮）÷ 参照轮 × 100%。QPS/请求数升高通常更好；RT/错误率/阶段耗时升高通常更差。"),
        ("共有 / 独有接口", "按接口名称对齐：各轮都有的为共有；仅某轮出现的为独有（缺侧显示「本轮无」）。"),
        ("趋势图 QPS 柱", "该秒瞬时完成请求数，不是全程平均 QPS。"),
        ("趋势图 RT 折线", "该秒有完成请求时的平均 / P95 响应时间；空闲秒不标点，折线连续跨过。"),
        ("响应时间分布", "按耗时区间统计请求个数，用于观察延迟是否集中、是否存在长尾。"),
    )
    body = "".join(f"<tr><td>{h(k)}</td><td>{h(v)}</td></tr>" for k, v in rows)
    return f"""
  <div class="section" contenteditable="false">
    <h2>{h(heading)}</h2>
    <p style="font-size:13px;color:#64748b;margin-bottom:10px">下列释义适用于本报告中的同名指标；若某节未出现对应字段可忽略。</p>
    <table class="glossary-table">
      <thead><tr><th>指标</th><th>含义</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
  </div>"""


def _bar_width(val: float, max_val: float) -> float:
    if max_val <= 0:
        return 8.0
    return max(8.0, min(100.0, (val / max_val) * 100.0))


def render_rt_bars(
    *,
    min_rt: Any = None,
    median_rt: Any = None,
    avg_rt: Any = None,
    p90_rt: Any = None,
    p95_rt: Any = None,
    max_rt: Any = None,
) -> str:
    items = [
        ("Min", min_rt, "green"),
        ("P50/Median", median_rt, "blue"),
        ("Avg", avg_rt, "orange"),
        ("P90", p90_rt, "blue"),
        ("P95", p95_rt, "orange"),
        ("Max", max_rt, "red"),
    ]
    nums = []
    for _, v, _ in items:
        try:
            if v is not None:
                nums.append(float(v))
        except (TypeError, ValueError):
            pass
    if not nums:
        return ""
    peak = max(nums) or 1.0
    rows = []
    for label, v, color in items:
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        w = _bar_width(fv, peak)
        rows.append(
            f'<div class="chart-bar"><div class="bar-label">{h(label)} ({h(round(fv, 2))} ms)</div>'
            f'<div class="bar-track"><div class="bar-fill {color}" style="width:{w:.1f}%">{h(round(fv, 2))} ms</div></div></div>'
        )
    return "\n".join(rows)


def render_percentile_table(
    *,
    median_rt: Any = None,
    p90_rt: Any = None,
    p95_rt: Any = None,
    p99_rt: Any = None,
    max_rt: Any = None,
    min_rt: Any = None,
    avg_rt: Any = None,
) -> str:
    cells = [
        ("Min", min_rt),
        ("P50", median_rt),
        ("Avg", avg_rt),
        ("P90", p90_rt),
        ("P95", p95_rt),
        ("P99", p99_rt),
        ("Max", max_rt),
    ]
    th = "".join(f"<th>{h(k)} <span class='unit'>(ms)</span></th>" for k, _ in cells)
    td = "".join(
        f"<td class='num'>{h(round(float(v), 2))} <span class='unit'>ms</span></td>"
        if v is not None else "<td>-</td>"
        for _, v in cells
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody><tr>{td}</tr></tbody></table>"


def metric_lower_is_better(metric_key: str) -> Optional[bool]:
    """True=越低越好；False=越高越好；None=中性。"""
    k = (metric_key or "").lower()
    if k in ("qps", "success_qps", "avg_qps", "total_requests", "success_count"):
        return False
    if k in (
        "avg_response_time", "avg_rt", "p95_response_time", "p95", "p95_rt", "avg_p95",
        "p90_response_time", "p99_response_time", "error_rate", "avg_error_rate",
        "max_response_time",
    ):
        return True
    # 流式/链路阶段指标（phase_mean_* / phase_p95_*）耗时越低越好
    if k.startswith("phase_"):
        return True
    return None


def pct_tone(pct: Optional[float], *, lower_is_better: Optional[bool] = None) -> str:
    """返回 better / worse / flat。"""
    if pct is None:
        return "flat"
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return "flat"
    if abs(p) < 0.5:
        return "flat"
    if lower_is_better is None:
        return "flat" if abs(p) < 10 else "worse"
    improved = (p < 0) if lower_is_better else (p > 0)
    return "better" if improved else "worse"


def colorize_pct_in_text(text: Any, *, metric_key: str = "", lower_is_better: Optional[bool] = None) -> str:
    """将文案中的「下降73% / 增加 12%」等按指标好坏着色（已转义 HTML）。"""
    if text is None:
        return ""
    s = str(text)
    if not s:
        return ""
    lib = lower_is_better if lower_is_better is not None else metric_lower_is_better(metric_key)
    escaped = h(s)

    def _repl(m: re.Match) -> str:
        full = m.group(0)
        verb = m.group(1) or ""
        try:
            n = float(m.group(2))
        except (TypeError, ValueError):
            return full
        if verb == "改善":
            return f'<span class="pct-better">{full}</span>'
        if verb == "恶化":
            return f'<span class="pct-worse">{full}</span>'
        up = n > 0
        if verb and re.search(r"下降|减少|降低", verb):
            up = False
        if verb and re.search(r"上升|增加|升高", verb):
            up = True
        if abs(n) < 0.5:
            return f'<span class="pct-flat">{full}</span>'
        if lib is None:
            return f'<span class="pct-flat">{full}</span>'
        better = (not up) if lib else up
        cls = "pct-better" if better else "pct-worse"
        return f'<span class="{cls}">{full}</span>'

    return re.sub(
        r"(上升|下降|增加|减少|升高|降低|改善|恶化)?\s*([+-]?\d+(?:\.\d+)?)\s*%",
        _repl,
        escaped,
    )


def pct_span(
    pct: Optional[float],
    *,
    ref: bool = False,
    lower_is_better: Optional[bool] = None,
    metric_key: str = "",
) -> str:
    if ref or pct is None:
        return ""
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return ""
    lib = lower_is_better if lower_is_better is not None else metric_lower_is_better(metric_key)
    tone = pct_tone(p, lower_is_better=lib)
    cls = {"better": "pct-better", "worse": "pct-worse", "flat": "pct-flat"}.get(tone, "pct-flat")
    return f' <span class="{cls}" style="font-size:12px">({p:+g}%)</span>'


def err_tag(rate: Any) -> str:
    try:
        r = float(rate or 0)
    except (TypeError, ValueError):
        r = 0.0
    cls = "tag-green" if r <= 0 else ("tag-orange" if r < 1 else "tag-red")
    return f'<span class="tag {cls}">{h(round(r, 2))}%</span>'
