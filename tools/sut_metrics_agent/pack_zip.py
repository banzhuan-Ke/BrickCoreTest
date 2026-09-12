#!/usr/bin/env python3
"""打包被测监控采集器 zip（.sh 强制 LF，排除 venv/data/__pycache__）。

用法（在本目录或任意处）：
  python tools/sut_metrics_agent/pack_zip.py
  python tools/sut_metrics_agent/pack_zip.py -o /tmp/sut_metrics_agent.zip
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
INCLUDE_NAMES = {
    "sut_metrics_agent.py",
    "agent_ctl.py",
    "agent_config.example.json",
    "requirements.txt",
    "README.md",
    "start.sh",
    "stop.sh",
    "start.bat",
    "stop.bat",
}
EXCLUDE_DIR_NAMES = {".venv", "venv", "data", "__pycache__", ".git"}


def _normalize_bytes(name: str, raw: bytes) -> bytes:
    # Linux/mac 脚本必须 LF；bat 保持 CRLF
    if name.endswith(".sh") or name.endswith(".py") or name.endswith(".md") or name.endswith(".txt") or name.endswith(".json"):
        text = raw.decode("utf-8")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.endswith("\n"):
            text += "\n"
        return text.encode("utf-8")
    if name.endswith(".bat") or name.endswith(".cmd"):
        text = raw.decode("utf-8", errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\n", "\r\n")
        if not text.endswith("\r\n"):
            text += "\r\n"
        return text.encode("utf-8")
    return raw


def pack(out: Path) -> Path:
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(HERE.iterdir()):
            if not path.is_file():
                continue
            if path.name not in INCLUDE_NAMES:
                continue
            data = _normalize_bytes(path.name, path.read_bytes())
            # zip 内统一用正斜杠，避免 Linux unzip 警告 backslash
            zf.writestr(path.name, data)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Pack sut_metrics_agent.zip with LF shell scripts")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=HERE / "sut_metrics_agent.zip",
        help="output zip path",
    )
    args = ap.parse_args()
    path = pack(args.output)
    print(f"wrote {path} ({path.stat().st_size} bytes)")
    print("includes:", ", ".join(sorted(INCLUDE_NAMES)))
    print("note: start.sh/stop.sh are LF; do not re-zip with Windows Explorer if you need Linux.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
