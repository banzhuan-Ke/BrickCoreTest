"""
操作日志中间件
"""
import json
import re
from fastapi import Request
from app.models.sys import OperationLog
from app.core.platform.config import MCP_HTTP_PATH

# 需要脱敏的字段名
SENSITIVE_FIELDS = {"password", "password_confirm", "admin_password", "token", "secret", "access_token"}

# 体积过大、不应完整入库/下发的字段（如 Runner 屏幕截图 base64）
BULK_PARAM_FIELDS = frozenset({
    "image_base64",
    "screenshot",
    "body",
    "html",
    "video",
    "video_url",
    "content",
    "result_data",
    "raw_actions",
    "steps",
})

# 单字段字符串最大保留长度（超出则省略）
MAX_PARAM_STRING_LEN = 500

_GENERIC_ACTIONS = frozenset({"创建", "更新", "删除", "修改", "操作"})

# 路由映射：(method, 正则pattern, action, module, path_name)
ROUTE_MAPPING = [
    # 系统管理
    ("POST", r"^/sys/users/login$", "用户登录", "系统管理", "用户登录"),
    ("POST", r"^/sys/users$", "创建用户", "系统管理", "创建用户"),
    ("PUT", r"^/sys/users/\d+$", "更新用户", "系统管理", "更新用户"),
    ("DELETE", r"^/sys/users/\d+$", "删除用户", "系统管理", "删除用户"),
    ("PUT", r"^/sys/users/\d+/active$", "启用/停用用户", "系统管理", "启用/停用用户"),
    ("POST", r"^/sys/roles$", "创建角色", "系统管理", "创建角色"),
    ("PUT", r"^/sys/roles/\d+$", "更新角色", "系统管理", "更新角色"),
    ("DELETE", r"^/sys/roles/\d+$", "删除角色", "系统管理", "删除角色"),
    ("POST", r"^/sys/projects$", "创建项目", "项目配置", "创建项目"),
    ("PUT", r"^/sys/projects/\d+$", "更新项目", "项目配置", "更新项目"),
    ("PUT", r"^/sys/projects/\d+/default$", "设为默认项目", "项目配置", "设为默认项目"),
    ("DELETE", r"^/sys/projects/\d+$", "删除项目", "项目配置", "删除项目"),
    ("POST", r"^/sys/envs$", "创建环境", "项目配置", "创建环境"),
    ("PUT", r"^/sys/envs/\d+$", "更新环境", "项目配置", "更新环境"),
    ("DELETE", r"^/sys/envs/\d+$", "删除环境", "项目配置", "删除环境"),
    ("POST", r"^/sys/catalogs$", "创建目录", "项目配置", "创建目录"),
    ("PUT", r"^/sys/catalogs/\d+$", "更新目录", "项目配置", "更新目录"),
    ("DELETE", r"^/sys/catalogs/\d+$", "删除目录", "项目配置", "删除目录"),
    ("PUT", r"^/sys/mcp/config$", "更新MCP配置", "系统管理", "更新MCP配置"),
    ("POST", r"^/sys/devices$", "创建设备", "Web自动化", "创建设备"),
    ("PUT", r"^/sys/devices/[^/]+$", "更新设备", "Web自动化", "更新设备"),
    ("POST", r"^/sys/devices/[^/]+/stop$", "停止Runner设备", "Web自动化", "停止Runner设备"),
    ("DELETE", r"^/sys/devices/[^/]+$", "删除设备", "Web自动化", "删除设备"),
    ("DELETE", r"^/sys/operation-logs$", "删除操作日志", "系统管理", "批量删除操作日志"),

    # Runner 客户端（Web 自动化执行器）
    ("POST", r"^/runner/connect$", "Runner上线", "Web自动化", "Runner客户端上线"),
    ("POST", r"^/runner/disconnect$", "Runner下线", "Web自动化", "Runner客户端下线"),
    ("POST", r"^/runner/engine-ready$", "Runner引擎就绪", "Web自动化", "Runner引擎就绪"),
    ("POST", r"^/runner/results$", "回传执行结果", "Web自动化", "Runner回传UI执行结果"),
    ("POST", r"^/runner/results/internal$", "回传执行结果", "Web自动化", "Runner回传UI执行结果(内部)"),
    ("POST", r"^/runner/device-log$", "上报设备日志", "Web自动化", "Runner上报设备日志"),
    ("POST", r"^/runner/device-log/batch$", "批量上报设备日志", "Web自动化", "Runner批量上报设备日志"),
    ("POST", r"^/runner/device-screen$", "上报设备屏幕", "Web自动化", "Runner上报设备屏幕"),
    ("POST", r"^/runner/upload/presign$", "获取上传凭证", "Web自动化", "Runner获取MinIO上传凭证"),

    # Web 自动化
    ("POST", r"^/ui/cases$", "创建用例", "Web自动化", "创建UI用例"),
    ("PUT", r"^/ui/cases/\d+$", "更新用例", "Web自动化", "更新UI用例"),
    ("DELETE", r"^/ui/cases/\d+$", "删除用例", "Web自动化", "删除UI用例"),
    ("POST", r"^/ui/cases/\d+/copy$", "复制用例", "Web自动化", "复制UI用例"),
    ("POST", r"^/ui/suites$", "创建套件", "Web自动化", "创建UI套件"),
    ("PUT", r"^/ui/suites/\d+$", "更新套件", "Web自动化", "更新UI套件"),
    ("DELETE", r"^/ui/suites/\d+$", "删除套件", "Web自动化", "删除UI套件"),
    ("POST", r"^/ui/suites/\d+/cases$", "套件添加用例", "Web自动化", "UI套件添加用例"),
    ("POST", r"^/ui/tasks$", "创建计划", "Web自动化", "创建UI执行计划"),
    ("PUT", r"^/ui/tasks/\d+$", "更新计划", "Web自动化", "更新UI执行计划"),
    ("DELETE", r"^/ui/tasks/\d+$", "删除计划", "Web自动化", "删除UI执行计划"),
    ("POST", r"^/ui/exec/cases/\d+$", "执行用例", "Web自动化", "执行UI用例"),
    ("POST", r"^/ui/exec/suites/\d+$", "执行套件", "Web自动化", "执行UI套件"),
    ("POST", r"^/ui/exec/tasks/\d+$", "执行任务", "Web自动化", "执行UI计划"),
    ("POST", r"^/ui/exec/stop/\d+$", "停止执行", "Web自动化", "停止UI计划执行"),
    ("POST", r"^/ui/exec/stop/suite/\d+$", "停止执行", "Web自动化", "停止UI套件执行"),
    ("POST", r"^/ui/exec/stop/case/\d+$", "停止执行", "Web自动化", "停止UI用例执行"),
    ("DELETE", r"^/ui/records/tasks/\d+$", "删除任务记录", "Web自动化", "删除UI任务记录"),
    ("DELETE", r"^/ui/records/suites/\d+$", "删除套件记录", "Web自动化", "删除UI套件记录"),
    ("DELETE", r"^/ui/records/cases/\d+$", "删除用例记录", "Web自动化", "删除UI用例记录"),
    ("POST", r"^/schedule/jobs$", "创建定时任务", "Web自动化", "创建UI定时任务"),
    ("PUT", r"^/schedule/jobs/[^/]+$", "更新定时任务", "Web自动化", "更新UI定时任务"),
    ("DELETE", r"^/schedule/jobs/[^/]+$", "删除定时任务", "Web自动化", "删除UI定时任务"),
    ("POST", r"^/schedule/jobs/[^/]+/switch$", "切换定时任务状态", "Web自动化", "切换UI定时任务状态"),

    # 接口自动化
    ("POST", r"^/api-module/definition$", "创建接口", "接口自动化", "创建接口定义"),
    ("PUT", r"^/api-module/definition/\d+$", "更新接口", "接口自动化", "更新接口定义"),
    ("DELETE", r"^/api-module/definition/\d+$", "删除接口", "接口自动化", "删除接口定义"),
    ("POST", r"^/api-module/definition/batch-delete$", "批量删除接口", "接口自动化", "批量删除接口定义"),
    ("POST", r"^/api-module/debug$", "接口调试", "接口自动化", "接口在线调试"),
    ("POST", r"^/api-module/case$", "创建接口用例", "接口自动化", "创建接口用例"),
    ("PUT", r"^/api-module/case/\d+$", "更新接口用例", "接口自动化", "更新接口用例"),
    ("DELETE", r"^/api-module/case/\d+$", "删除接口用例", "接口自动化", "删除接口用例"),
    ("POST", r"^/api-module/case/\d+/run$", "执行接口用例", "接口自动化", "执行接口用例"),
    ("POST", r"^/api-module/case/\d+/copy$", "复制接口用例", "接口自动化", "复制接口用例"),
    ("POST", r"^/api-module/suite$", "创建接口套件", "接口自动化", "创建接口套件"),
    ("PUT", r"^/api-module/suite/\d+$", "更新接口套件", "接口自动化", "更新接口套件"),
    ("DELETE", r"^/api-module/suite/\d+$", "删除接口套件", "接口自动化", "删除接口套件"),
    ("POST", r"^/api-module/suite/\d+/run$", "执行接口套件", "接口自动化", "执行接口套件"),
    ("POST", r"^/api-module/batch-run$", "批量执行用例", "接口自动化", "批量执行接口用例"),
    ("POST", r"^/api-module/plan$", "创建测试计划", "接口自动化", "创建接口测试计划"),
    ("PUT", r"^/api-module/plan/\d+$", "更新测试计划", "接口自动化", "更新接口测试计划"),
    ("DELETE", r"^/api-module/plan/\d+$", "删除测试计划", "接口自动化", "删除接口测试计划"),
    ("POST", r"^/api-module/plan/\d+/run$", "执行测试计划", "接口自动化", "执行接口测试计划"),
    ("POST", r"^/api-module/import/swagger$", "导入Swagger", "接口自动化", "导入Swagger文档"),
    ("POST", r"^/api-module/import/postman$", "导入Postman", "接口自动化", "导入Postman集合"),
    ("POST", r"^/api-module/import/curl$", "导入Curl", "接口自动化", "导入Curl命令"),
    ("DELETE", r"^/api-module/records/\d+$", "删除接口执行记录", "接口自动化", "删除接口执行记录"),
    ("POST", r"^/api-module/cron-jobs$", "创建接口定时任务", "接口自动化", "创建接口定时任务"),
    ("PUT", r"^/api-module/cron-jobs/\d+$", "更新接口定时任务", "接口自动化", "更新接口定时任务"),
    ("DELETE", r"^/api-module/cron-jobs/\d+$", "删除接口定时任务", "接口自动化", "删除接口定时任务"),
    ("POST", r"^/api-module/header-templates$", "创建Header模板", "接口自动化", "创建Header模板"),
    ("PUT", r"^/api-module/header-templates/\d+$", "更新Header模板", "接口自动化", "更新Header模板"),
    ("DELETE", r"^/api-module/header-templates/\d+$", "删除Header模板", "接口自动化", "删除Header模板"),
    ("POST", r"^/api-module/header-templates/\d+/set-default$", "设为默认Header模板", "接口自动化", "设为默认Header模板"),

    # AI 测试
    ("POST", r"^/ai/assistant/chat$", "助手对话", "AI测试", "AI助手对话"),
    ("POST", r"^/ai/assistant/confirm$", "助手确认执行", "AI测试", "AI助手确认执行"),
    ("POST", r"^/ai/assistant/sessions$", "创建助手会话", "AI测试", "创建AI助手会话"),
    ("PATCH", r"^/ai/assistant/sessions/\d+$", "重命名助手会话", "AI测试", "重命名AI助手会话"),
    ("DELETE", r"^/ai/assistant/sessions/\d+$", "删除助手会话", "AI测试", "删除AI助手会话"),
    ("POST", r"^/ai/generate/api-case$", "AI生成接口用例", "AI测试", "AI生成接口用例"),
    ("POST", r"^/ai/generate/api-case/import$", "导入AI接口用例", "AI测试", "导入AI接口用例"),
    ("POST", r"^/api-module/mock/ai-generate$", "AI生成Mock响应", "接口自动化", "AI生成Mock响应"),
    ("POST", r"^/ai/generate/ui-case$", "AI生成UI用例", "AI测试", "AI生成UI用例"),
    ("POST", r"^/ai/analyze/failure$", "AI失败分析", "AI测试", "AI失败分析"),
    ("POST", r"^/ai/analyze/failure/batch$", "AI批量失败分析", "AI测试", "AI批量失败分析"),
    ("POST", r"^/ai/analyze/report-summary$", "AI报告摘要", "AI测试", "AI报告摘要"),
    ("POST", r"^/ai/chat/report-summary$", "AI报告摘要", "AI测试", "AI报告摘要"),
    ("POST", r"^/ai/requirements/upload$", "上传需求文档", "AI测试", "上传需求文档"),
    ("POST", r"^/ai/requirements/\d+/generate-cases$", "AI生成需求用例", "AI测试", "AI生成需求用例"),
    ("POST", r"^/ai/configs$", "创建AI模型配置", "AI测试", "创建AI模型配置"),
    ("PUT", r"^/ai/configs/\d+$", "更新AI模型配置", "AI测试", "更新AI模型配置"),
    ("DELETE", r"^/ai/configs/\d+$", "删除AI模型配置", "AI测试", "删除AI模型配置"),
    ("POST", r"^/ai/record/start$", "启动AI录制", "AI测试", "启动AI录制"),
    ("POST", r"^/ai/record/optimize-steps$", "AI优化用例步骤", "AI测试", "AI优化用例步骤"),
    ("POST", r"^/ai/record/\d+/apply$", "应用录制结果", "AI测试", "应用AI录制结果"),
    ("POST", r"^/ai/record/\d+/optimize$", "AI优化录制步骤", "AI测试", "AI优化录制步骤"),

    # 迭代测试资料库
    ("POST", r"^/ai/knowledge/folders$", "创建资料文件夹", "迭代测试资料库", "创建迭代文件夹"),
    ("PUT", r"^/ai/knowledge/folders/\d+$", "更新资料文件夹", "迭代测试资料库", "更新迭代文件夹"),
    ("DELETE", r"^/ai/knowledge/folders/\d+$", "删除资料文件夹", "迭代测试资料库", "删除迭代文件夹"),
    ("POST", r"^/ai/knowledge/documents/upload$", "上传资料文档", "迭代测试资料库", "上传资料文档"),
    ("POST", r"^/ai/knowledge/documents/archive-from-requirement$", "需求归档", "迭代测试资料库", "需求归档到资料库"),
    ("POST", r"^/ai/knowledge/documents/archive-from-text$", "文本归档", "迭代测试资料库", "文本归档到资料库"),
    ("DELETE", r"^/ai/knowledge/documents/\d+$", "删除资料文档", "迭代测试资料库", "删除资料文档"),
    ("POST", r"^/ai/knowledge/documents/\d+/reparse$", "重新解析文档", "迭代测试资料库", "重新解析资料文档"),
    ("POST", r"^/ai/knowledge/documents/reparse$", "批量重新解析文档", "迭代测试资料库", "批量重新解析资料文档"),
    ("POST", r"^/ai/knowledge/documents/\d+/reindex-rag$", "重建RAG索引", "迭代测试资料库", "重建资料RAG索引"),
    ("POST", r"^/ai/knowledge/documents/\d+/rebuild-digest$", "重建摘要缓存", "迭代测试资料库", "重建资料摘要缓存"),
    ("POST", r"^/ai/knowledge/retrieve$", "检索资料库", "迭代测试资料库", "RAG检索资料库"),
    ("POST", r"^/ai/knowledge/iteration-reports$", "生成迭代报告", "迭代测试资料库", "生成迭代测试报告"),
    ("POST", r"^/ai/knowledge/iteration-reports/\d+/retry$", "重试报告生成", "迭代测试资料库", "重试迭代报告生成"),
    ("PUT", r"^/ai/knowledge/settings$", "更新资料库配置", "迭代测试资料库", "更新资料库生成配置"),

    # 性能测试
    ("POST", r"^/perf/scenes$", "创建压测场景", "性能测试", "创建压测场景"),
    ("PUT", r"^/perf/scenes/\d+$", "更新压测场景", "性能测试", "更新压测场景"),
    ("DELETE", r"^/perf/scenes/\d+$", "删除压测场景", "性能测试", "删除压测场景"),
    ("POST", r"^/perf/scenes/\d+/run$", "启动压测", "性能测试", "启动压测"),
    ("POST", r"^/perf/workers/register$", "压测Worker上线", "性能测试", "压测Worker注册上线"),
    ("POST", r"^/perf/workers/unregister$", "压测Worker下线", "性能测试", "压测Worker主动下线"),
    ("POST", r"^/perf/workers/heartbeat$", "压测Worker心跳", "性能测试", "压测Worker心跳"),
    ("POST", r"^/perf/workers/\d+/report$", "压测Worker秒级上报", "性能测试", "压测Worker秒级上报"),
    ("POST", r"^/perf/workers/\d+/final$", "压测Worker最终报告", "性能测试", "压测Worker最终报告"),
]


def resolve_route_info(method: str, path: str) -> tuple[str, str, str]:
    """根据请求方法和路径解析 (action, module, path_name)。"""
    for m, pattern, action, module, path_name in ROUTE_MAPPING:
        if m == method and re.search(pattern, path):
            return action, module, path_name
    action, module = _resolve_action_and_module_fallback(method, path)
    path_name = _infer_path_name(method, path, action, module)
    return action, module, path_name


def _resolve_action_and_module(method: str, path: str) -> tuple[str, str]:
    action, module, _ = resolve_route_info(method, path)
    return action, module


def _resolve_action_and_module_fallback(method: str, path: str) -> tuple[str, str]:
    """fallback：尝试根据 path 前缀判断模块"""
    if path.startswith("/sys"):
        module = "系统管理"
    elif path.startswith("/ai"):
        module = "AI测试"
    elif path.startswith("/perf"):
        module = "性能测试"
    elif path.startswith("/runner") or path.startswith("/ui") or path.startswith("/schedule"):
        module = "Web自动化"
    elif path.startswith("/api-module"):
        module = "接口自动化"
    else:
        module = "其他"
    if path.startswith("/ai/"):
        tail = path.rstrip("/").split("/")[-1].replace("-", "_")
        ai_action_map = {
            "chat": "助手对话",
            "confirm": "助手确认执行",
            "api_case": "AI生成接口用例",
            "ui_case": "AI生成UI用例",
            "failure": "AI失败分析",
            "report_summary": "AI报告摘要",
            "generate_cases": "AI生成需求用例",
            "upload": "上传需求文档",
            "optimize": "AI优化录制步骤",
        }
        if tail in ai_action_map:
            return ai_action_map[tail], module
    if method == "POST":
        action = "创建"
    elif method == "PUT":
        action = "更新"
    elif method == "DELETE":
        action = "删除"
    elif method == "PATCH":
        action = "修改"
    else:
        action = "操作"
    return action, module


def _infer_path_name(method: str, path: str, action: str, module: str) -> str:
    if action not in _GENERIC_ACTIONS:
        return action
    normalized = re.sub(r"/\d+", "/{id}", path.rstrip("/"))
    segment = path.rstrip("/").split("/")[-1] if path else ""
    runner_labels = {
        "connect": "Runner客户端上线",
        "disconnect": "Runner客户端下线",
        "engine-ready": "Runner引擎就绪",
        "results": "Runner回传UI执行结果",
        "device-log": "Runner上报设备日志",
        "batch": "Runner批量上报设备日志",
        "device-screen": "Runner上报设备屏幕",
        "presign": "Runner获取MinIO上传凭证",
    }
    if path.startswith("/runner/"):
        if segment in runner_labels:
            return runner_labels[segment]
        return f"Runner/{segment or '接口'}"
    api_labels = {
        "definition": "接口定义",
        "case": "接口用例",
        "suite": "接口套件",
        "plan": "接口测试计划",
        "debug": "接口在线调试",
        "mock": "Mock接口",
    }
    parts = normalized.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "api-module" and parts[1] in api_labels:
        label = api_labels[parts[1]]
        if action == "创建":
            return f"创建{label}"
        if action == "更新":
            return f"更新{label}"
        if action == "删除":
            return f"删除{label}"
        return label
    if segment:
        perf_worker_labels = {
            "register": "压测Worker注册上线",
            "unregister": "压测Worker主动下线",
            "heartbeat": "压测Worker心跳",
            "report": "压测Worker秒级上报",
            "final": "压测Worker最终报告",
        }
        if path.startswith("/perf/workers/"):
            if segment in perf_worker_labels:
                return perf_worker_labels[segment]
            return f"压测Worker/{segment}"
        return f"{module}-{action}({segment})"
    return f"{module}-{action}"


def _truncate_large_value(key: str, value):
    """压缩超大字段，避免操作日志撑爆数据库与前端渲染。"""
    if isinstance(value, str):
        if key in BULK_PARAM_FIELDS or len(value) > MAX_PARAM_STRING_LEN:
            return f"[omitted, length={len(value)}]"
        return value
    if isinstance(value, dict):
        return compact_log_params(value)
    if isinstance(value, list):
        if len(value) > 20:
            return f"[omitted, list_length={len(value)}]"
        return [_truncate_large_value(key, item) for item in value]
    return value


def compact_log_params(data) -> dict | list | str | int | float | bool | None:
    """递归压缩请求参数中的大字段。"""
    if not isinstance(data, dict):
        return data
    result = {}
    for k, v in data.items():
        if k in SENSITIVE_FIELDS:
            result[k] = "***"
        elif isinstance(v, dict):
            result[k] = compact_log_params(v)
        elif isinstance(v, list):
            if len(v) > 20:
                result[k] = f"[omitted, list_length={len(v)}]"
            else:
                result[k] = [_truncate_large_value(k, item) for item in v]
        else:
            result[k] = _truncate_large_value(k, v)
    return result


def _mask_sensitive_data(data: dict) -> dict:
    """脱敏处理（兼容旧调用）。"""
    return compact_log_params(data) if isinstance(data, dict) else data


def _get_client_ip(request: Request) -> str:
    """获取客户端真实 IP"""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        return x_real_ip
    return request.client.host if request.client else ""


async def _parse_request_body(request: Request) -> dict:
    """解析请求体，仅对 application/json 做处理"""
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return {}
    try:
        body = await request.body()
        if not body:
            return {}
        data = json.loads(body)
        if isinstance(data, dict):
            return _mask_sensitive_data(data)
        return compact_log_params({"data": data}) if data is not None else {}
    except Exception:
        return {}


async def _resolve_perf_worker_user(params: dict, path: str) -> tuple[int, str] | None:
    """从压测 Worker 请求体中的 token 解析节点名称（无用户 JWT 的 Worker 脚本调用）。"""
    token = params.get("token")
    if not token or not path.startswith("/perf/workers"):
        return None

    from app.models.perf import PerfWorker

    worker = None
    worker_id = params.get("worker_id")
    if worker_id is not None:
        try:
            worker = await PerfWorker.get_or_none(id=int(worker_id), token=token)
        except (TypeError, ValueError):
            worker = None

    if not worker and path.endswith("/unregister"):
        host = str(params.get("host") or "").strip()
        q = PerfWorker.filter(token=token)
        if host:
            q = q.filter(host=host)
        worker = await q.order_by("-id").first()

    if not worker and path.endswith("/register"):
        host = str(params.get("host") or "").strip()
        q = PerfWorker.filter(token=token)
        if host:
            q = q.filter(host=host)
        worker = await q.order_by("-id").first()

    if not worker:
        worker = await PerfWorker.filter(token=token).order_by("-id").first()

    if not worker:
        return None

    label = (worker.name or "").strip() or (worker.host or "").strip() or f"#{worker.id}"
    return 0, f"压测Worker·{label}"


async def _resolve_log_user(request: Request, path: str, params: dict) -> tuple[int, str]:
    """解析操作人：支持登录用户 JWT、Runner 客户端 token、压测 Worker token。"""
    if path in ("/sys/users/login", "/login") or path.endswith("/login"):
        if params.get("username"):
            return 0, str(params["username"])

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.platform.auth import verify_token

            token = auth_header.replace("Bearer ", "", 1).strip()
            payload = verify_token(token)
            uid = payload.get("id") or payload.get("user_id") or 0
            uname = payload.get("username") or payload.get("sub") or ""
            if uname:
                return int(uid or 0), str(uname)
        except Exception:
            pass

    runner_token = request.headers.get("x-runner-token") or request.headers.get("X-Runner-Token")
    if runner_token:
        try:
            from jose import jwt
            from app.core.platform.config import SECRET_KEY, ALGORITHM
            from app.models.sys import User

            data = jwt.decode(runner_token, SECRET_KEY, algorithms=[ALGORITHM])
            if data.get("typ") != "runner":
                raise ValueError("not runner token")
            user_id = int(data.get("user_id") or 0)
            device_id = str(data.get("device_id") or "").strip()
            if user_id:
                rows = await User.filter(id=user_id, is_del=False).values("id", "username")
                if rows:
                    uname = rows[0].get("username") or str(user_id)
                    if device_id:
                        return user_id, f"{uname}({device_id})"
                    return user_id, uname
            if device_id:
                return user_id, f"Runner设备({device_id})"
        except Exception:
            pass

    internal_token = request.headers.get("x-internal-token") or request.headers.get("X-Internal-Token")
    if internal_token:
        from app.core.platform.config import INTERNAL_API_KEY
        if internal_token == INTERNAL_API_KEY:
            return 0, "系统内部服务"

    perf_user = await _resolve_perf_worker_user(params, path)
    if perf_user:
        return perf_user

    return 0, "未知用户"


# 不需要记录日志的路径前缀或完整路径
SKIP_PATHS = {
    "/sys/users/token",
    "/sys/users/verify",
    "/sys/users/refresh",
    "/runner/heartbeat",
    "/runner/health",
    "/runner/version",
    "/runner/active-recording",
    "/login",  # 外部扫描/误配路径，非平台真实登录接口
    "/perf/workers/heartbeat",  # 压测 Worker 每 30s 心跳，无审计价值
    # Runner 高频上报：无审计价值且 params 体积巨大（尤其 image_base64）
    "/runner/device-screen",
    "/runner/device-log",
    "/runner/device-log/batch",
    # Runner 对象存储预签名：执行/上传极高频，无审计价值
    "/runner/upload/presign",
    "/runner/download/presign",
}
SKIP_PREFIXES = (
    "/static",
    "/swagger",
    "/redoc",
    "/openapi.json",
)
# 高频探活 / 机器上报，无审计价值
SKIP_PATH_REGEXES = (
    re.compile(r"^/ai/record/\d+/heartbeat$"),
    re.compile(r"^/perf/workers/\d+/report$"),  # 压测秒级上报
    re.compile(r"^/ui/debug/sessions/\d+/compare-steps$"),  # 交互调试轮询对比
    re.compile(r"^/ai/generate/locator-heal/internal$"),
)


def _should_skip_operation_log(path: str) -> bool:
    if path in SKIP_PATHS:
        return True
    if any(path.startswith(p) for p in SKIP_PREFIXES):
        return True
    if any(pat.match(path) for pat in SKIP_PATH_REGEXES):
        return True
    return path == MCP_HTTP_PATH or path.startswith(f"{MCP_HTTP_PATH}/")


class OperationLogMiddleware:
    """操作日志中间件：记录写操作请求"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        if _should_skip_operation_log(path):
            await self.app(scope, receive, send)
            return

        method = request.method
        if method not in ("POST", "PUT", "DELETE", "PATCH"):
            await self.app(scope, receive, send)
            return

        body = await request.body()
        # ASGI receive 只能完整交付一次 body；二次调用须返回空帧，避免下游重复拼接
        body_sent = False

        async def receive_wrapper():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        request_for_log = Request(scope, receive_wrapper)
        params = await _parse_request_body(request_for_log)
        # 日志解析已消费一次 receive；给下游再准备一份可回放的 body
        body_sent = False

        status_code = 200

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
            await send(message)

        await self.app(scope, receive_wrapper, send_wrapper)

        user_id, username = await _resolve_log_user(request, path, params)
        action, module, path_name = resolve_route_info(method, path)
        ip = _get_client_ip(request)

        try:
            await OperationLog.create(
                user_id=user_id,
                username=username,
                action=action,
                module=module,
                method=method,
                path=path,
                path_name=path_name,
                params=params,
                ip=ip,
                status_code=status_code,
            )
        except Exception:
            pass
