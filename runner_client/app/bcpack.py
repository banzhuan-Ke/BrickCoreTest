"""客户端侧 .bcpack 解密与增量通道选择（与 scripts/bcpack.py 算法一致）。"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Mapping

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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def decrypt_bcpack_to_zip(blob: bytes, *, key: bytes | None = None) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise RuntimeError(
            "当前客户端未包含 cryptography，无法解密增量包。请重新打包正式版 GUI（含 cryptography）。"
        ) from exc
    key = key or package_aes_key()
    if len(blob) < HEADER_LEN + 16:
        raise ValueError("bcpack 文件过小或已损坏")
    if blob[:4] != MAGIC:
        raise ValueError("不是有效的 .bcpack（magic 不匹配）")
    ver, alg, _reserved = struct.unpack_from("<BBH", blob, 4)
    if ver != FORMAT_VERSION:
        raise ValueError(f"不支持的 bcpack 版本: {ver}")
    if alg != ALG_AES_GCM:
        raise ValueError(f"不支持的加密算法: {alg}")
    expect_digest = blob[8:40]
    nonce = blob[40:52]
    ciphertext = blob[52:]
    try:
        plain = AESGCM(key).decrypt(nonce, ciphertext, associated_data=MAGIC)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("增量包解密失败（密钥不匹配或文件损坏）") from exc
    if hashlib.sha256(plain).digest() != expect_digest:
        raise ValueError("增量包校验失败（明文 hash 不匹配）")
    return plain


def parse_version(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for segment in (version or "0").strip().split("."):
        token = segment.split("-")[0].split("+")[0]
        try:
            parts.append(int(token))
        except ValueError:
            parts.append(0)
    return tuple(parts or (0,))


def compare_version(left: str, right: str) -> int:
    a = parse_version(left)
    b = parse_version(right)
    length = max(len(a), len(b))
    a = a + (0,) * (length - len(a))
    b = b + (0,) * (length - len(b))
    if a > b:
        return 1
    if a < b:
        return -1
    return 0


def select_update_plan(
    current_version: str,
    manifest: Mapping[str, Any] | None,
    *,
    gui_version: str | None = None,
) -> dict[str, Any]:
    """选择更新计划：none / patch / full（与 scripts/bcpack.py 保持一致）。"""
    if not isinstance(manifest, Mapping):
        return {"action": "full", "channels": [], "reason": "无增量清单，使用整包"}
    latest = str(manifest.get("latest") or "").strip()
    if not latest:
        return {"action": "full", "channels": [], "reason": "清单缺少 latest"}

    pkg = current_version or "0"
    gui_ver = gui_version if gui_version is not None else pkg
    pkg_behind = compare_version(pkg, latest) < 0
    gui_behind = compare_version(gui_ver or "0", latest) < 0
    if not pkg_behind and not gui_behind:
        return {"action": "none", "channels": [], "reason": "已是最新"}

    min_base = str(manifest.get("min_base_version") or "").strip()
    if pkg_behind and min_base and compare_version(pkg, min_base) < 0:
        return {
            "action": "full",
            "channels": [],
            "reason": f"当前版本低于增量底座要求 {min_base}",
        }

    channels = [c for c in (manifest.get("channels") or []) if isinstance(c, Mapping)]
    by_id = {str(c.get("id") or ""): dict(c) for c in channels}
    runner = by_id.get("runner")
    gui = by_id.get("gui")

    selected: list[dict[str, Any]] = []
    if pkg_behind and runner:
        mb = str(runner.get("min_base_version") or "").strip()
        if mb and compare_version(pkg, mb) < 0:
            return {
                "action": "full",
                "channels": [],
                "reason": f"runner 通道要求底座 >= {mb}",
            }
        selected.append(runner)

    need_gui = False
    if selected and runner and bool(runner.get("requires_gui")):
        need_gui = True
    if gui_behind:
        need_gui = True
    if pkg_behind and not runner and gui:
        need_gui = True

    if need_gui:
        if not gui:
            return {"action": "full", "channels": [], "reason": "需要 GUI 增量但通道缺失"}
        if not any(c.get("id") == "gui" for c in selected):
            selected.append(gui)

    if not selected:
        return {"action": "full", "channels": [], "reason": "无匹配增量通道"}
    return {"action": "patch", "channels": selected, "reason": "分层增量"}


def read_installed_package_version(install_root: Path, *, fallback: str = "0.0.0") -> str:
    vf = install_root / "VERSION.txt"
    if vf.is_file():
        text = vf.read_text(encoding="utf-8-sig").strip()
        if text:
            return text.splitlines()[0].strip()
    return fallback


def load_manifest_dict(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None
