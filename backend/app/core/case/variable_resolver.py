"""变量解析器：与 UI Runner 对齐，支持动态变量、Faker 表达式与嵌套引用。"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional

try:
    from faker import Faker
except ImportError:  # pragma: no cover - 运行环境应安装 Faker
    Faker = None  # type: ignore

from app.modules.data_tools.errors import ToolExecutionError
from app.modules.data_tools.inline_tools import (
    DT_CACHE_KEY,
    DT_EXPR_PREFIX,
    execute_inline_tool,
    should_cache_inline_expression,
)

_VAR_PATTERN = re.compile(r"\$\{\{([^}]+)\}\}|\$\{([^}]+)\}|\{\{([^}]+)\}\}")
_FAKER_EXPR_PATTERN = re.compile(r"^faker\.(\w+)\((.*)\)$", re.IGNORECASE)


def _placeholder_forms(key: str) -> set[str]:
    k = (key or "").strip()
    if not k:
        return set()
    return {f"${{{{{k}}}}}", f"${{{k}}}", f"{{{{{k}}}}}"}


def is_self_referential_value(key: str, value: Any) -> bool:
    """环境变量写成 cookie=${{cookie}} 这类自引用。"""
    if not isinstance(value, str):
        return False
    return value.strip() in _placeholder_forms(key)


class VariableResolver:
    """接口/UI 共用的变量解析逻辑。"""

    _BUILTIN_GENERATORS = (
        "random_name",
        "random_phone",
        "random_email",
        "random_address",
        "random_company",
        "random_int",
        "random_str",
        "timestamp",
        "now_time",
        "today",
    )

    _FRESH_BUILTIN_KEYS = frozenset({"timestamp", "now_time", "today"})

    def __init__(self, global_vars: Optional[Dict[str, Any]] = None):
        from app.core.shared.global_vars_validate import flatten_global_vars

        raw = dict(global_vars or {})
        # 套件级 dt 缓存必须保留同一 dict 引用，不能被 flatten 成字符串或丢弃
        shared_dt_cache = raw.get(DT_CACHE_KEY)
        self._global_vars = flatten_global_vars(raw)
        self._cache: Dict[str, Any] = {}
        self._resolving: set[str] = set()
        self._faker = Faker("zh_CN") if Faker else None
        if isinstance(shared_dt_cache, dict):
            self._global_vars[DT_CACHE_KEY] = shared_dt_cache
        elif DT_CACHE_KEY not in self._global_vars or not isinstance(self._global_vars.get(DT_CACHE_KEY), dict):
            self._global_vars[DT_CACHE_KEY] = {}

    @staticmethod
    def _dt_tool_id(expr: str) -> str:
        raw = (expr or "").strip()
        if raw.startswith(DT_EXPR_PREFIX):
            raw = raw[len(DT_EXPR_PREFIX):]
        return raw.split("|", 1)[0].strip()

    def get(self, key: str) -> Any:
        if key in self._cache:
            return self._cache[key]

        # 循环引用（如 cookie=${{cookie}}）时直接断开，避免 RecursionError
        if key in self._resolving:
            return None

        if key.startswith(DT_EXPR_PREFIX):
            self._resolving.add(key)
            try:
                value = self._resolve_inline_tool(key)
            finally:
                self._resolving.discard(key)
            # 当前时间类 / 留空基准的 date_format·date_add：每次解析取新值
            if should_cache_inline_expression(key):
                self._cache[key] = value
            return value

        if key in self._global_vars:
            self._resolving.add(key)
            try:
                raw = self._global_vars[key]
                if is_self_referential_value(key, raw):
                    value = None
                else:
                    value = self._resolve_raw_value(raw)
                    if is_self_referential_value(key, value):
                        value = None
            finally:
                self._resolving.discard(key)
            self._cache[key] = value
            return value

        value = self._generate_dynamic(key)
        if value is not None:
            if key not in self._FRESH_BUILTIN_KEYS:
                self._cache[key] = value
            return value

        return None

    def replace_in_string(self, text: str) -> str:
        if not isinstance(text, str) or not text:
            return text

        for _ in range(10):
            new_text = _VAR_PATTERN.sub(self._replacer, text)
            if new_text == text:
                break
            text = new_text
        return text

    def get_resolved_snapshot(self) -> Dict[str, Any]:
        """返回当前执行过程中已解析/生成的变量，便于报告展示。"""
        snapshot = {
            k: v for k, v in self._global_vars.items()
            if k != DT_CACHE_KEY
        }
        snapshot.update(self._cache)
        return snapshot

    def _replacer(self, match: re.Match) -> str:
        var_name = (match.group(1) or match.group(2) or match.group(3) or "").strip()
        if not var_name:
            return match.group(0)
        try:
            value = self.get(var_name)
        except ToolExecutionError:
            raise
        if value is not None:
            return str(value)
        return match.group(0)

    def _lookup_binding(self, key: str) -> Any:
        """解析内联工具参数 @var 时使用的变量查找（不触发 dt 表达式）。"""
        if not key or key == DT_CACHE_KEY:
            return None
        if key in self._cache:
            return self._cache[key]
        if key in self._resolving:
            return None
        if key in self._global_vars:
            self._resolving.add(key)
            try:
                raw = self._global_vars[key]
                if is_self_referential_value(key, raw):
                    value = None
                else:
                    value = self._resolve_raw_value(raw)
                    if is_self_referential_value(key, value):
                        value = None
            finally:
                self._resolving.discard(key)
            self._cache[key] = value
            return value
        return self._generate_dynamic(key)

    def _resolve_inline_tool(self, expr: str) -> str:
        cache = self._global_vars.get(DT_CACHE_KEY)
        if not isinstance(cache, dict):
            cache = {}
            self._global_vars[DT_CACHE_KEY] = cache
        return execute_inline_tool(expr, self._lookup_binding, cache)

    def _resolve_raw_value(self, raw: Any) -> Any:
        if raw is None or not isinstance(raw, str):
            return raw

        faker_value = self._eval_faker_expression(raw)
        if faker_value is not None:
            return faker_value

        if "${{" in raw or "${" in raw or "{{" in raw:
            return self.replace_in_string(raw)

        return raw

    def _generate_dynamic(self, key: str) -> Any:
        if not self._faker:
            return self._generate_builtin_without_faker(key)

        generators = {
            "random_name": lambda: self._faker.name(),
            "random_phone": lambda: self._faker.phone_number(),
            "random_email": lambda: self._faker.email(),
            "random_address": lambda: self._faker.address(),
            "random_company": lambda: self._faker.company(),
            "random_int": lambda: self._faker.random_int(min=1000, max=9999),
            "timestamp": lambda: str(int(time.time())),
            "now_time": lambda: time.strftime("%Y-%m-%d %H:%M:%S"),
            "today": lambda: time.strftime("%Y-%m-%d"),
        }
        generator = generators.get(key)
        return generator() if generator else None

    @staticmethod
    def _generate_builtin_without_faker(key: str) -> Any:
        if key == "random_int":
            import random

            return random.randint(1000, 9999)
        if key == "timestamp":
            return str(int(time.time()))
        if key == "now_time":
            return time.strftime("%Y-%m-%d %H:%M:%S")
        if key == "today":
            return time.strftime("%Y-%m-%d")
        return None

    def _eval_faker_expression(self, expr: str) -> Any:
        if not self._faker:
            return None

        match = _FAKER_EXPR_PATTERN.match(expr.strip())
        if not match:
            return None

        method_name = match.group(1)
        args_str = (match.group(2) or "").strip()
        method = getattr(self._faker, method_name, None)
        if not callable(method):
            return None

        args, kwargs = self._parse_faker_args(args_str)
        try:
            return method(*args, **kwargs)
        except TypeError:
            return None

    @staticmethod
    def _parse_faker_args(args_str: str):
        args = []
        kwargs = {}
        if not args_str:
            return args, kwargs

        for part in args_str.split(","):
            token = part.strip()
            if not token:
                continue
            if "=" in token:
                key, value = token.split("=", 1)
                kwargs[key.strip()] = VariableResolver._parse_literal(value.strip())
            else:
                args.append(VariableResolver._parse_literal(token))
        return args, kwargs

    @staticmethod
    def _parse_literal(raw: str) -> Any:
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            return raw[1:-1]
        if raw.lower() in {"true", "false"}:
            return raw.lower() == "true"
        try:
            return int(raw)
        except ValueError:
            try:
                return float(raw)
            except ValueError:
                return raw
