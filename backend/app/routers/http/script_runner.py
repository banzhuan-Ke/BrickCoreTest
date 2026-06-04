"""
RestrictedPython 脚本沙箱执行器。

脚本语言：Python（RestrictedPython 受限沙箱）

脚本执行上下文（可用变量）：
  - variables: dict  — 变量字典，可读写，修改后会传回调用方
  - response:  dict  — 仅后置脚本可用，格式：
                       {"status_code": 200, "body": {...}, "headers": {...}}
  - timestamp()      — 返回当前 Unix 时间戳（int），替代 __import__('time')
  - print(...)       — 输出到脚本日志，可在报告中查看

安全限制（RestrictedPython 保证）：
  - 禁止 import os / sys / subprocess 等危险模块
  - 禁止文件操作 (open)
  - 禁止 exec / eval / compile
  - 禁止 __import__、双下划线名称等
"""

import time

try:
    from RestrictedPython import compile_restricted, safe_builtins, safe_globals
    from RestrictedPython.Guards import safer_getattr, guarded_iter_unpack_sequence
    from RestrictedPython.Eval import default_guarded_getitem, default_guarded_getiter
    from RestrictedPython.PrintCollector import PrintCollector

    _RESTRICTED_PYTHON_AVAILABLE = True
except ImportError:
    _RESTRICTED_PYTHON_AVAILABLE = False


def _write_guard(obj):
    return obj


def _inplacevar_guard(op, val, expr):
    return val


def _build_script_globals():
    """构建 RestrictedPython 运行所需的 globals（含 guards）。"""
    globals_dict = dict(safe_globals)
    globals_dict["_print_"] = PrintCollector
    globals_dict["__builtins__"] = safe_builtins
    globals_dict["_getattr_"] = safer_getattr
    globals_dict["_getitem_"] = default_guarded_getitem
    globals_dict["_getiter_"] = default_guarded_getiter
    globals_dict["_iter_unpack_sequence_"] = guarded_iter_unpack_sequence
    globals_dict["_write_"] = _write_guard
    globals_dict["_inplacevar_"] = _inplacevar_guard
    globals_dict["timestamp"] = lambda: int(time.time())
    return globals_dict


def _collect_print_logs(local_vars: dict) -> list:
    printer = local_vars.get("_print")
    if printer is None:
        return []
    text = str(printer())
    if not text:
        return []
    return [line for line in text.splitlines()]


def run_script(script: str, variables: dict, response: dict = None) -> dict:
    """
    在受限沙箱中执行 Python 脚本。

    Args:
        script:    要执行的脚本文本
        variables: 当前变量字典（脚本可读写）
        response:  响应上下文（仅后置脚本传入），格式：
                   {"status_code": int, "body": any, "headers": dict}

    Returns:
        {
            "variables": dict,  # 脚本执行后的变量字典（可能已被脚本修改）
            "logs": list[str],  # print() 输出的内容
            "error": str | None # 脚本执行异常信息，None 表示正常
        }
    """
    if not script or not script.strip():
        return {"variables": variables, "logs": [], "error": None}

    if not _RESTRICTED_PYTHON_AVAILABLE:
        return {
            "variables": variables,
            "logs": [],
            "error": "RestrictedPython 未安装，无法执行脚本。请运行: pip install RestrictedPython>=7.1",
        }

    local_vars = {
        "variables": dict(variables),
        "response": response or {},
        "printed": "",
    }

    script_globals = _build_script_globals()

    try:
        code = compile_restricted(script, filename="<script>", mode="exec")
        exec(code, script_globals, local_vars)  # noqa: S102
        return {
            "variables": local_vars.get("variables", variables),
            "logs": _collect_print_logs(local_vars),
            "error": None,
        }
    except SyntaxError as e:
        return {
            "variables": variables,
            "logs": _collect_print_logs(local_vars),
            "error": f"脚本语法错误: {e}",
        }
    except Exception as e:
        return {
            "variables": variables,
            "logs": _collect_print_logs(local_vars),
            "error": f"脚本执行错误: {type(e).__name__}: {e}",
        }
