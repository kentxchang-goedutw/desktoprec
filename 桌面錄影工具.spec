# -*- mode: python ; coding: utf-8 -*-
import os
import sys


app_name = '桌面錄影工具V2'
icon_path = 'assets/icon.ico' if sys.platform == 'win32' and os.path.exists('assets/icon.ico') else None


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('ui/styles.qss', 'ui'), ('assets/*', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=sys.platform == 'darwin',
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name=f'{app_name}.app',
        icon=None,
        bundle_identifier='tw.blogspot.kentxchang.desktoprecorder',
    )
