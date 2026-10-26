# PyInstaller build file: pyinstaller --noconfirm navigator.spec
import sys

datas = [("navigator/config", "navigator/config"), ("navigator/i18n/*.json", "navigator/i18n"),
         ("navigator/resources", "navigator/resources")]
excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore"]

a = Analysis(["run.py"], pathex=["."], datas=datas, excludes=excludes)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Decarbonisation Navigator",
              console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="Decarbonisation Navigator", upx=False)
    app = BUNDLE(coll, name="Decarbonisation Navigator.app",
                 bundle_identifier="gr.katsampas.decarbonisation-navigator",
                 info_plist={"NSHighResolutionCapable": True})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="DecarbonisationNavigator",
              console=False, upx=False)
