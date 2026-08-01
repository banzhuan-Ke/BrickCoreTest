"""自然语言 → 压测场景草稿（仅编排，不施压）。

匹配项目内 ApiTestCase / ApiSuite，产出与 PerfSceneCreate 对齐的草稿。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Optional

from app.models.http import ApiSuiteCase, ApiTestCase, ApiTestSuite
from app.modules.perf.perf_journey import (
    JOURNEY_FIXED_MODE,
    JOURNEY_LOOP_MODE,
    LAYOUT_SINGLE_PHASE,
    journey_to_scene_items,
    suite_cases_to_journey,
)
from app.modules.stream_phase import STREAM_BURST_MODE, default_stream_profile, normalize_perf_mode

CATALOG_LIMIT = 80

LOAD_PROFILES = {
    "smoke": {"concurrent_users": 5, "duration_seconds": 30, "loop_count": 1},
    "normal": {"concurrent_users": 10, "duration_seconds": 60, "loop_count": 10},
    "peak": {"concurrent_users": 50, "duration_seconds": 180, "loop_count": 50},
}

# 梯度探容量默认阶段（users 上限 200，与 validate_perf_config 对齐）
STEPPING_PROFILES = {
    "smoke": [
        {"users": 5, "duration": 30},
        {"users": 10, "duration": 30},
        {"users": 20, "duration": 30},
    ],
    "normal": [
        {"users": 10, "duration": 30},
        {"users": 20, "duration": 30},
        {"users": 50, "duration": 60},
        {"users": 100, "duration": 60},
    ],
    "peak": [
        {"users": 20, "duration": 30},
        {"users": 50, "duration": 60},
        {"users": 100, "duration": 60},
        {"users": 150, "duration": 60},
        {"users": 200, "duration": 60},
    ],
}

_JOURNEY_HINT = re.compile(r"链路|流程|顺序|登录链|业务链|多步|步骤", re.I)
_LOOP_HINT = re.compile(r"瞬时|循环|每人|loop\b|打完|固定次数", re.I)
_SMOKE_HINT = re.compile(r"冒烟|试跑|小并发", re.I)
_PEAK_HINT = re.compile(r"峰值|压满|高并发|打满", re.I)
# 注意：勿把「爬坡/加压」算进梯度——那是 ramp_up
# 「最大并发」单独出现常表示目标并发值，需搭配探/找/是多少等才视为梯度意图
_STEPPING_HINT = re.compile(
    r"梯度|阶梯|递增并发|摸高|极限并发|stepping|capacity|"
    r"(?:探|找|测).{0,12}最大并发|最大并发.{0,8}(?:是多少|多少|上限|附近)",
    re.I,
)
_STREAM_BURST_HINT = re.compile(
    r"stream_burst|sse_burst|流式阶段|瞬时流式|流式突发|每人一次.*(?:流式|SSE)",
    re.I,
)
_STREAM_OVERLAY_HINT = re.compile(r"\bSSE\b|流式|首字|TTFT|问答流", re.I)

_CONCURRENT_PATTERNS = [
    re.compile(r"(?:大概|大约|约|之前|上次|估[计值]?|已知)?\s*(?:是|为|到)?\s*(\d{1,4})\s*并发", re.I),
    re.compile(r"并发\s*(?:大概|大约|约|是|为|到)?\s*(\d{1,4})", re.I),
    re.compile(r"(\d{1,4})\s*(?:个)?\s*(?:用户|VU|vu)\b", re.I),
    re.compile(r"(?:concurrent(?:_users)?|concurrency)\s*[:=]?\s*(\d{1,4})", re.I),
]


def _safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if val is None or val == "":
            return default
        return int(val)
    except (TypeError, ValueError):
        return default


def _extract_concurrent_hint(text: str) -> Optional[int]:
    """从描述中提取并发数字；优先「大概是40并发」这类表述。"""
    if not text:
        return None
    for pat in _CONCURRENT_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        n = _safe_int(m.group(1))
        if n is not None and 1 <= n <= 1000:
            return n
    return None


def _extract_duration_hint(text: str) -> Optional[int]:
    """从描述中提取持续秒数（支持 1小时 / 30分钟 / 持续30秒）。

    注意：避免把「1～3 秒间隔」误当成压测时长。
    """
    if not text:
        return None
    m = re.search(r"(?:持续|压|跑|测)?\s*(\d+(?:\.\d+)?)\s*小时", text, re.I)
    if m:
        return max(1, min(86400, int(float(m.group(1)) * 3600)))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hours?)\b", text, re.I)
    if m:
        return max(1, min(86400, int(float(m.group(1)) * 3600)))
    m = re.search(r"(?:持续|压|跑|测)?\s*(\d+(?:\.\d+)?)\s*分钟", text, re.I)
    if m:
        return max(1, min(86400, int(float(m.group(1)) * 60)))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:min|minutes?)\b", text, re.I)
    if m:
        return max(1, min(86400, int(float(m.group(1)) * 60)))
    # 秒：必须带「持续/时长」等，且排除区间间隔
    m = re.search(r"(?:持续|时长|压测)\s*(\d+)\s*秒", text, re.I)
    if m:
        return max(1, min(86400, int(m.group(1))))
    m = re.search(r"(?:duration|for)\s*(\d+)\s*(?:s|sec|seconds?)\b", text, re.I)
    if m:
        return max(1, min(86400, int(m.group(1))))
    return None


def _to_ms(val: float, unit: str) -> int:
    u = (unit or "ms").lower()
    if u in ("秒", "s", "sec", "secs", "second", "seconds"):
        return int(round(val * 1000))
    return int(round(val))


def _extract_delay_hint(text: str) -> Optional[dict]:
    """从描述提取 think-time / 步骤间隔。"""
    if not text:
        return None
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*[~～\-到至]\s*(\d+(?:\.\d+)?)\s*(秒|s|sec|secs|ms|毫秒)",
        text,
        re.I,
    )
    if m:
        a = _to_ms(float(m.group(1)), m.group(3))
        b = _to_ms(float(m.group(2)), m.group(3))
        dmin, dmax = min(a, b), max(a, b)
        return {
            "delay_mode": "random",
            "delay_ms": 0,
            "delay_ms_min": max(0, dmin),
            "delay_ms_max": max(0, dmax),
        }
    m = re.search(
        r"(?:间隔|think\s*time|思考时间|延迟)\s*(\d+(?:\.\d+)?)\s*(秒|s|sec|ms|毫秒)",
        text,
        re.I,
    )
    if m:
        ms = max(0, _to_ms(float(m.group(1)), m.group(2)))
        return {
            "delay_mode": "fixed",
            "delay_ms": ms,
            "delay_ms_min": 0,
            "delay_ms_max": 0,
        }
    if re.search(r"随机间隔|随机\s*(?:延迟|think)", text, re.I):
        return {
            "delay_mode": "random",
            "delay_ms": 0,
            "delay_ms_min": 1000,
            "delay_ms_max": 3000,
        }
    return None


def _extract_loop_count_hint(text: str) -> Optional[int]:
    if not text:
        return None
    patterns = [
        r"(?:每人|每\s*VU|每个用户)?\s*(?:循环|跑|执行)\s*(\d+)\s*(?:次|轮)",
        r"循环\s*(\d+)\s*次",
        r"loop_count\s*[:=]?\s*(\d+)",
        r"(\d+)\s*(?:次|轮)\s*(?:循环|打完)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            n = _safe_int(m.group(1))
            if n is not None and 1 <= n <= 100000:
                return n
    return None


def _extract_ramp_hint(text: str) -> Optional[int]:
    """加压/爬坡秒数（与梯度 stepping 区分）。"""
    if not text:
        return None
    m = re.search(r"(?:加压|爬坡|ramp[\-\s]?up)\s*(\d+)\s*秒", text, re.I)
    if m:
        return max(0, min(600, int(m.group(1))))
    m = re.search(r"ramp[\-\s]?up\s*[:=]?\s*(\d+)", text, re.I)
    if m:
        return max(0, min(600, int(m.group(1))))
    return None


def _extract_error_threshold_hint(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(
        r"错误率\s*(?:超|超过|大于|高于|>|≥|>=)?\s*(\d+(?:\.\d+)?)\s*%",
        text,
        re.I,
    )
    if m:
        return max(0.0, min(100.0, float(m.group(1))))
    m = re.search(r"(?:熔断|自动停[止掉])\s*(?:阈值)?\s*(\d+(?:\.\d+)?)\s*%", text, re.I)
    if m:
        return max(0.0, min(100.0, float(m.group(1))))
    return None


def _extract_warmup_hint(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(?:预热|热身|warmup)\s*(\d+)\s*秒", text, re.I)
    if m:
        return max(0, min(600, int(m.group(1))))
    return None


def _build_steps_around_anchor(anchor: int, profile: str = "normal") -> list[dict]:
    """以已知并发为中心生成探容量梯度（约 0.5x～2x）。"""
    n = max(1, min(200, int(anchor)))
    stage_duration = 30 if profile == "smoke" else 60
    if profile == "smoke":
        ratios = (0.5, 1.0, 1.5)
    elif profile == "peak":
        ratios = (0.5, 0.75, 1.0, 1.5, 2.0, 2.5)
    else:
        ratios = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)

    users_list: list[int] = []
    seen: set[int] = set()
    for r in ratios:
        u = max(1, min(200, int(round(n * r))))
        if users_list and u <= users_list[-1]:
            u = min(200, users_list[-1] + max(5, n // 4 or 5))
        if u not in seen:
            seen.add(u)
            users_list.append(u)
    if n not in seen and n <= 200:
        users_list.append(n)
        users_list = sorted(set(users_list))
    return [{"users": u, "duration": stage_duration} for u in users_list[:8]]


def _norm_delay(intent: dict, user_prompt: str = "") -> dict:
    mode = str(intent.get("delay_mode") or "").strip().lower()
    delay_ms = max(0, _safe_int(intent.get("delay_ms"), 0) or 0)
    dmin = max(0, _safe_int(intent.get("delay_ms_min"), 0) or 0)
    dmax = max(0, _safe_int(intent.get("delay_ms_max"), 0) or 0)
    has_intent_delay = delay_ms > 0 or dmin > 0 or dmax > 0 or mode in ("fixed", "random")
    if mode not in ("fixed", "random"):
        mode = "fixed"
    if mode == "random" and dmax < dmin:
        dmin, dmax = dmax, dmin
    # intent 未给出有效间隔时，从话术兜底（如「1～3 秒随机间隔」）
    if not (delay_ms or dmin or dmax):
        hint = _extract_delay_hint(user_prompt or "")
        if hint:
            return hint
        if not has_intent_delay:
            return {
                "delay_mode": "fixed",
                "delay_ms": 0,
                "delay_ms_min": 0,
                "delay_ms_max": 0,
            }
    return {
        "delay_mode": mode,
        "delay_ms": delay_ms,
        "delay_ms_min": dmin,
        "delay_ms_max": dmax,
    }


def _apply_delay_to_items(items: list[dict], delay: dict) -> list[dict]:
    out = []
    for it in items:
        row = dict(it)
        row.update(delay)
        out.append(row)
    return out


def _apply_delay_to_journey(journey: dict, delay: dict) -> dict:
    phases = []
    for phase in journey.get("phases") or []:
        steps = []
        for step in phase.get("steps") or []:
            s = dict(step)
            s.update(delay)
            steps.append(s)
        p = dict(phase)
        p["steps"] = steps
        phases.append(p)
    j = dict(journey)
    j["phases"] = phases
    return j


def infer_profile(user_prompt: str, intent: Optional[dict] = None) -> str:
    intent = intent or {}
    raw = str(intent.get("profile") or "").strip().lower()
    if raw in LOAD_PROFILES:
        return raw
    text = user_prompt or ""
    if _SMOKE_HINT.search(text):
        return "smoke"
    if _PEAK_HINT.search(text):
        return "peak"
    return "normal"


def _want_stepping(intent: dict, user_prompt: str) -> bool:
    mode = str(intent.get("mode") or "").strip().lower()
    if mode == "stepping":
        return True
    if isinstance(intent.get("steps"), list) and intent.get("steps"):
        return True
    # LLM 已明确非梯度模式时，不因话术弱匹配强行改写
    if mode in ("fixed", "loop", JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE, STREAM_BURST_MODE, "sse_burst"):
        return False
    return bool(_STEPPING_HINT.search(user_prompt or ""))


def _want_stream_burst(intent: dict, user_prompt: str) -> bool:
    mode = normalize_perf_mode(str(intent.get("mode") or ""))
    if mode == STREAM_BURST_MODE:
        return True
    return bool(_STREAM_BURST_HINT.search(user_prompt or ""))


def _want_stream_overlay(intent: dict, user_prompt: str) -> bool:
    """非 stream_burst 模式下是否挂 stream_profile（SSE/流式解析）。"""
    if intent.get("stream_profile") and isinstance(intent.get("stream_profile"), dict):
        return True
    if _want_stream_burst(intent, user_prompt):
        return False
    return bool(_STREAM_OVERLAY_HINT.search(user_prompt or ""))


def _coerce_error_threshold(intent: dict, user_prompt: str, profile: str) -> float:
    raw = intent.get("error_rate_threshold")
    if raw is not None and raw != "":
        try:
            return max(0.0, min(100.0, float(raw)))
        except (TypeError, ValueError):
            pass
    hint = _extract_error_threshold_hint(user_prompt or "")
    if hint is not None:
        return hint
    # 峰值档默认开启熔断，与编辑页默认 50 对齐
    if profile == "peak":
        return 50.0
    return 0.0


def _normalize_steps(
    raw_steps: Any,
    profile: str,
    *,
    anchor: Optional[int] = None,
    fallback: bool = True,
) -> list[dict]:
    """归一化梯度阶段；非法/空则按锚点或 profile 给默认可落库阶段。"""
    out: list[dict] = []
    if isinstance(raw_steps, list):
        for s in raw_steps:
            if not isinstance(s, dict):
                continue
            users = _safe_int(s.get("users") or s.get("concurrent_users") or s.get("concurrency"))
            duration = _safe_int(s.get("duration") or s.get("duration_seconds"))
            if users is None or duration is None:
                continue
            users = max(1, min(200, users))
            duration = max(1, min(3600, duration))
            out.append({"users": users, "duration": duration})
    if not out:
        if not fallback:
            return []
        if anchor and anchor >= 1:
            out = _build_steps_around_anchor(anchor, profile)
        else:
            out = [dict(s) for s in STEPPING_PROFILES.get(profile) or STEPPING_PROFILES["normal"]]
    # 阶段应按并发非降序探容量；若 LLM 乱序则按 users 升序
    if len(out) >= 2 and any(out[i]["users"] > out[i + 1]["users"] for i in range(len(out) - 1)):
        out = sorted(out, key=lambda x: (x["users"], x["duration"]))
    return out[:20]


def parse_llm_intent(raw: str) -> dict:
    """从 LLM 文本提取意图 JSON；失败返回空 dict。"""
    if not raw or not str(raw).strip():
        return {}
    text = str(raw).strip()
    code_block = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
    for block in code_block:
        try:
            data = json.loads(block.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _case_matches_tags(case_tags: Any, wanted: list[str]) -> bool:
    if not wanted:
        return True
    tags = case_tags if isinstance(case_tags, list) else []
    lower = {str(t).strip().lower() for t in tags if t is not None}
    return any(w.lower() in lower for w in wanted)


def _case_row(case: ApiTestCase) -> dict:
    api = case.api
    return {
        "id": case.id,
        "name": case.name or "",
        "tags": case.tags or [],
        "method": (api.method if api else "") or "",
        "path": (api.path if api else "") or "",
    }


async def build_case_catalog(
    project_id: int,
    *,
    suite_id: Optional[int] = None,
    tags: Optional[list[str]] = None,
    case_ids: Optional[list[int]] = None,
    limit: int = CATALOG_LIMIT,
) -> dict[str, Any]:
    """压缩候选用例/套件，供 Prompt 与 resolve 使用。

    - 套件 case_ids 仅含未删除且属本项目的用例
    - 指定 suite_id 时不回退到全项目用例池
    - 指定 case_ids 时优先按给定用例构建候选（测单接口）
    """
    wanted_tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
    suites_out: list[dict] = []
    cases_out: list[dict] = []
    seen_ids: set[int] = set()

    # 用户显式点选的接口用例：优先作为候选池（不再用标签过滤，避免「用例在但没打 tag」被误杀）
    wanted_case_ids: list[int] = []
    if case_ids:
        for x in case_ids:
            cid = _safe_int(x)
            if cid is None or cid in seen_ids:
                continue
            wanted_case_ids.append(cid)
            seen_ids.add(cid)
        seen_ids.clear()
        if wanted_case_ids:
            live_cases = await ApiTestCase.filter(
                id__in=wanted_case_ids, project_id=project_id, is_del=False
            ).prefetch_related("api").all()
            live_by_id = {c.id: c for c in live_cases}
            for cid in wanted_case_ids:
                case = live_by_id.get(cid)
                if not case:
                    continue
                cases_out.append(_case_row(case))
                seen_ids.add(cid)
            return {
                "cases": cases_out[:limit],
                "suites": [],
            }

    suite_qs = ApiTestSuite.filter(project_id=project_id, is_del=False)
    if suite_id:
        suite_qs = suite_qs.filter(id=suite_id)
    suites = await suite_qs.order_by("-id").limit(30).all()

    suite_id_list = [s.id for s in suites]
    links_by_suite: dict[int, list[int]] = defaultdict(list)
    if suite_id_list:
        links = await ApiSuiteCase.filter(suite_id__in=suite_id_list).order_by("sort").all()
        for lk in links:
            links_by_suite[lk.suite_id].append(lk.case_id)

    all_link_ids = list({cid for cids in links_by_suite.values() for cid in cids})
    live_by_id: dict[int, ApiTestCase] = {}
    if all_link_ids:
        live_cases = await ApiTestCase.filter(
            id__in=all_link_ids, project_id=project_id, is_del=False
        ).prefetch_related("api").all()
        live_by_id = {c.id: c for c in live_cases}

    for suite in suites:
        raw_ids = links_by_suite.get(suite.id) or []
        live_ordered = [cid for cid in raw_ids if cid in live_by_id]
        if wanted_tags:
            live_ordered = [
                cid for cid in live_ordered
                if _case_matches_tags(live_by_id[cid].tags, wanted_tags)
            ]
        suites_out.append({
            "id": suite.id,
            "name": suite.name or "",
            "case_ids": live_ordered,
        })
        if suite_id and suite.id == suite_id:
            for cid in live_ordered:
                if cid in seen_ids:
                    continue
                cases_out.append(_case_row(live_by_id[cid]))
                seen_ids.add(cid)

    # 仅未指定套件时，才回退到项目用例池
    if not cases_out and not suite_id:
        qs = ApiTestCase.filter(project_id=project_id, is_del=False)
        cases = await qs.order_by("-id").limit(max(limit * 3, limit)).prefetch_related("api").all()
        for case in cases:
            if case.id in seen_ids:
                continue
            if not _case_matches_tags(case.tags, wanted_tags):
                continue
            cases_out.append(_case_row(case))
            seen_ids.add(case.id)
            if len(cases_out) >= limit:
                break

    return {
        "cases": cases_out[:limit],
        "suites": suites_out,
    }


def format_catalog_for_prompt(catalog: dict) -> tuple[str, str]:
    cases = catalog.get("cases") or []
    suites = catalog.get("suites") or []
    cases_compact = [
        {
            "id": c["id"],
            "name": c["name"],
            "tags": c.get("tags") or [],
            "api": f"{c.get('method') or ''} {c.get('path') or ''}".strip(),
        }
        for c in cases
    ]
    suites_compact = [
        {"id": s["id"], "name": s["name"], "case_ids": s.get("case_ids") or []}
        for s in suites
    ]
    return (
        json.dumps(cases_compact, ensure_ascii=False, indent=2),
        json.dumps(suites_compact, ensure_ascii=False, indent=2),
    )


def _resolve_case_ids(
    intent: dict,
    catalog_cases: list[dict],
) -> tuple[list[int], list[str], list[dict]]:
    """返回 (matched_ids, unmatched_labels, matched_case_rows)。"""
    by_id = {int(c["id"]): c for c in catalog_cases if c.get("id") is not None}
    by_name: dict[str, list[dict]] = {}
    for c in catalog_cases:
        key = (c.get("name") or "").strip().lower()
        if key:
            by_name.setdefault(key, []).append(c)

    matched: list[int] = []
    unmatched: list[str] = []
    seen: set[int] = set()

    raw_ids = intent.get("case_ids") or []
    if isinstance(raw_ids, list):
        for x in raw_ids:
            cid = _safe_int(x)
            if cid is None:
                unmatched.append(str(x))
                continue
            if cid in by_id and cid not in seen:
                matched.append(cid)
                seen.add(cid)
            else:
                unmatched.append(f"case_id={cid}")

    raw_names = intent.get("case_names") or []
    if isinstance(raw_names, list):
        for name in raw_names:
            key = str(name or "").strip().lower()
            if not key:
                continue
            hits = by_name.get(key) or []
            if not hits:
                hits = [
                    c for c in catalog_cases
                    if key in (c.get("name") or "").lower()
                ]
            if not hits:
                unmatched.append(str(name))
                continue
            cid = int(hits[0]["id"])
            if cid not in seen:
                matched.append(cid)
                seen.add(cid)

    matched_rows = [by_id[i] for i in matched if i in by_id]
    return matched, unmatched, matched_rows


def _coerce_prefer_journey(intent: dict, user_prompt: str) -> tuple[bool, bool]:
    """返回 (prefer_journey, explicit)。explicit=True 表示用户/LLM 显式指定。"""
    raw = intent.get("prefer_journey", None)
    if isinstance(raw, bool):
        return raw, True
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw), True
    if isinstance(raw, str):
        low = raw.strip().lower()
        if low in ("true", "1", "yes", "y"):
            return True, True
        if low in ("false", "0", "no", "n"):
            return False, True
    return bool(_JOURNEY_HINT.search(user_prompt or "")), False


def resolve_draft(
    *,
    intent: dict,
    catalog_cases: list[dict],
    catalog_suites: list[dict],
    user_prompt: str,
    project_id: int,
    catalog_id: Optional[int] = None,
) -> dict[str, Any]:
    """将 LLM 意图解析为可预览/落库的草稿。"""
    intent = intent if isinstance(intent, dict) else {}
    warnings: list[str] = []
    delay = _norm_delay(intent, user_prompt)
    profile = infer_profile(user_prompt, intent)
    defaults = LOAD_PROFILES[profile]

    suite_by_id = {int(s["id"]): s for s in catalog_suites if s.get("id") is not None}
    suite_id = _safe_int(intent.get("suite_id"))
    suite_meta = suite_by_id.get(suite_id) if suite_id else None
    if suite_id and not suite_meta:
        warnings.append(f"suite_id={suite_id} 不在候选套件中，已忽略")
        suite_id = None

    matched_ids: list[int] = []
    unmatched: list[str] = []
    matched_rows: list[dict] = []
    journey = None
    journey_source = None

    if suite_meta:
        # catalog 中的 case_ids 已过滤删除/标签
        suite_case_ids = [int(x) for x in (suite_meta.get("case_ids") or []) if _safe_int(x)]
        ordered_cases = [{"case_id": cid, "name": ""} for cid in suite_case_ids]
        if not ordered_cases:
            unmatched.append(f"套件 {suite_meta.get('name')} 无有效用例")
        else:
            journey = suite_cases_to_journey(
                ordered_cases,
                layout=LAYOUT_SINGLE_PHASE,
                suite_name=suite_meta.get("name") or "",
            )
            journey = _apply_delay_to_journey(journey, delay)
            matched_ids = suite_case_ids
            # 必须按套件原始顺序输出 matched_cases，避免前端按 catalog 倒序重建链路
            by_catalog = {
                int(c["id"]): c for c in catalog_cases if c.get("id") is not None
            }
            matched_rows = []
            for cid in suite_case_ids:
                if cid in by_catalog:
                    matched_rows.append(by_catalog[cid])
                else:
                    matched_rows.append({
                        "id": cid, "name": f"用例#{cid}", "tags": [], "method": "", "path": "",
                    })
            journey_source = {
                "suite_id": suite_meta["id"],
                "suite_name": suite_meta.get("name") or "",
                "layout": LAYOUT_SINGLE_PHASE,
                "case_ids": suite_case_ids,
                "imported_at": None,
                "from_ai_nl": True,
            }
    else:
        matched_ids, unmatched, matched_rows = _resolve_case_ids(intent, catalog_cases)

    prefer_journey, prefer_explicit = _coerce_prefer_journey(intent, user_prompt)
    want_stepping = _want_stepping(intent, user_prompt)
    want_stream_burst = _want_stream_burst(intent, user_prompt) and not want_stepping
    want_stream_overlay = _want_stream_overlay(intent, user_prompt) and not want_stream_burst
    mode_input = str(intent.get("mode") or "").strip().lower()
    if want_stepping:
        # 梯度模式与 journey 互斥：平台 stepping 不支持链路编排
        prefer_journey = False
        if journey:
            journey = None
            journey_source = None
            warnings.append("梯度探容量已改为按勾选用例加权施压（非链路顺序）")
    elif want_stream_burst:
        prefer_journey = False
        if journey:
            journey = None
            journey_source = None
            warnings.append("流式阶段压测已改为按勾选用例施压（非链路顺序）")
    elif suite_meta:
        prefer_journey = True
    elif not prefer_explicit and len(matched_ids) > 1:
        # 多用例默认链路；但 LLM 已明确 fixed/loop 等表示混合加权流量时尊重
        if mode_input in ("fixed", "loop", STREAM_BURST_MODE, "sse_burst", "stepping"):
            prefer_journey = False
        else:
            prefer_journey = True

    want_loop = bool(_LOOP_HINT.search(user_prompt or ""))
    mode_raw = normalize_perf_mode(mode_input) if mode_input else ""
    allowed_modes = (
        "fixed",
        "loop",
        "stepping",
        STREAM_BURST_MODE,
        JOURNEY_FIXED_MODE,
        JOURNEY_LOOP_MODE,
    )
    if want_stepping:
        mode_raw = "stepping"
    elif want_stream_burst:
        mode_raw = STREAM_BURST_MODE
    elif not mode_raw or mode_raw not in allowed_modes:
        if prefer_journey:
            mode_raw = JOURNEY_LOOP_MODE if want_loop else JOURNEY_FIXED_MODE
        else:
            mode_raw = "loop" if want_loop else "fixed"
    elif want_loop and mode_raw == "fixed" and not prefer_journey:
        # 话术明确瞬时/循环，且未走链路时，纠正 LLM 误标的 fixed
        mode_raw = "loop"

    prompt_concurrent = _extract_concurrent_hint(user_prompt or "")
    prompt_duration = _extract_duration_hint(user_prompt or "")
    prompt_loop = _extract_loop_count_hint(user_prompt or "")
    prompt_ramp = _extract_ramp_hint(user_prompt or "")
    prompt_warmup = _extract_warmup_hint(user_prompt or "")
    concurrent = _safe_int(intent.get("concurrent_users"))
    duration = _safe_int(intent.get("duration_seconds"))
    loop_count = _safe_int(intent.get("loop_count"))
    ramp = _safe_int(intent.get("ramp_up_seconds"))
    if ramp is None:
        ramp = prompt_ramp if prompt_ramp is not None else 0
    warmup = _safe_int(intent.get("warmup_seconds"))
    if warmup is None:
        warmup = prompt_warmup
    error_threshold = _coerce_error_threshold(intent, user_prompt or "", profile)
    # 梯度：优先用描述里的已知并发作锚点；LLM steps 若离锚点太远则重算
    step_anchor = concurrent if (concurrent and concurrent >= 1) else prompt_concurrent
    steps: list[dict] = []
    if want_stepping:
        llm_steps = _normalize_steps(
            intent.get("steps"), profile, anchor=None, fallback=False
        )
        # 仅当 LLM 真给了 steps 时 _normalize_steps 才非空；空则走锚点/默认
        had_llm_steps = isinstance(intent.get("steps"), list) and bool(intent.get("steps"))
        if had_llm_steps and llm_steps:
            if step_anchor and not any(
                abs(s["users"] - step_anchor) <= max(5, int(step_anchor * 0.25))
                for s in llm_steps
            ):
                steps = _build_steps_around_anchor(step_anchor, profile)
                warnings.append(f"已按已知约 {step_anchor} 并发重算梯度阶段")
            else:
                steps = llm_steps
        else:
            steps = _normalize_steps(None, profile, anchor=step_anchor)
    if concurrent is None or concurrent < 1:
        if want_stepping and steps:
            concurrent = max(s["users"] for s in steps)
        elif prompt_concurrent:
            concurrent = prompt_concurrent
        else:
            concurrent = defaults["concurrent_users"]
            warnings.append(f"未指定并发，已按 {profile} 档默认 {concurrent}")
    concurrent = max(1, min(1000, concurrent))
    if duration is None or duration < 1:
        if prompt_duration:
            duration = prompt_duration
        else:
            duration = defaults["duration_seconds"]
    duration = max(1, min(86400, duration))
    if loop_count is None or loop_count < 1:
        if prompt_loop:
            loop_count = prompt_loop
        else:
            loop_count = defaults["loop_count"]
    loop_count = max(1, min(100000, loop_count))
    ramp = max(0, min(600, ramp or 0))

    if prefer_journey and matched_ids and journey is None:
        ordered = [{"case_id": cid, "name": ""} for cid in matched_ids]
        journey = suite_cases_to_journey(
            ordered,
            layout=LAYOUT_SINGLE_PHASE,
            suite_name=(intent.get("name") or "业务链路"),
        )
        journey = _apply_delay_to_journey(journey, delay)

    # 显式不要 journey：清掉误建的链路
    if not prefer_journey:
        journey = None
        journey_source = None
        if mode_raw in (JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE):
            mode_raw = "loop" if mode_raw == JOURNEY_LOOP_MODE or want_loop else "fixed"

    if journey and mode_raw in ("fixed", "loop"):
        mode_raw = JOURNEY_LOOP_MODE if mode_raw == "loop" else JOURNEY_FIXED_MODE
    if journey and mode_raw not in (JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE):
        if mode_raw not in ("stepping", STREAM_BURST_MODE):
            mode_raw = JOURNEY_LOOP_MODE if want_loop else JOURNEY_FIXED_MODE

    scene_items: list[dict] = []
    config: dict[str, Any] = {
        "mode": mode_raw,
        "concurrent_users": concurrent,
        "ramp_up_seconds": ramp,
        "error_rate_threshold": error_threshold,
        "distribution_mode": "weighted_random",
    }
    if warmup is not None:
        config["warmup_seconds"] = max(0, min(600, warmup))

    stream_profile = None
    if isinstance(intent.get("stream_profile"), dict) and intent.get("stream_profile"):
        stream_profile = dict(intent["stream_profile"])
    elif want_stream_burst or want_stream_overlay:
        stream_profile = default_stream_profile()
    if stream_profile:
        config["stream_profile"] = stream_profile

    if mode_raw == "stepping":
        config["mode"] = "stepping"
        config["steps"] = steps
        # concurrent_users 取峰值阶段，便于列表展示；执行以 steps 为准
        config["concurrent_users"] = max(s["users"] for s in steps) if steps else concurrent
        scene_items = _apply_delay_to_items(
            [{"case_id": cid, "weight": 1} for cid in matched_ids],
            delay,
        )
        if not steps:
            warnings.append("梯度阶段为空，请补全 steps 后再落库")
    elif mode_raw == STREAM_BURST_MODE:
        config["mode"] = STREAM_BURST_MODE
        if not config.get("stream_profile"):
            config["stream_profile"] = default_stream_profile()
        scene_items = _apply_delay_to_items(
            [{"case_id": cid, "weight": 1} for cid in matched_ids],
            delay,
        )
    elif journey:
        config["journey"] = journey
        if journey_source:
            config["journey_source"] = journey_source
        scene_items = _apply_delay_to_items(journey_to_scene_items({"journey": journey}), delay)
        if mode_raw == JOURNEY_LOOP_MODE:
            config["loop_count"] = loop_count
        else:
            config["mode"] = JOURNEY_FIXED_MODE
            config["duration_seconds"] = duration
    else:
        scene_items = _apply_delay_to_items(
            [{"case_id": cid, "weight": 1} for cid in matched_ids],
            delay,
        )
        if mode_raw == "loop":
            config["loop_count"] = loop_count
        else:
            config["mode"] = "fixed"
            config["duration_seconds"] = duration

    name = (intent.get("name") or "").strip() or (user_prompt or "AI压测场景")[:40]
    name = name[:100]
    description = (intent.get("reasoning") or "").strip()
    if not description:
        description = f"AI 一句话生成：{(user_prompt or '')[:180]}"

    importable = bool(scene_items) or bool(
        journey and any((p.get("steps") or []) for p in (journey.get("phases") or []))
    )
    if mode_raw == "stepping" and not steps:
        importable = False
    if not importable:
        warnings.append("未匹配到可用用例，无法创建场景；请补充套件/标签约束或改写描述")

    return {
        "name": name,
        "description": description[:500],
        "project_id": project_id,
        "catalog_id": catalog_id,
        "scene_items": scene_items,
        "config": config,
        "matched_cases": [
            {"id": c.get("id"), "name": c.get("name"), "method": c.get("method"), "path": c.get("path")}
            for c in matched_rows
        ],
        "unmatched": unmatched,
        "warnings": warnings,
        "importable": importable,
        "profile": profile,
        "reasoning": intent.get("reasoning") or "",
    }


def apply_selected_cases(draft: dict, selected_ids: list[int]) -> dict:
    """按勾选的 case_id 重建 scene_items / journey（前端预览编辑用，亦可服务端复用）。"""
    draft = dict(draft or {})
    config = dict(draft.get("config") or {})
    matched = list(draft.get("matched_cases") or [])
    by_id = {int(c["id"]): c for c in matched if c.get("id") is not None}
    selected_set = {int(cid) for cid in selected_ids if cid is not None}
    # 优先沿用 journey_source / journey / scene_items 的规范顺序，避免勾选表序打乱链路
    canonical: list[int] = []
    src_ids = (config.get("journey_source") or {}).get("case_ids") or []
    if isinstance(src_ids, list) and src_ids:
        canonical = [int(x) for x in src_ids if _safe_int(x) is not None]
    if not canonical:
        for phase in ((config.get("journey") or {}).get("phases") or []):
            for step in phase.get("steps") or []:
                cid = _safe_int(step.get("case_id"))
                if cid is not None:
                    canonical.append(cid)
    if not canonical:
        for it in draft.get("scene_items") or []:
            if isinstance(it, dict):
                cid = _safe_int(it.get("case_id"))
                if cid is not None:
                    canonical.append(cid)
    if not canonical:
        canonical = [int(x) for x in selected_ids if _safe_int(x) is not None]

    seen: set[int] = set()
    ordered: list[int] = []
    for cid in canonical:
        if cid in selected_set and cid in by_id and cid not in seen:
            ordered.append(cid)
            seen.add(cid)
    for cid in selected_ids:
        try:
            n = int(cid)
        except (TypeError, ValueError):
            continue
        if n in selected_set and n in by_id and n not in seen:
            ordered.append(n)
            seen.add(n)

    delay = _norm_delay({})
    items = draft.get("scene_items") or []
    if items and isinstance(items[0], dict):
        delay = _norm_delay(items[0])
    else:
        for phase in ((config.get("journey") or {}).get("phases") or []):
            for step in phase.get("steps") or []:
                delay = _norm_delay(step)
                break
            else:
                continue
            break

    mode = str(config.get("mode") or "fixed")
    use_journey = (
        mode not in ("stepping", STREAM_BURST_MODE, "sse_burst")
        and (mode in (JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE) or bool(config.get("journey")))
    )
    if use_journey and ordered:
        phase_name = "业务链路"
        phases = ((config.get("journey") or {}).get("phases") or [])
        if phases and phases[0].get("name"):
            phase_name = phases[0]["name"]
        journey = suite_cases_to_journey(
            [{"case_id": cid} for cid in ordered],
            layout=LAYOUT_SINGLE_PHASE,
            suite_name=phase_name,
        )
        journey = _apply_delay_to_journey(journey, delay)
        config["journey"] = journey
        if mode not in (JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE):
            config["mode"] = JOURNEY_FIXED_MODE
        scene_items = _apply_delay_to_items(journey_to_scene_items({"journey": journey}), delay)
        src = dict(config.get("journey_source") or {})
        if src:
            src["case_ids"] = ordered
            config["journey_source"] = src
    else:
        config.pop("journey", None)
        if mode in (JOURNEY_FIXED_MODE, JOURNEY_LOOP_MODE):
            config["mode"] = "loop" if mode == JOURNEY_LOOP_MODE else "fixed"
        scene_items = _apply_delay_to_items([{"case_id": cid, "weight": 1} for cid in ordered], delay)

    draft["config"] = config
    draft["scene_items"] = scene_items
    draft["matched_cases"] = matched
    draft["importable"] = bool(scene_items)
    if not draft["importable"]:
        warnings = list(draft.get("warnings") or [])
        msg = "请至少勾选一个用例"
        if msg not in warnings:
            warnings.append(msg)
        draft["warnings"] = warnings
    return draft
