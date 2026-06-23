"""
Runner 客户端运行要求、录制提示与排查摘要（供设备管理页与 API 展示）
"""
from __future__ import annotations

from typing import Any

from app.core import config as settings


def build_runner_notices() -> dict[str, Any]:
    latest = settings.RUNNER_CLIENT_VERSION_LATEST
    minimum = settings.RUNNER_CLIENT_VERSION_MIN
    return {
        "version": latest,
        "minimum_version": minimum,
        "runtime_requirements": [
            "Windows 10/11 x64；安装包已内置 Python 3.11 与 Playwright Chromium，测试机无需单独装 Python",
            "打包版需完整解压：BrickCoreRunner.exe、_internal/、runner/、VERSION.txt 必须在同一目录",
            "运行库：MSVCP140.dll / VCRUNTIME140.dll（安装包已内置；若 greenlet DLL 报错请重新下载最新 zip）",
            "网络：测试机可访问平台 80 端口；MQ 25672、Redis 26379、MinIO 9200（按环境放行）",
            "磁盘：安装包约 800MB；录制截图会临时占用 runner 缓存目录",
        ],
        "dev_mode_requirements": [
            "开发调试请使用 runner_client/start-client.bat，会自动创建 runner_client/venv 与 runner/venv",
            "本机需安装 Python 3.11 并加入 PATH；首次需 playwright install chromium（开发 venv 内）",
            "禁止与 PyCharm 直接 Run main.py 混用：同一 device_id 只能有一个 Runner 子进程",
        ],
        "recording_tips": [
            "录制时浏览器会蓝框高亮即将录制的元素；点击后顶部 3 秒内可点「撤销」",
            "顶栏图标按钮请点在文字或图标+文字整块上；常见词（设置/登录）优先选「区域链式」定位",
            "建议业务页面为关键按钮添加 data-testid，录制会自动优先生成该定位",
            "导入前查看步骤「质量」列：风险行可在定位下拉里切换备选；AI 优化会从候选中智能重选默认定位",
        ],
        "troubleshooting": [
            {
                "title": "No module named 'jsonpath_ng' / 依赖不完整",
                "detail": "在 runner 目录执行 venv\\Scripts\\pip install -r requirements.txt，或重跑 start-client.bat；客户端下线后再上线。",
            },
            {
                "title": "runner venv / pyvenv.cfg 报错",
                "detail": "开发模式勿混用打包版 runner/venv；删除 runner/venv 后重新运行 start-client.bat 重建。",
            },
            {
                "title": "同环境套件一成功一失败",
                "detail": "多为多个 runner/main.py 进程抢 MQ；仅保留 start-client.bat 或 BrickCoreRunner.exe 上线的一个进程。",
            },
            {
                "title": "录制定位不准 / 只有一种候选",
                "detail": "升级至 v1.3.6+；AI 优化会从候选列表智能重选默认定位（如区域链式）；仍不准请手动切换下拉备选。",
            },
            {
                "title": "hover 步骤执行极慢（每次多等约 20 秒）",
                "detail": "升级至 v1.3.15+；旧版将步骤里的 timeout 误当作悬停后 sleep。升级后 timeout 仅用于定位超时，悬停后默认停留 500ms，可按需设 wait_time。",
            },
            {
                "title": "Playwright 浏览器缺失",
                "detail": "打包版启动时会提示补装；开发模式在 runner\\venv 内执行 playwright install chromium。",
            },
        ],
        "doc_links": [
            {"label": "执行器使用说明", "doc_id": "runner-client"},
            {"label": "打包与版本", "doc_id": "runner-packaging"},
            {"label": "排查指南", "path": "/docs", "query": {"doc": "runner-troubleshooting"}},
        ],
    }


def merge_notices_into_release(info: dict[str, Any]) -> dict[str, Any]:
    info = dict(info)
    info["runner_notices"] = build_runner_notices()
    return info
