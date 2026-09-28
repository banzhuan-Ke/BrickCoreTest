"""AskUser 一次性认领（Redis），防止并发双提烧卡。"""
from __future__ import annotations

from typing import Any

from app.core.infra.redis_client import redis_cli

ASK_CLAIM_PREFIX = "assist_ask_claim:"
ASK_CLAIM_TTL_SECONDS = 600
PASTE_REF_PREFIX = "assist_paste_ref:"
PASTE_REF_TTL_SECONDS = 300


async def try_claim_ask_answer(*, session_id: int, ask_id: str, user_id: int) -> bool:
    """原子认领；True=本请求获得执行权。"""
    key = f"{ASK_CLAIM_PREFIX}{int(session_id)}:{str(ask_id).strip()}"
    try:
        ok = await redis_cli.set(key, str(int(user_id)), nx=True, ex=ASK_CLAIM_TTL_SECONDS)
        return bool(ok)
    except Exception:
        # Redis 异常时降级为允许（仍依赖 DB ask_user_done 检查）
        return True


async def release_ask_answer_claim(*, session_id: int, ask_id: str) -> None:
    key = f"{ASK_CLAIM_PREFIX}{int(session_id)}:{str(ask_id).strip()}"
    try:
        await redis_cli.delete(key)
    except Exception:
        pass


async def store_paste_ref(content: str, *, ttl: int = PASTE_REF_TTL_SECONDS) -> str:
    """把粘贴正文存 Redis，confirm token 只持 ref，避免巨大 payload。"""
    import uuid

    ref = uuid.uuid4().hex
    key = f"{PASTE_REF_PREFIX}{ref}"
    await redis_cli.setex(key, ttl, content or "")
    return ref


async def load_paste_ref(ref: str, *, consume: bool = True) -> str:
    key = f"{PASTE_REF_PREFIX}{str(ref or '').strip()}"
    if not key.endswith(str(ref or "").strip()) or not ref:
        raise ValueError("粘贴内容引用无效")
    if consume:
        try:
            raw = await redis_cli.getdel(key)
        except Exception:
            raw = await redis_cli.get(key)
            if raw is not None:
                await redis_cli.delete(key)
    else:
        raw = await redis_cli.get(key)
    if raw is None:
        raise ValueError("粘贴内容已过期，请重新生成预览")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return str(raw)


def validate_ask_user_answers(
    pending: dict[str, Any] | None,
    answers: dict[str, Any] | None,
) -> dict[str, Any]:
    """按 pending.fields 校验答案；返回规范化后的 answers。"""
    pending = pending if isinstance(pending, dict) else {}
    raw = answers if isinstance(answers, dict) else {}
    if str(raw.get("cancelled") or "").lower() in ("1", "true", "yes"):
        return {"cancelled": "1"}

    fields = pending.get("fields") if isinstance(pending.get("fields"), list) else []
    by_name: dict[str, dict[str, Any]] = {}
    for f in fields:
        if isinstance(f, dict) and f.get("name"):
            by_name[str(f["name"])] = f

    # 字段白名单（允许 cancelled）
    out: dict[str, Any] = {}
    for k, v in raw.items():
        key = str(k)
        if key == "cancelled":
            continue
        if by_name and key not in by_name:
            continue
        out[key] = v

    # input_mode 动态必填（需求 Chip）
    mode = str(out.get("input_mode") or "").strip().lower()
    for name, f in by_name.items():
        required = bool(f.get("required", True))
        if name == "requirement_id" and mode:
            required = mode != "paste"
        elif name == "content" and mode:
            required = mode == "paste"
        elif name == "requirement_name":
            required = False
        if not required:
            continue
        val = out.get(name)
        if val is None or (isinstance(val, str) and not val.strip()):
            label = f.get("label") or name
            raise ValueError(f"请填写：{label}")

        ft = str(f.get("field_type") or "text").lower()
        if ft == "number":
            try:
                out[name] = int(str(val).strip()) if str(val).strip().isdigit() else float(str(val).strip())
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{label} 须为数字") from exc
        elif ft == "select":
            opts = f.get("options") if isinstance(f.get("options"), list) else []
            allowed = {o.get("value") for o in opts if isinstance(o, dict)}
            # 规范化比较：数字/字符串
            if allowed:
                ok = val in allowed or str(val) in {str(a) for a in allowed}
                if not ok:
                    raise ValueError(f"{label} 不在可选列表中")
        max_len = f.get("max_length")
        if max_len is not None and isinstance(val, str):
            try:
                lim = int(max_len)
            except (TypeError, ValueError):
                lim = 0
            if lim > 0 and len(val) > lim:
                raise ValueError(f"{label} 过长（最多 {lim} 字符）")

    return out
