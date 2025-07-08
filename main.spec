# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files("gradio_client")
datas += collect_data_files("gradio")
datas += collect_data_files("gradio_calendar")
datas += collect_data_files("gradio_log")

# 自动选择图标
if sys.platform == "darwin":
    icon_file = os.path.abspath("assets/icon.icns")
    is_windowed = True  # 不会跳出命令行，直接进入webui，需要确保运行稳定
    is_console = False  # 一般命令行应用
elif sys.platform == "win32":
    icon_file = os.path.abspath("assets/icon.ico")
    is_windowed = False # 需要在windows环境下测试以决定怎样启用
    is_console = True   # 一般命令行应用
else:
    icon_file = None    #Linux/*BSD等其他系统默认设置为标准命令行程序
    is_windowed = False
    is_console = True

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    module_collection_mode={
        "gradio": "py",  # Collect gradio package as source .py files
        "gradio_calendar": "py",  # Collect'
        "gradio_log": "py",  # Collect'
    },
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="biliTickerBuy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file if icon_file else None,
)

# macOS构建`.app`应用
# 运行后会构建两个应用，一个是不会跳出命令行的带icon的程序，另一个则是命令行应用，没有icon
app = None
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="biliTickerBuy.app",
        icon=icon_file,
        bundle_identifier="com.mikumifa.bilitickerbuy",  # 标识符瞎编的，用的github地址，可以随便改
    )
