# -*- mode: python ; coding: utf-8 -*-
import os

ROOT = os.path.dirname(os.path.abspath(SPEC))          # packaging/
PROJECT_ROOT = os.path.dirname(ROOT)                    # repo root

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'main.py')],
    pathex=[os.path.join(PROJECT_ROOT, 'src')],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_ROOT, 'src', 'sigiq', 'assets'), 'sigiq/assets'),
    ],
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
    name='SigIQ',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(PROJECT_ROOT, 'src', 'sigiq', 'assets', 'icon.ico')],
)
