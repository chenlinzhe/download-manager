# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('index.html', '.'), ('app.js', '.')],
    hiddenimports=['webview.platforms.edgechromium', 'webview.platforms.winforms'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PySide2', 'PySide6', 'tkinter', 'torch', 'torchvision', 'torchaudio', 'tensorflow', 'keras', 'IPython', 'numba', 'scipy', 'sklearn', 'numpy', 'pandas', 'matplotlib', 'pyspark',
              'PIL', 'Pillow', 'cryptography', 'bcrypt', 'mako', 'jinja2', 'MarkupSafe', 'pygments', 'psutil', 'bs4', 'lxml', 'pytz', 'dateutil', 'pytest', 'docutils', 'sphinx'],
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
    name='下载包管家智能搜索版-v19',
    icon='app.ico',
    version='version_info.txt',
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
)
