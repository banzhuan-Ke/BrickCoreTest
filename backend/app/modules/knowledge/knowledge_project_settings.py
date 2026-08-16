"""项目级资料库 / 报告生成设置（存 Project.global_vars['knowledge_settings']）"""
from __future__ import annotations

import copy
from typing import Any, Optional

from app.core.platform.config import (
    KNOWLEDGE_EMBED_MAX_CHUNKS_PER_JOB,
    KNOWLEDGE_FULLTEXT_MAX_CHARS,
    KNOWLEDGE_MAPREDUCE_CHUNK_CHARS,
    KNOWLEDGE_MAPREDUCE_CONCURRENCY,
    KNOWLEDGE_MAPREDUCE_ENABLED,
    KNOWLEDGE_MAPREDUCE_MAX_CHUNKS,
    KNOWLEDGE_RETRIEVE_STRATEGY,
)
from app.models.sys import Project
from app.modules.knowledge.knowledge_embed_config import (
    DEFAULT_VECTOR_EMBED_DOC_TYPES,
    normalize_embed_provider,
    normalize_retrieve_strategy,
    normalize_vector_embed_doc_types,
    platform_vector_embed_allowed,
)

KNOWLEDGE_SETTINGS_GLOBAL_VARS_KEY = "knowledge_settings"

# context_strategy: auto | truncate | mapreduce | rag
DEFAULT_KNOWLEDGE_PROJECT_SETTINGS: dict[str, Any] = {
    "fulltext_max_chars": KNOWLEDGE_FULLTEXT_MAX_CHARS,
    "context_strategy": "auto",
    "mapreduce_enabled": KNOWLEDGE_MAPREDUCE_ENABLED,
    "mapreduce_chunk_chars": KNOWLEDGE_MAPREDUCE_CHUNK_CHARS,
    "mapreduce_max_chunks": KNOWLEDGE_MAPREDUCE_MAX_CHUNKS,
    "mapreduce_concurrency": KNOWLEDGE_MAPREDUCE_CONCURRENCY,
    "mapreduce_by_report_kind": True,
    "digest_cache_enabled": True,
    "digest_cache_on_upload": True,
    "digest_cache_min_chars": 12000,
    "rag_enabled": True,
    "rag_top_k": 12,
    "rag_chunk_chars": 1800,
    "rag_reindex_on_upload": True,
    "vector_embed_enabled": False,
    "vector_embed_on_upload": False,
    "vector_embed_config_id": None,
    "vector_embed_provider": "",
    "vector_embed_model": "",
    "vector_embed_ai_config_id": None,
    "retrieve_strategy": KNOWLEDGE_RETRIEVE_STRATEGY if KNOWLEDGE_RETRIEVE_STRATEGY in ("lexical", "vector", "hybrid") else "lexical",
    "hybrid_lexical_weight": 0.4,
    "vector_embed_doc_types": list(DEFAULT_VECTOR_EMBED_DOC_TYPES),
    "vector_embed_max_chunks_per_job": max(50, int(KNOWLEDGE_EMBED_MAX_CHUNKS_PER_JOB or 500)),
    "knowledge_qa_ai_config_id": None,
    "knowledge_image_parse_mode": "ocr_then_vision",
    "knowledge_doc_vision_ai_config_id": None,
    "knowledge_image_ocr_concurrency": 1,
    "default_template_by_kind": {},
    "default_knowledge_refs_enabled": False,
    "default_knowledge_auto_folders": 2,
    "default_knowledge_folder_ids": [],
    "default_knowledge_enable_case_generate": True,
    "default_knowledge_enable_test_points": True,
    "default_knowledge_enable_test_scheme": True,
    "default_knowledge_enable_failure_analysis": True,
}

KNOWLEDGE_SETTING_FIELD_DEFS: list[dict[str, Any]] = [
    {
        "key": "fulltext_max_chars",
        "label": "单次上下文上限（字）",
        "type": "int",
        "group": "context",
        "min": 8000,
        "max": 128000,
        "step": 1000,
        "recommended": "32000",
        "description": "最终送入报告/计划/方案生成 LLM 的资料总字数上限。",
        "tip": "资料少时可降到 16000 省 token；多份大需求建议 32000～48000。",
    },
    {
        "key": "context_strategy",
        "label": "超长资料处理策略",
        "type": "select",
        "group": "context",
        "options": [
            {"value": "auto", "label": "自动（推荐）"},
            {"value": "mapreduce", "label": "分块提炼 Map-Reduce"},
            {"value": "rag", "label": "检索增强 RAG"},
            {"value": "truncate", "label": "硬截断（不额外调 LLM）"},
        ],
        "recommended": "auto",
        "description": "当所选文档总字数超过上限时的处理方式。",
        "tip": "自动：优先用已缓存摘要 → RAG 检索 → Map-Reduce → 截断。",
    },
    {
        "key": "mapreduce_enabled",
        "label": "启用 Map-Reduce",
        "type": "bool",
        "group": "mapreduce",
        "recommended": "开启",
        "description": "将长文档切分后多次调用 AI 提炼要点，再合并送入报告生成。",
        "tip": "多份大 PRD 场景建议开启；会显著增加生成耗时与 token。",
    },
    {
        "key": "mapreduce_chunk_chars",
        "label": "Map 分块大小（字）",
        "type": "int",
        "group": "mapreduce",
        "min": 4000,
        "max": 24000,
        "step": 500,
        "recommended": "10000",
        "description": "单次 Map 调用送入 AI 的片段长度。",
        "tip": "模型上下文大可用 12000～16000；小模型建议 8000～10000。",
    },
    {
        "key": "mapreduce_max_chunks",
        "label": "最多 Map 片段数",
        "type": "int",
        "group": "mapreduce",
        "min": 4,
        "max": 48,
        "step": 1,
        "recommended": "24",
        "description": "一次生成最多处理的文档片段数量，防止 token 与费用失控。",
        "tip": "超大迭代可调到 32；一般 16～24 足够。",
    },
    {
        "key": "mapreduce_concurrency",
        "label": "Map 并行数",
        "type": "int",
        "group": "mapreduce",
        "min": 1,
        "max": 6,
        "step": 1,
        "recommended": "3",
        "description": "同时进行的分块提炼请求数。",
        "tip": "API 限流严时设为 1～2；配额充足可用 3～4。",
    },
    {
        "key": "mapreduce_by_report_kind",
        "label": "按报告类型调整提炼侧重",
        "type": "bool",
        "group": "mapreduce",
        "recommended": "开启",
        "description": "测试计划/方案/功能报告等使用不同的提炼提示侧重。",
        "tip": "开启后 Map 阶段会强调与当前报告类型相关的要点。",
    },
    {
        "key": "digest_cache_enabled",
        "label": "启用文档摘要缓存",
        "type": "bool",
        "group": "digest",
        "recommended": "开启",
        "description": "为长文档预生成/缓存 AI 摘要，报告生成时直接复用，避免重复 Map。",
        "tip": "同一文档多次生成报告时显著省时省 token。",
    },
    {
        "key": "digest_cache_on_upload",
        "label": "上传后自动生成摘要",
        "type": "bool",
        "group": "digest",
        "recommended": "开启",
        "description": "文档上传或重新解析成功后，后台异步生成摘要缓存。",
        "tip": "需在 AI 配置中至少有一个可用模型；大文件上传后稍等片刻。",
    },
    {
        "key": "digest_cache_min_chars",
        "label": "摘要缓存阈值（字）",
        "type": "int",
        "group": "digest",
        "min": 3000,
        "max": 80000,
        "step": 1000,
        "recommended": "12000",
        "description": "仅当文档字符数达到该值时才生成摘要缓存。",
        "tip": "短文档直接全文送入即可，无需额外摘要。",
    },
    {
        "key": "rag_enabled",
        "label": "启用词法分块索引",
        "type": "bool",
        "group": "rag",
        "recommended": "开启",
        "description": "为文档建立 TF 词法分块索引，用于关键词检索（不调用 Embedding API）。",
        "tip": "默认免费；与可选向量 Embedding 独立。",
    },
    {
        "key": "rag_top_k",
        "label": "RAG 检索条数",
        "type": "int",
        "group": "rag",
        "min": 4,
        "max": 32,
        "step": 1,
        "recommended": "12",
        "description": "检索时取相关性最高的分块数量。",
        "tip": "范围大、模块多时可调到 16～20；资料少时 8 即可。",
    },
    {
        "key": "rag_chunk_chars",
        "label": "RAG 分块大小（字）",
        "type": "int",
        "group": "rag",
        "min": 800,
        "max": 4000,
        "step": 100,
        "recommended": "1800",
        "description": "建立索引时每个分块的 target 长度。",
        "tip": "1800～2200 适合中文需求；表格多时可略小以便按行切分。",
    },
    {
        "key": "rag_reindex_on_upload",
        "label": "上传后重建词法索引",
        "type": "bool",
        "group": "rag",
        "recommended": "开启",
        "description": "文档上传或重新解析后自动更新词法分块索引。",
        "tip": "关闭后可在文件夹详情手动「重建词法索引」。",
    },
    {
        "key": "vector_embed_enabled",
        "label": "启用向量 Embedding",
        "type": "bool",
        "group": "vector_embed",
        "recommended": "关闭",
        "description": "为资料分块调用云端 Embedding API，支持语义/混合检索。",
        "tip": "默认关闭；在下方保存开启后，按 Provider 与文档类型执行，会产生 Embedding API 费用。",
    },
    {
        "key": "vector_embed_on_upload",
        "label": "上传后自动向量索引",
        "type": "bool",
        "group": "vector_embed",
        "recommended": "关闭",
        "description": "词法索引完成后，对符合类型的文档异步执行向量 Embedding。",
        "tip": "需同时开启「启用向量 Embedding」。",
    },
    {
        "key": "vector_embed_config_id",
        "label": "Embedding 模型配置",
        "type": "embed_config_id",
        "group": "vector_embed",
        "recommended": "留空（使用平台默认 Embedding 配置）",
        "description": "从平台「AI 模型 → Embedding 模型配置」中选择；留空则使用平台默认项。",
        "tip": "切换模型或维度后，需对已有文档重新「重建向量」；检索与索引须使用同一套配置。",
    },
    {
        "key": "retrieve_strategy",
        "label": "资料检索策略",
        "type": "select",
        "group": "vector_embed",
        "options": [
            {"value": "lexical", "label": "词法检索（默认）"},
            {"value": "vector", "label": "向量检索"},
            {"value": "hybrid", "label": "混合检索"},
        ],
        "recommended": "lexical",
        "description": "资料检索、资料问答与报告 RAG 使用的默认策略。",
        "tip": "未建向量索引时自动降级为词法检索。",
    },
    {
        "key": "hybrid_lexical_weight",
        "label": "混合检索 · 词法权重",
        "type": "float",
        "group": "vector_embed",
        "min": 0,
        "max": 1,
        "step": 0.05,
        "recommended": "0.4",
        "description": "混合检索时词法分数占比（0～1），其余为向量分数。",
        "tip": "仅 retrieve_strategy=hybrid 时生效。",
    },
    {
        "key": "vector_embed_doc_types",
        "label": "自动向量索引的文档类型",
        "type": "multi_select",
        "group": "vector_embed",
        "recommended": "需求/Bug/总结/计划",
        "description": "embed_mode=inherit 时，仅这些类型的文档会自动走向量 Embedding。",
        "tip": "单文档可在文件夹详情覆盖为「仅词法」或「启用向量」。",
    },
    {
        "key": "vector_embed_max_chunks_per_job",
        "label": "单次向量任务分块上限",
        "type": "int",
        "group": "vector_embed",
        "min": 50,
        "max": 5000,
        "step": 50,
        "recommended": str(max(50, int(KNOWLEDGE_EMBED_MAX_CHUNKS_PER_JOB or 500))),
        "description": "单篇文档一次「重建向量」允许的最大分块数，防止超大文档费用失控。",
        "tip": "大 Bug 导出常超过 500；可调到 800～1500。仍超限请拆分文档。环境变量 KNOWLEDGE_EMBED_MAX_CHUNKS_PER_JOB 仅作新项目默认值。",
    },
    {
        "key": "knowledge_qa_ai_config_id",
        "label": "资料问答 · 智能模式模型",
        "type": "ai_config_id",
        "group": "knowledge_qa",
        "recommended": "留空（使用场景绑定 knowledge_qa）",
        "description": "资料问答「智能模式」使用的 LLM；留空则使用 AI 场景配置中的 knowledge_qa 绑定。",
        "tip": "检索模式不消耗 LLM token。",
    },
    {
        "key": "knowledge_image_parse_mode",
        "label": "文档图片入库模式",
        "type": "select",
        "group": "knowledge_qa",
        "options": [
            {"value": "off", "label": "关闭（仅保留正文文字）"},
            {"value": "ocr", "label": "本地 OCR（RapidOCR，推荐 2G 服务器）"},
            {"value": "vision", "label": "Vision 读图（全部图片，较慢）"},
            {"value": "ocr_then_vision", "label": "OCR + Vision 加强（全部图片）"},
        ],
        "recommended": "ocr",
        "description": "上传/重新解析时，将文档内图片识别结果写入正文；无单文档张数上限，后台串行处理。",
        "tip": "默认 OCR 免费省内存；加强解析可在文档详情单独触发 Vision。",
    },
    {
        "key": "knowledge_doc_vision_ai_config_id",
        "label": "文档读图 · Vision 模型",
        "type": "ai_config_id",
        "group": "knowledge_qa",
        "recommended": "留空（使用场景绑定 requirement_doc_understand）",
        "description": "资料库文档图片 Vision 读图使用的模型；留空则使用「需求文档读图」场景绑定。",
        "tip": "仅在 vision / ocr_then_vision 模式或「加强解析」时调用。",
    },
    {
        "key": "knowledge_image_ocr_concurrency",
        "label": "图片 OCR 并行数",
        "type": "int",
        "group": "knowledge_qa",
        "min": 1,
        "max": 2,
        "step": 1,
        "recommended": "1",
        "description": "本地 RapidOCR 同时处理的图片数；2G 内存建议设为 1。",
        "tip": "张数多时后台会逐张处理，不设单文档上限。",
    },
]

SETTING_GROUPS: list[dict[str, str]] = [
    {"key": "context", "label": "上下文与长度", "description": "控制送入 LLM 的资料体量与超长时的总策略。"},
    {"key": "refs", "label": "默认资料引用", "description": "各 AI 场景未手动选择资料时的自动引用策略。"},
    {"key": "mapreduce", "label": "分块提炼 Map-Reduce", "description": "长文档分片提炼、合并，适合多份大 PRD。"},
    {"key": "digest", "label": "文档摘要缓存", "description": "预生成摘要，重复生成报告时复用。"},
    {"key": "rag", "label": "词法检索 RAG", "description": "TF 分块索引与关键词检索（默认开启，无 Embedding 费用）。"},
    {"key": "vector_embed", "label": "向量 Embedding（可选）", "description": "云端向量索引与检索策略；默认关闭。"},
    {"key": "knowledge_qa", "label": "资料问答", "description": "智能问答默认模型（Phase 4c 使用）。"},
]


def _clamp_float(val: Any, lo: float, hi: float, default: float) -> float:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _normalize_optional_ai_config_id(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        n = int(val)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _clamp_int(val: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def normalize_knowledge_project_settings(raw: Any) -> dict[str, Any]:
    base = copy.deepcopy(DEFAULT_KNOWLEDGE_PROJECT_SETTINGS)
    if not isinstance(raw, dict):
        return base
    base["fulltext_max_chars"] = _clamp_int(
        raw.get("fulltext_max_chars"), 8000, 128000, base["fulltext_max_chars"]
    )
    strategy = str(raw.get("context_strategy") or "auto").strip().lower()
    if strategy in ("auto", "truncate", "mapreduce", "rag"):
        base["context_strategy"] = strategy
    for key in (
        "mapreduce_enabled",
        "mapreduce_by_report_kind",
        "digest_cache_enabled",
        "digest_cache_on_upload",
        "rag_enabled",
        "rag_reindex_on_upload",
        "vector_embed_enabled",
        "vector_embed_on_upload",
        "default_knowledge_refs_enabled",
        "default_knowledge_enable_case_generate",
        "default_knowledge_enable_test_points",
        "default_knowledge_enable_test_scheme",
        "default_knowledge_enable_failure_analysis",
    ):
        if key in raw and raw[key] is not None:
            base[key] = bool(raw[key])
    base["mapreduce_chunk_chars"] = _clamp_int(
        raw.get("mapreduce_chunk_chars"), 4000, 24000, base["mapreduce_chunk_chars"]
    )
    base["mapreduce_max_chunks"] = _clamp_int(
        raw.get("mapreduce_max_chunks"), 4, 48, base["mapreduce_max_chunks"]
    )
    base["mapreduce_concurrency"] = _clamp_int(
        raw.get("mapreduce_concurrency"), 1, 6, base["mapreduce_concurrency"]
    )
    base["digest_cache_min_chars"] = _clamp_int(
        raw.get("digest_cache_min_chars"), 3000, 80000, base["digest_cache_min_chars"]
    )
    base["rag_top_k"] = _clamp_int(raw.get("rag_top_k"), 4, 32, base["rag_top_k"])
    base["rag_chunk_chars"] = _clamp_int(raw.get("rag_chunk_chars"), 800, 4000, base["rag_chunk_chars"])
    base["hybrid_lexical_weight"] = _clamp_float(
        raw.get("hybrid_lexical_weight"), 0.0, 1.0, base["hybrid_lexical_weight"]
    )
    base["retrieve_strategy"] = normalize_retrieve_strategy(
        raw.get("retrieve_strategy") if raw.get("retrieve_strategy") is not None else base["retrieve_strategy"]
    )
    provider_raw = raw.get("vector_embed_provider")
    if provider_raw is not None:
        base["vector_embed_provider"] = normalize_embed_provider(provider_raw) if str(provider_raw).strip() else ""
    if raw.get("vector_embed_model") is not None:
        base["vector_embed_model"] = str(raw.get("vector_embed_model") or "").strip()
    if "vector_embed_ai_config_id" in raw:
        base["vector_embed_ai_config_id"] = _normalize_optional_ai_config_id(raw.get("vector_embed_ai_config_id"))
    if "vector_embed_config_id" in raw:
        base["vector_embed_config_id"] = _normalize_optional_ai_config_id(raw.get("vector_embed_config_id"))
    if "knowledge_qa_ai_config_id" in raw:
        base["knowledge_qa_ai_config_id"] = _normalize_optional_ai_config_id(raw.get("knowledge_qa_ai_config_id"))
    if "knowledge_doc_vision_ai_config_id" in raw:
        base["knowledge_doc_vision_ai_config_id"] = _normalize_optional_ai_config_id(
            raw.get("knowledge_doc_vision_ai_config_id")
        )
    if raw.get("knowledge_image_parse_mode") is not None:
        from app.modules.knowledge.knowledge_image_parse import normalize_image_parse_mode

        base["knowledge_image_parse_mode"] = normalize_image_parse_mode(raw.get("knowledge_image_parse_mode"))
    base["knowledge_image_ocr_concurrency"] = _clamp_int(
        raw.get("knowledge_image_ocr_concurrency"), 1, 2, base["knowledge_image_ocr_concurrency"]
    )
    if raw.get("vector_embed_doc_types") is not None:
        base["vector_embed_doc_types"] = normalize_vector_embed_doc_types(raw.get("vector_embed_doc_types"))
    base["vector_embed_max_chunks_per_job"] = _clamp_int(
        raw.get("vector_embed_max_chunks_per_job"),
        50,
        5000,
        base["vector_embed_max_chunks_per_job"],
    )
    base["default_knowledge_auto_folders"] = _clamp_int(
        raw.get("default_knowledge_auto_folders"), 1, 10, base["default_knowledge_auto_folders"]
    )
    if isinstance(raw.get("default_knowledge_folder_ids"), list):
        ids: list[int] = []
        for x in raw["default_knowledge_folder_ids"]:
            try:
                n = int(x)
            except (TypeError, ValueError):
                continue
            if n > 0:
                ids.append(n)
        base["default_knowledge_folder_ids"] = ids
    if isinstance(raw.get("default_template_by_kind"), dict):
        from app.modules.knowledge.template_defaults import normalize_default_template_by_kind

        base["default_template_by_kind"] = normalize_default_template_by_kind(raw["default_template_by_kind"])
    return base


def get_knowledge_settings_from_project(project: Project) -> dict[str, Any]:
    gv = project.global_vars if isinstance(project.global_vars, dict) else {}
    return normalize_knowledge_project_settings(gv.get(KNOWLEDGE_SETTINGS_GLOBAL_VARS_KEY))


async def load_knowledge_project_settings(project_id: int) -> dict[str, Any]:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        return normalize_knowledge_project_settings(None)
    return get_knowledge_settings_from_project(project)


def knowledge_settings_updatable_keys() -> frozenset[str]:
    """可持久化的配置键（与 DEFAULT_KNOWLEDGE_PROJECT_SETTINGS 保持一致）。"""
    return frozenset(DEFAULT_KNOWLEDGE_PROJECT_SETTINGS.keys())


def knowledge_settings_schema_field_keys() -> frozenset[str]:
    """生成配置页 schema.fields 中的全部字段键。"""
    from app.modules.knowledge.knowledge_refs_resolve import knowledge_refs_settings_fields

    return frozenset(
        f["key"]
        for f in (*KNOWLEDGE_SETTING_FIELD_DEFS, *knowledge_refs_settings_fields())
        if isinstance(f, dict) and f.get("key")
    )


def extract_knowledge_settings_updates(raw: Any) -> dict[str, Any]:
    """从请求体提取合法配置项，忽略前端附带的无关字段。"""
    if not isinstance(raw, dict):
        return {}
    allowed = knowledge_settings_updatable_keys()
    return {k: raw[k] for k in raw if k in allowed}


async def save_knowledge_project_settings(project_id: int, updates: dict[str, Any]) -> dict[str, Any]:
    project = await Project.get_or_none(id=project_id, is_del=False)
    if not project:
        raise ValueError("项目不存在")
    current = get_knowledge_settings_from_project(project)
    merged = normalize_knowledge_project_settings({**current, **(updates or {})})
    gv = dict(project.global_vars or {})
    gv[KNOWLEDGE_SETTINGS_GLOBAL_VARS_KEY] = merged
    project.global_vars = gv
    await project.save()
    return merged


def settings_schema_payload() -> dict[str, Any]:
    from app.modules.knowledge.knowledge_embed_config import embed_capabilities_payload
    from app.modules.knowledge.knowledge_refs_resolve import knowledge_refs_settings_fields

    defaults = normalize_knowledge_project_settings(None)
    fields = list(KNOWLEDGE_SETTING_FIELD_DEFS) + knowledge_refs_settings_fields()
    return {
        "groups": SETTING_GROUPS,
        "fields": fields,
        "defaults": defaults,
        "embed_capabilities": embed_capabilities_payload(),
        "env_fallback": {
            "fulltext_max_chars": KNOWLEDGE_FULLTEXT_MAX_CHARS,
            "mapreduce_enabled": KNOWLEDGE_MAPREDUCE_ENABLED,
        },
    }


async def resolve_knowledge_settings(project_id: Optional[int]) -> dict[str, Any]:
    if project_id:
        return await load_knowledge_project_settings(project_id)
    return normalize_knowledge_project_settings(None)


def is_vector_embed_active(settings: dict[str, Any]) -> bool:
    """运行时是否实际走向量 Embedding（仅看项目配置，默认关闭）。"""
    return bool(settings.get("vector_embed_enabled"))


def resolve_vector_embed_max_chunks_per_job(settings: Optional[dict[str, Any]] = None) -> int:
    """单次向量任务分块上限：项目配置优先，否则环境变量默认。"""
    default = max(50, int(KNOWLEDGE_EMBED_MAX_CHUNKS_PER_JOB or 500))
    if not isinstance(settings, dict):
        return default
    return _clamp_int(settings.get("vector_embed_max_chunks_per_job"), 50, 5000, default)