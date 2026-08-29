#!/usr/bin/env python3
"""容器内 / 本机安装 brickcore_tm（自包含，不依赖仓库 scripts/）。

用法:
  python tools/install_brickcore_tm.py /path/to/brickcore_tm-*.bcpack
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
    for p in list(site.getsitepackages()) + [Path(site.getusersitepackages())]:
        c = Path(p)
        try:
            c.mkdir(parents=True, exist_ok=True)
            probe = c / ".tm_write_probe"
            probe.write_text("1", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return c
        except OSError:
            continue
    raise SystemExit("无可用 site-packages，请传 --target")


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
        src = Path(tmp) / "brickcore_tm"
        if not src.is_dir():
            found = [p for p in Path(tmp).rglob("brickcore_tm") if p.is_dir()]
            src = found[0] if found else None
        if src is None:
            raise SystemExit("包内无 brickcore_tm 目录")
        if not (src / "__init__.py").is_file():
            raise SystemExit("包内 brickcore_tm 缺少 __init__.py（包可能损坏）")
        dest = target / "brickcore_tm"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        # 粗检：Nuitka 包应有二进制；明文包应有多个 .py
        bins = list(dest.glob("*.pyd")) + list(dest.glob("*.so"))
        pys = [p for p in dest.glob("*.py") if p.name != "__init__.py"]
        if not bins and not pys:
            raise SystemExit("安装结果异常：既无业务 .py 也无 .pyd/.so")
    print(f"installed -> {dest}")
    if bins:
        print(f"  detected Nuitka binaries: {len(bins)}")
    else:
        print(f"  detected plaintext modules: {len(pys)}")
    print("重启 backend 后访问 /test-management/premium-status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
