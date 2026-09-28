#!/usr/bin/env python3
"""容器内 / 本机安装 brickcore_assist（自包含，不依赖仓库 scripts/）。

用法:
  python tools/install_brickcore_assist.py /path/to/brickcore_assist-*.bcpack
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import site
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"BCPK"
FORMAT_VERSION = 1
ALG_AES_GCM = 1
HEADER_LEN = 52
_PKG = "brickcore_assist"


def package_aes_key() -> bytes:
    parts = (
        b"BrickCore\x00Runner\x01Update",
        b"v1\xfelayered\xffpatch",
        bytes([0x3C, 0xA5, 0x91, 0x2E, 0x77, 0x0B, 0xD4, 0x68]),
    )
    return hashlib.sha256(b"|".join(parts)).digest()


def decrypt_bcpack_to_zip(blob: bytes) -> bytes:
    if len(blob) < HEADER_LEN + 16:
        raise ValueError("bcpack 文件过小或已损坏")
    if blob[:4] != MAGIC:
        raise ValueError("不是有效的 .bcpack")
    ver, alg, _ = struct.unpack_from("<BBH", blob, 4)
    if ver != FORMAT_VERSION or alg != ALG_AES_GCM:
        raise ValueError("不支持的 bcpack 版本/算法")
    nonce = blob[40:52]
    return AESGCM(package_aes_key()).decrypt(nonce, blob[52:], associated_data=MAGIC)


def default_target() -> Path:
    for preferred in (Path("/app/ext_packages"), Path("ext_packages")):
        try:
            preferred.mkdir(parents=True, exist_ok=True)
            probe = preferred / ".assist_write_probe"
            probe.write_text("1", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return preferred
        except OSError:
            continue
    for p in list(site.getsitepackages()) + [Path(site.getusersitepackages())]:
        c = Path(p)
        try:
            c.mkdir(parents=True, exist_ok=True)
            probe = c / ".assist_write_probe"
            probe.write_text("1", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return c
        except OSError:
            continue
    raise SystemExit("无可用安装目录，请传 --target（Docker 建议 /app/ext_packages）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pack", type=Path)
    ap.add_argument("--target", type=Path, default=None)
    args = ap.parse_args()
    if not args.pack.is_file():
        print("file not found", file=sys.stderr)
        return 1
    target = args.target or default_target()
    zip_bytes = decrypt_bcpack_to_zip(args.pack.read_bytes())
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "p.zip"
        zpath.write_bytes(zip_bytes)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(tmp)
        src = Path(tmp) / _PKG
        if not src.is_dir():
            found = [p for p in Path(tmp).rglob(_PKG) if p.is_dir()]
            src = found[0] if found else None
        if src is None:
            raise SystemExit(f"包内无 {_PKG} 目录")
        if not (src / "__init__.py").is_file():
            raise SystemExit(f"包内 {_PKG} 缺少 __init__.py（包可能损坏）")
        dest = target / _PKG
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        bins = list(dest.rglob("*.pyd")) + list(dest.rglob("*.so"))
        pys = [p for p in dest.rglob("*.py") if p.name != "__init__.py"]
        if not bins and not pys:
            raise SystemExit("安装结果异常：既无业务 .py 也无 .pyd/.so")
    print(f"installed -> {dest}")
    if bins:
        print(f"  detected Nuitka binaries: {len(bins)}")
    else:
        print(f"  detected plaintext modules: {len(pys)}")
    print("重启 backend 后确认 import brickcore_assist / ASSIST_STANDARD_ENABLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
