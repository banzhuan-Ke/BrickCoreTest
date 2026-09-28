"""需求工作区用例机器质检（AI-REQ Phase 1 确定性校验，无 LLM）。

结果写入 AiRequirementCase.extra["quality_checks"]：
  issues: [{code, level, message}]
  severity: ok | warning | error
  score: 0～100
  checked_at: ISO8601
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.modules.ai.functional_case_duplicate import _normalize_key

ISSUE_LEVELS = ("info", "warning", "error")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_steps(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for st in raw:
        if isinstance(st, dict):
            out.append(st)
        elif isinstance(st, str) and st.strip():
            out.append({"step": st.strip(), "expect": ""})
    return out


def _check_executability(case: dict) -> list[dict]:
    issues: list[dict] = []
    pre = (case.get("precondition") or "").strip()
    if not pre:
        issues.append(
            {
                "code": "missing_precondition",
                "level": "warning",
                "message": "缺少前置条件",
            }
        )
    steps = _as_steps(case.get("steps"))
    if not steps:
        issues.append(
            {
                "code": "missing_steps",
                "level": "error",
                "message": "缺少测试步骤",
            }
        )
        return issues
    empty_step = 0
    empty_expect = 0
    for st in steps:
        if not str(st.get("step") or "").strip():
            empty_step += 1
        if not str(st.get("expect") or "").strip():
            empty_expect += 1
    if empty_step:
        issues.append(
            {
                "code": "empty_step_text",
                "level": "error",
                "message": f"有 {empty_step} 个步骤正文为空",
            }
        )
    if empty_expect:
        issues.append(
            {
                "code": "empty_expect_text",
                "level": "warning",
                "message": f"有 {empty_expect} 个步骤缺少预期结果",
            }
        )
    return issues


def _check_title(case: dict) -> list[dict]:
    title = (case.get("title") or "").strip()
    if not title:
        return [{"code": "missing_title", "level": "error", "message": "缺少用例标题"}]
    if len(title) < 4:
        return [
            {
                "code": "title_too_short",
                "level": "warning",
                "message": "标题过短，可能不利于审核与去重",
            }
        ]
    return []


def _check_section_source(
    case: dict, *, selected_section_ids: list[str] | None
) -> list[dict]:
    issues: list[dict] = []
    sids = case.get("section_ids") or []
    if not isinstance(sids, list):
        sids = []
    sids = [str(x) for x in sids if x]
    if not sids:
        issues.append(
            {
                "code": "missing_section_ids",
                "level": "warning",
                "message": "未关联来源章节，不利于追溯",
            }
        )
        return issues
    if selected_section_ids:
        allowed = {str(x) for x in selected_section_ids if x}
        if allowed and not any(s in allowed for s in sids):
            issues.append(
                {
                    "code": "section_mismatch",
                    "level": "warning",
                    "message": "关联章节不在本次生成所选范围内",
                }
            )
    return issues


def _check_duplicate(
    case: dict,
    peer_cases: list[dict] | None,
    *,
    peer_index: int | None = None,
) -> list[dict]:
    if not peer_cases:
        return []
    title = _normalize_key(case.get("title") or "")
    module = _normalize_key(case.get("module") or "")
    if not title:
        return []
    self_id = case.get("id")
    hits = 0
    for i, peer in enumerate(peer_cases):
        if peer_index is not None and i == peer_index:
            continue
        if peer is case:
            continue
        if self_id is not None and peer.get("id") is not None and peer.get("id") == self_id:
            continue
        if _normalize_key(peer.get("title") or "") != title:
            continue
        if module and _normalize_key(peer.get("module") or "") not in ("", module):
            continue
        hits += 1
    if hits:
        return [
            {
                "code": "duplicate_title",
                "level": "warning",
                "message": f"与同批 {hits} 条用例标题高度相似（可能重复）",
            }
        ]
    return []


def _score_and_severity(issues: list[dict]) -> tuple[int, str]:
    if not issues:
        return 100, "ok"
    score = 100
    has_error = False
    has_warning = False
    for it in issues:
        level = (it.get("level") or "info").lower()
        if level == "error":
            has_error = True
            score -= 25
        elif level == "warning":
            has_warning = True
            score -= 10
        else:
            score -= 2
    score = max(0, min(100, score))
    if has_error:
        return score, "error"
    if has_warning:
        return score, "warning"
    return score, "ok"


def run_case_quality_checks(
    case: dict,
    *,
    peer_cases: list[dict] | None = None,
    selected_section_ids: list[str] | None = None,
    peer_index: int | None = None,
) -> dict[str, Any]:
    """对单条用例跑确定性校验。

    peer_index：在 peer_cases 中的自身下标，避免 dict 拷贝后 `is` 比对失败导致「自我重复」。
    """
    issues: list[dict] = []
    issues.extend(_check_title(case))
    issues.extend(_check_executability(case))
    issues.extend(_check_section_source(case, selected_section_ids=selected_section_ids))
    issues.extend(_check_duplicate(case, peer_cases, peer_index=peer_index))
    score, severity = _score_and_severity(issues)
    return {
        "issues": issues,
        "severity": severity,
        "score": score,
        "issue_count": len(issues),
        "checked_at": _now_iso(),
    }


def attach_quality_checks(
    extra: dict | None,
    quality: dict,
) -> dict:
    out = dict(extra) if isinstance(extra, dict) else {}
    out["quality_checks"] = quality
    return out


def apply_quality_checks_to_case_dicts(
    cases: list[dict],
    *,
    selected_section_ids: list[str] | None = None,
) -> list[dict]:
    """就地为每条用例 dict 写入 quality_checks（生成落库前用）。"""
    for idx, item in enumerate(cases):
        if not isinstance(item, dict):
            continue
        q = run_case_quality_checks(
            item,
            peer_cases=cases,
            selected_section_ids=selected_section_ids,
            peer_index=idx,
        )
        item["quality_checks"] = q
    return cases


def quality_summary_from_extra(extra: Any) -> dict[str, Any] | None:
    if not isinstance(extra, dict):
        return None
    q = extra.get("quality_checks")
    return q if isinstance(q, dict) else None


def first_issue_message(quality: dict | None) -> str:
    if not isinstance(quality, dict):
        return ""
    issues = quality.get("issues") or []
    if not issues:
        return ""
    msg = (issues[0].get("message") or "").strip()
    more = len(issues) - 1
    if more > 0:
        return f"{msg} 等 {len(issues)} 项"
    return msg
