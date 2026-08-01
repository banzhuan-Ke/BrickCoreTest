# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：BrickCore Runner 桌面客户端（onedir）"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
# SPECPATH = directory of this .spec file (runner_client/)
client = Path(SPECPATH).resolve()
root = client.parent

_crypto_datas, _crypto_binaries, _crypto_hidden = collect_all("cryptography")
_crypto_hidden += collect_submodules("cryptography")

a = Analysis(
    [str(client / "__main__.py")],
    pathex=[str(root)],
    binaries=_crypto_binaries,
    datas=_crypto_datas,
    hiddenimports=[
        "runner_client",
        "runner_client.main",
        "runner_client.app.api_client",
        "runner_client.app.app_local_status",
        "runner_client.app.brick_animation",
        "runner_client.app.engine_capabilities",
        "runner_client.app.engine_manager",
        "runner_client.app.perf_worker_manager",
        "runner_client.app.store",
        "runner_client.app.runtime_check",
        "runner_client.app.win_subprocess",
        "runner_client.app.health",
        "runner_client.app.preferences",
        "runner_client.app.runner_execution_config",
        "runner_client.app.secure_store",
        "runner_client.app.server_dialog",
        "runner_client.app.settings_dialog",
        "runner_client.app.package_updater",
        "runner_client.app.bcpack",
        "runner_client.app.layered_updater",
        "runner_client.app.ui_debug_hotkeys",
        "cryptography",
        "cryptography.hazmat.primitives.ciphers.aead",
        "cryptography.hazmat.bindings._rust",
        *_crypto_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BrickCoreRunner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BrickCoreRunner",
)
