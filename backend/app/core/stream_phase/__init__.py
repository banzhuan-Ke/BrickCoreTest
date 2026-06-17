from app.core.stream_phase.contract import (
    STREAM_BURST_MODE,
    LEGACY_SSE_BURST_MODE,
    normalize_perf_mode,
    is_stream_burst_mode,
    has_stream_profile_config,
    use_stream_execution,
    normalize_stream_profile,
    default_stream_profile,
)
from app.core.stream_phase.aggregate import aggregate_phase_metrics, detail_to_excel_row
from app.core.stream_phase.registry import list_parsers, get_parser_preset, parse_stream_lines
from app.core.stream_phase.engine import execute_stream_request, stream_result_to_perf_queue_item, extract_stream_detail, migrate_legacy_detail

__all__ = [
    "STREAM_BURST_MODE",
    "LEGACY_SSE_BURST_MODE",
    "normalize_perf_mode",
    "is_stream_burst_mode",
    "has_stream_profile_config",
    "use_stream_execution",
    "normalize_stream_profile",
    "default_stream_profile",
    "aggregate_phase_metrics",
    "detail_to_excel_row",
    "list_parsers",
    "get_parser_preset",
    "parse_stream_lines",
    "execute_stream_request",
    "stream_result_to_perf_queue_item",
    "extract_stream_detail",
    "migrate_legacy_detail",
]
