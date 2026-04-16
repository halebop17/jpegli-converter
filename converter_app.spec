from pathlib import Path

project_root = Path(SPECPATH)

block_cipher = None


a = Analysis(
    ['converter_app.py'],
    pathex=[str(project_root)],
    binaries=[(str(project_root / 'bin' / 'cjpegli'), 'bin')],
    datas=[],
    hiddenimports=['imagecodecs', 'tifffile'],
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
    name='TIFF to jpegli Converter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name='TIFF to jpegli Converter',
)

app = BUNDLE(
    coll,
    name='TIFF to jpegli Converter.app',
    icon=None,
    bundle_identifier='com.halebop17.jpegli-converter',
    info_plist={
        'CFBundleName': 'TIFF to jpegli Converter',
        'CFBundleDisplayName': 'TIFF to jpegli Converter',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': 'True',
    },
)