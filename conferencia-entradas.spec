# -*- mode: python ; coding: utf-8 -*-
# Build: python -m PyInstaller conferencia-entradas.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files

datas = []
for pacote in ("pdfminer", "reportlab", "pdfplumber"):
    datas += collect_data_files(pacote)  # CMaps do pdfminer, fontes do reportlab

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # testes
        "pytest", "_pytest", "pluggy", "iniconfig", "tests",
        # pacotes pesados do ambiente que a aplicação não usa
        "pandas", "numpy", "pyarrow", "scipy", "matplotlib", "sqlalchemy",
        "pydantic", "IPython", "setuptools", "tkinter", "jinja2",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="conferencia-entradas",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
