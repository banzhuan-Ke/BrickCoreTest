#!/usr/bin/env python3
"""BrickCore 被测监控采集器启停与配置向导（交互式，配置可复用）。"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "agent_config.json"
PID_PATH = HERE / "agent.pid"
LOG_PATH = HERE / "agent.log"
AGENT_PY = HERE / "sut_metrics_agent.py"
VENV_PY = HERE / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
    "python.exe" if os.name == "nt" else "python"
)


def _python() -> str:
    if VENV_PY.exists():
        return str(VENV_PY)
    return sys.executable


def _load_config() -> Optional[dict[str, Any]]:
    if not CONFIG_PATH.exists():
        return None
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


def _mask_token(token: str) -> str:
    t = (token or "").strip()
    if len(t) <= 10:
        return "***"
    return t[:6] + "…" + t[-4:]


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    return raw if raw else default


def _ask_yes_no(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    raw = input(f"{prompt} ({d}): ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes", "1", "是")


def _validate_platform(platform: str) -> str:
    platform = platform.strip().rstrip("/")
    u = urlparse(platform)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise SystemExit("platform 须为 http(s)://主机[:端口] 形式")
    return platform


def interactive_config(existing: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    print("\n=== BrickCore 被测监控采集器 · 配置 ===\n")
    existing = existing or {}

    if existing.get("platform") and existing.get("token"):
        print(f"已保存配置：")
        print(f"  平台：{existing.get('platform')}")
        print(f"  Token：{_mask_token(str(existing.get('token')))}")
        print(f"  allow_insecure_http：{bool(existing.get('allow_insecure_http'))}")
        print()
        print("请选择：")
        print("  1) 使用上次配置并启动")
        print("  2) 只更新 Token（平台地址不变）")
        print("  3) 重新填写全部配置")
        choice = _ask("选项", "1")
        if choice == "1":
            return dict(existing)
        if choice == "2":
            token = _ask("新 Token")
            if len(token) < 16:
                raise SystemExit("Token 过短")
            cfg = dict(existing)
            cfg["token"] = token
            _save_config(cfg)
            print(f"已保存 → {CONFIG_PATH}")
            return cfg

    platform = _ask("测试平台地址（如 http://47.111.226.241）", str(existing.get("platform") or ""))
    platform = _validate_platform(platform)
    token = _ask("Token（控制台创建被测服务器时复制）")
    if len(token) < 16:
        raise SystemExit("Token 过短，请确认粘贴完整")

    allow_insecure = False
    if platform.startswith("http://"):
        host = (urlparse(platform).hostname or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            allow_insecure = _ask_yes_no(
                "当前是 HTTP（非本机），是否允许明文传输 Token（allow_insecure_http）",
                True,
            )
            if not allow_insecure:
                raise SystemExit("非本机 HTTP 必须允许 allow_insecure_http，或改用 HTTPS")

    interval = _ask("采样间隔秒", str(existing.get("interval_sec") or 5))
    upload = _ask("上传间隔秒", str(existing.get("upload_every_sec") or 15))

    cfg = {
        "platform": platform,
        "token": token,
        "allow_insecure_http": allow_insecure,
        "interval_sec": int(interval),
        "upload_every_sec": int(upload),
        "buffer_hours": int(existing.get("buffer_hours") or 48),
        "data_dir": str(existing.get("data_dir") or "./data"),
    }
    _save_config(cfg)
    print(f"\n已保存配置 → {CONFIG_PATH}")
    return cfg


def _read_pid() -> Optional[int]:
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in (out.stdout or "")
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_status() -> None:
    pid = _read_pid()
    if pid and _pid_alive(pid):
        print(f"采集器运行中，PID={pid}")
        print(f"日志：{LOG_PATH}")
    elif pid:
        print(f"PID 文件存在但进程不在（PID={pid}），可执行 stop 清理后 start")
    else:
        print("采集器未运行")
    cfg = _load_config()
    if cfg:
        print(f"配置：{cfg.get('platform')} token={_mask_token(str(cfg.get('token')))}")


def cmd_stop() -> None:
    pid = _read_pid()
    if not pid:
        print("未找到 PID，尝试按进程名结束…")
        if os.name == "nt":
            subprocess.run(
                ["wmic", "process", "where", "CommandLine like '%sut_metrics_agent.py%'", "delete"],
                check=False,
                capture_output=True,
            )
        else:
            subprocess.run(["pkill", "-f", "sut_metrics_agent.py"], check=False)
        print("已尝试停止")
        return
    if _pid_alive(pid):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
            else:
                os.kill(pid, signal.SIGTERM)
                for _ in range(20):
                    if not _pid_alive(pid):
                        break
                    time.sleep(0.2)
                if _pid_alive(pid):
                    os.kill(pid, signal.SIGKILL)
        except OSError as e:
            print(f"停止失败：{e}")
            return
        print(f"已停止采集器（PID={pid}）")
    else:
        print("进程已不存在，清理 PID 文件")
    try:
        PID_PATH.unlink(missing_ok=True)
    except TypeError:
        if PID_PATH.exists():
            PID_PATH.unlink()


def cmd_start(*, skip_prompt: bool = False) -> None:
    if not AGENT_PY.exists():
        raise SystemExit(f"找不到 {AGENT_PY}")
    py = _python()
    if not Path(py).exists() and py == str(VENV_PY):
        print("未检测到 .venv，请先：python3 -m venv .venv && .venv/bin/pip install -r requirements.txt")
        raise SystemExit(1)

    existing = _load_config()
    if skip_prompt and existing and existing.get("platform") and existing.get("token"):
        cfg = existing
    else:
        cfg = interactive_config(existing)

    pid = _read_pid()
    if pid and _pid_alive(pid):
        print(f"采集器已在运行（PID={pid}）。如需重启请先执行 stop。")
        return

    env = os.environ.copy()
    log_f = open(LOG_PATH, "a", encoding="utf-8")
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0x00000008
        )
        proc = subprocess.Popen(
            [py, str(AGENT_PY), "-c", str(CONFIG_PATH)],
            cwd=str(HERE),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=creationflags,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            [py, str(AGENT_PY), "-c", str(CONFIG_PATH)],
            cwd=str(HERE),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
            close_fds=True,
        )
    PID_PATH.write_text(str(proc.pid), encoding="utf-8")
    print(f"已后台启动采集器，PID={proc.pid}")
    print(f"平台：{cfg.get('platform')}")
    print(f"日志：{LOG_PATH} （可用：tail -f {LOG_PATH}）")
    print("停止：./stop.sh  或  python agent_ctl.py stop")


def main(argv: Optional[list[str]] = None) -> None:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(
            "用法：\n"
            "  python agent_ctl.py start     # 交互配置（可复用上次）并后台启动\n"
            "  python agent_ctl.py start -y  # 直接用已有配置启动\n"
            "  python agent_ctl.py stop      # 停止采集器\n"
            "  python agent_ctl.py status    # 查看状态\n"
            "  python agent_ctl.py config    # 仅更新配置，不启动\n"
        )
        return
    cmd = argv[0]
    if cmd == "start":
        cmd_start(skip_prompt="-y" in argv or "--yes" in argv)
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "status":
        cmd_status()
    elif cmd == "config":
        interactive_config(_load_config())
    else:
        raise SystemExit(f"未知命令：{cmd}")


if __name__ == "__main__":
    main()
