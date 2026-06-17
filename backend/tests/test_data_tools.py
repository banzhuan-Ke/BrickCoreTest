"""通用数据工厂工具箱单元测试"""
import pytest

from app.core.data_tools.executor import ToolExecutionError, execute_tool
from app.core.data_tools.registry import list_tools


def test_tool_count_at_least_18():
    assert len(list_tools()) >= 55


def test_uuid_tool():
    result = execute_tool("uuid", {})
    assert result["output_text"]
    assert len(result["output_text"]) == 36


def test_md5_tool():
    result = execute_tool("md5", {"text": "hello"})
    assert result["output"] == "5d41402abc4b2a76b9719d911017c592"


def test_json_format_invalid():
    with pytest.raises(ToolExecutionError):
        execute_tool("json_format", {"text": "not-json"})


def test_json_path_tool():
    payload = '{"data": {"name": "Tom"}}'
    result = execute_tool("json_path", {"text": payload, "path": "$.data.name"})
    assert result["output"] == "Tom"


def test_hmac_sha256_tool():
    result = execute_tool("hmac_sha256", {"text": "hello", "secret": "key"})
    assert result["output_text"]
    assert len(result["output_text"]) == 64


def test_json_compare_equal():
    result = execute_tool("json_compare", {"left": '{"a":1}', "right": '{"a":1}'})
    assert result["output"]["equal"] is True


def test_json_get_type_standard_json():
    result = execute_tool("json_get_type", {"text": '{"test": 12}', "path": "$.test"})
    assert result["output"] == "number"


def test_json_get_type_python_literal():
    result = execute_tool("json_get_type", {"text": "{'test': 12}", "path": "$.test"})
    assert result["output"] == "number"


def test_json_get_type_invalid():
    with pytest.raises(ToolExecutionError):
        execute_tool("json_get_type", {"text": "not-json", "path": "$.test"})


def test_json_format_python_literal():
    result = execute_tool("json_format", {"text": "{'a': 1}"})
    assert '"a"' in result["output_text"]


def test_cron_validate_tool():
    result = execute_tool("cron_validate", {"expr": "0 0 * * *"})
    assert result["output"]["valid"] is True


@pytest.mark.asyncio
async def test_merge_df_tag_variables_empty_project():
    from app.core.data_tools.tag_service import (
        merge_df_tag_variables,
        merge_execution_variables,
    )

    assert await merge_df_tag_variables(0, None) == {}
    assert await merge_execution_variables(None, None) == {}
    assert await merge_execution_variables(None, None, {"x": "1"}) == {"x": "1"}


def test_normalize_output_data_scalar_uuid():
    from app.core.data_tools.tag_service import normalize_output_data_for_storage

    uid = "c0dca218-c808-4706-a218-c5b47db981cf"
    stored, text = normalize_output_data_for_storage(uid, uid)
    assert stored == {}
    assert text == uid


def test_normalize_output_data_dict():
    from app.core.data_tools.tag_service import normalize_output_data_for_storage

    data = {"a": 1}
    stored, text = normalize_output_data_for_storage(data, None)
    assert stored == data
    assert text == '{"a": 1}'


def test_extract_df_tags_from_value():
    from app.core.data_tools.tag_refs import extract_df_tags_from_value

    assert extract_df_tags_from_value("phone=${{df:uuid_894931}}") == {"uuid_894931"}
    assert extract_df_tags_from_value({"value": "${{df:mobile}}", "x": 1}) == {"mobile"}
    assert extract_df_tags_from_value([]) == set()


def test_inline_md5_with_var_ref():
    from app.core.data_tools.inline_tools import DT_CACHE_KEY
    from app.core.variable_resolver import VariableResolver

    resolver = VariableResolver({"token": "hello", DT_CACHE_KEY: {}})
    out = resolver.replace_in_string("${{dt:md5|text=@token}}")
    assert out == "5d41402abc4b2a76b9719d911017c592"


def test_inline_uuid_cached_in_run():
    from app.core.data_tools.inline_tools import DT_CACHE_KEY
    from app.core.variable_resolver import VariableResolver

    cache: dict[str, str] = {}
    resolver = VariableResolver({DT_CACHE_KEY: cache})
    a = resolver.replace_in_string("${{dt:uuid}}")
    b = resolver.replace_in_string("${{dt:uuid}}")
    assert a == b
    assert len(a) == 36


def test_inline_uuid_shared_across_resolvers():
    from app.core.data_tools.inline_tools import DT_CACHE_KEY
    from app.core.variable_resolver import VariableResolver

    shared: dict[str, str] = {}
    r1 = VariableResolver({DT_CACHE_KEY: shared})
    r2 = VariableResolver({DT_CACHE_KEY: shared})
    u1 = r1.replace_in_string("${{dt:uuid}}")
    u2 = r2.replace_in_string("${{dt:uuid}}")
    assert u1 == u2


def test_inline_tool_invalid():
    from app.core.data_tools.errors import ToolExecutionError
    from app.core.data_tools.inline_tools import DT_CACHE_KEY
    from app.core.variable_resolver import VariableResolver

    resolver = VariableResolver({DT_CACHE_KEY: {}})
    with pytest.raises(ToolExecutionError):
        resolver.replace_in_string("${{dt:md5|text=@missing}}")


def test_inline_md5_quoted_email():
    from app.core.data_tools.inline_tools import DT_CACHE_KEY
    from app.core.variable_resolver import VariableResolver

    resolver = VariableResolver({DT_CACHE_KEY: {}})
    out = resolver.replace_in_string('${{dt:md5|text="test@163.com"}}')
    assert out == "5d41402abc4b2a76b9719d911017c592" or len(out) == 32
    # md5 of test@163.com
    import hashlib
    assert out == hashlib.md5("test@163.com".encode()).hexdigest()


def test_inline_md5_quoted_special_chars():
    from app.core.data_tools.inline_tools import DT_CACHE_KEY
    from app.core.variable_resolver import VariableResolver
    import hashlib

    resolver = VariableResolver({DT_CACHE_KEY: {}})
    raw = "hello|world=a"
    out = resolver.replace_in_string(f'${{dt:md5|text="{raw}"}}')
    assert out == hashlib.md5(raw.encode()).hexdigest()


def test_inline_md5_single_quoted():
    from app.core.data_tools.inline_tools import DT_CACHE_KEY, parse_dt_expression, resolve_dt_param_value
    from app.core.variable_resolver import VariableResolver
    import hashlib

    tool_id, params = parse_dt_expression("md5|text='a|b=c'")
    assert tool_id == "md5"
    assert resolve_dt_param_value(params["text"], lambda _: None) == "a|b=c"
    resolver = VariableResolver({DT_CACHE_KEY: {}})
    out = resolver.replace_in_string("${{dt:md5|text='a|b=c'}}")
    assert out == hashlib.md5(b"a|b=c").hexdigest()
