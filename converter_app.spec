from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project_root = Path(SPECPATH)

block_cipher = None

imagecodecs_datas, imagecodecs_binaries, imagecodecs_hiddenimports = collect_all('imagecodecs')
tifffile_datas, tifffile_binaries, tifffile_hiddenimports = collect_all('tifffile')


a = Analysis(
    ['converter_app.py'],
    pathex=[str(project_root)],
    binaries=[
        (str(project_root / 'bin' / 'cjpegli'),                    'bin'),
        (str(project_root / 'bin' / 'libjxl_threads.0.12.dylib'),  'bin'),
        (str(project_root / 'bin' / 'libjxl_cms.0.12.dylib'),      'bin'),
        (str(project_root / 'bin' / 'libjpeg.8.dylib'),            'bin'),
        (str(project_root / 'bin' / 'liblcms2.2.dylib'),           'bin'),
        (str(project_root / 'bin' / 'libhwy.1.dylib'),             'bin'),
    ] + imagecodecs_binaries + tifffile_binaries,
    datas=imagecodecs_datas + tifffile_datas,
    hiddenimports=imagecodecs_hiddenimports + tifffile_hiddenimports,
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
    name='JPG Master - JPEGLI & JXL Converter',
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
    name='JPG Master - JPEGLI & JXL Converter',
)

app = BUNDLE(
    coll,
    name='JPG Master - JPEGLI & JXL Converter.app',
    icon=None,
    bundle_identifier='com.halebop17.jpegli-converter',
    info_plist={
        'CFBundleName': 'JPG Master - JPEGLI & JXL Converter',
        'CFBundleDisplayName': 'JPG Master - JPEGLI & JXL Converter',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': 'True',
    },
)