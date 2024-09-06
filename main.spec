# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
import platform
datas = []
datas += collect_data_files('gradio_client')
datas += collect_data_files('gradio')
datas += collect_data_files('gradio_calendar')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    module_collection_mode={
        'gradio': 'py',  # Collect gradio package as source .py files
        'gradio_calendar': 'py', # Collect'
    },
    hiddenimports=['geetest.AmorterValidator','bili_ticket_gt_python'],
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
    name='biliTickerBuy',
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
    icon=['assets/icon.ico']
)


app = BUNDLE(exe,
             name='biliTickerBuy.app',
             icon='assets/icon.icns',
             bundle_identifier=None
             )
if platform.system() == "Darwin":
    ## Make app bundle double-clickable
    import plistlib
    from pathlib import Path
    app_path = Path(app.name)

    # read Info.plist
    with open(app_path / 'Contents/Info.plist', 'rb') as f:
        pl = plistlib.load(f)

    # write Info.plist
    with open(app_path / 'Contents/Info.plist', 'wb') as f:
        pl['CFBundleExecutable'] = 'wrapper'
        plistlib.dump(pl, f)

    # write new wrapper script
    shell_script = """#!/bin/bash
    dir=$(dirname $0)
    open -a Terminal file://${dir}/%s""" % app.appname
    with open(app_path / 'Contents/MacOS/wrapper', 'w') as f:
        f.write(shell_script)

    # make it executable
    (app_path  / 'Contents/MacOS/wrapper').chmod(0o755)