# -*- mode: python ; coding: utf-8 -*-

import os

# The folder this spec file is in (PyInstaller sets SPECPATH), so the
# published source builds from wherever it is checked out -- part of
# letting users rebuild pdfNote against a modified Qt (LGPL-3.0 s.4(d)).
ROOT = SPECPATH

# Shown in the app (File > License Information) and read by --self-test.
LEGAL_FILES = [
    'LICENSE_NOTICE.txt',
    'AGPL-3.0.txt', 'THIRD_PARTY_NOTICES.txt', 'THIRD_PARTY_LICENSES.txt',
    'LGPL-3.0.txt', 'GPL-3.0.txt',
    'Apache-2.0.txt', 'Python-LICENSE.txt', 'PyInstaller-COPYING.txt',
    'TERMS_OF_USE_ja.md', 'TERMS_OF_USE_en.md',
    'PRIVACY_POLICY_ja.md', 'PRIVACY_POLICY_en.md',
    'TOKUSHOHO_ja.md',
]

# The Microsoft Store purchases go through PyWinRT, imported inside the
# functions that use it; name the modules so the executable has them. The
# same list as STORE_WINRT_MODULES in app.py. PyInstaller only warns when one
# is not installed, so the self-test imports each of them.
STORE_MODULES = [
    'winrt.runtime', 'winrt.runtime.interop', 'winrt.system',
    'winrt.windows.foundation', 'winrt.windows.foundation.collections',
    'winrt.windows.services.store',
]

# Modules and Qt plugins pdfNote never loads. PyInstaller's hooks pulled them
# in anyway; leaving them out makes the executable smaller and keeps software
# under other licences -- the Qt Virtual Keyboard is GPL-3.0-only -- out of
# the distribution altogether. Pillow is only used by PyMuPDF functions
# pdfNote does not call.
EXCLUDED_MODULES = [
    'PIL', 'tkinter',
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtOpenGL',
    'PySide6.QtPdf', 'PySide6.QtVirtualKeyboard',
]
EXCLUDED_BINARIES = (
    'qt6virtualkeyboard', 'platforminputcontexts', 'qt6quick', 'qt6qml',
    'qt6opengl', 'opengl32sw', 'qt6pdf', 'imageformats\\qpdf',
    # Qt Network is kept from 5.31: QLocalServer is how a second launch
    # hands its file to the pdfNote already running. On Windows that is a
    # named pipe -- no socket is opened, so the privacy policy still holds.
    # Its TLS and network-information plugins are wanted only by code that
    # talks to a network, which this does not.
    'plugins\\tls', 'plugins\\networkinformation',
    # OpenSSL (libcrypto-3.dll / libssl-3.dll) is *not* excluded: File >
    # License Information reads ssl.OPENSSL_VERSION to show its version, and
    # THIRD_PARTY_NOTICES.txt names it. Two entries here used to spell it
    # "libcrypto-3-x64", which matched nothing and contradicted that (F5-01).
    'translations\\qt_help_',
    # TUIO touch input over the network: never requested.
    'plugins\\generic',
)


def _kept(entry):
    name = entry[0].replace('/', '\\').lower()
    return not any(part in name for part in EXCLUDED_BINARIES)


a = Analysis(
    [f'{ROOT}/app.py'],
    pathex=[],
    binaries=[],
    # The start screen draws the wordmark. A copy drawn for a dark
    # background is used when one is shipped, and there need not be one.
    # The 512px PNG stands in if the wordmark is missing: a QPixmap given
    # an .ico takes one frame out of it, and the frame it takes is small.
    datas=[
        (f'{ROOT}/pdfNote.ico', '.'),
        (f'{ROOT}/pdfNote-512.png', '.'),
        (f'{ROOT}/pdfNote-logo.png', '.'),
    ]
    + [
        (f'{ROOT}/{name}', '.')
        for name in ('pdfNote-logo-dark.png',)
        if os.path.exists(f'{ROOT}/{name}')
    ]
    + [(f'{ROOT}/legal/{name}', 'legal') for name in LEGAL_FILES],
    hiddenimports=STORE_MODULES,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    optimize=0,
)
a.binaries = [entry for entry in a.binaries if _kept(entry)]
a.datas = [entry for entry in a.datas if _kept(entry)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='pdfNote',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX is left off on purpose: whether it is installed would otherwise
    # decide what the executable looks like, and a UPX-compressed binary is
    # a well-known source of antivirus false positives (v5.26 review F3-09).
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=f'{ROOT}/version_info.txt',
    icon=[f'{ROOT}/pdfNote.ico'],
)
