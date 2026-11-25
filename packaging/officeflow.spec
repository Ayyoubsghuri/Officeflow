# PyInstaller build description: produces dist/OfficeFlow/ (OfficeFlow.exe + its files).
# Build the interface first (cd frontend && npm run build), then: pyinstaller packaging/officeflow.spec
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
WEB = ROOT / "officeflow" / "web"
if not (WEB / "index.html").exists():
    raise SystemExit("The interface is not built: run `npm run build` in the frontend folder first.")

sys.path.insert(0, str(ROOT))
from officeflow import __version__  # noqa: E402

hidden = collect_submodules("officeflow") + collect_submodules("uvicorn")

a = Analysis(
    [str(ROOT / "packaging" / "officeflow_app.py")],
    pathex=[str(ROOT)],
    datas=[(str(WEB), "officeflow/web")],
    hiddenimports=hidden,
    excludes=["tkinter", "PySide6", "PyQt5", "PyQt6", "matplotlib", "IPython", "pytest", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)

version_file = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                      VarFileInfo, VarStruct, VSVersionInfo)

    numbers = tuple(int(x) for x in (__version__.split(".") + ["0", "0", "0"])[:4])
    version_file = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("ProductName", "OfficeFlow"), StringStruct("FileDescription", "OfficeFlow"),
            StringStruct("FileVersion", __version__), StringStruct("ProductVersion", __version__),
            StringStruct("OriginalFilename", "OfficeFlow.exe"), StringStruct("CompanyName", "OfficeFlow")])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])])])

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="OfficeFlow",
    console=False,                       # no black console window
    icon=str(ROOT / "packaging" / "officeflow.ico"),
    version=version_file,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="OfficeFlow", upx=False)
