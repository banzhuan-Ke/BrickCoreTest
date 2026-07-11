"""步骤业务意图（intent）解析，供定位器自愈等场景使用。"""


def resolve_step_intent_text(
    *,
    step_intent: str | None = None,
    step_desc: str | None = None,
) -> str:
    """优先使用 intent，否则回退到 desc（兼容旧用例）。"""
    intent = (step_intent or "").strip()
    if intent:
        return intent
    return (step_desc or "").strip()


def resolve_step_intent_from_step(step: dict) -> str:
    if not isinstance(step, dict):
        return ""
    return resolve_step_intent_text(
        step_intent=step.get("intent"),
        step_desc=step.get("desc") or step.get("keyword"),
    )
