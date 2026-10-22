"""Build the WAV2C64 executables with PyInstaller.

    python packaging/build.py

Output in ./release:
  Windows : WAV2C64-<ver>-windows-x64.exe          (single file)
  macOS   : WAV2C64-<ver>-macos-arm64.dmg          (WAV2C64.app)
  Linux   : WAV2C64-<ver>-linux-x86_64.AppImage    (single file)
            WAV2C64-<ver>-linux-x86_64.tar.gz      (single binary)
"""

import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from wav2c64 import APP_NAME, VERSION, AUTHOR  # noqa: E402

ASSETS = os.path.join(ROOT, "wav2c64", "assets")
REL = os.path.join(ROOT, "release")
SEP = ";" if os.name == "nt" else ":"
APPIMAGETOOL = ("https://github.com/AppImage/appimagetool/releases/download/"
                "continuous/appimagetool-x86_64.AppImage")


def pyinstaller(extra, dist, work):
    import PyInstaller.__main__
    args = [
        os.path.join(ROOT, "run_wav2c64.py"),
        "--name", APP_NAME,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--distpath", dist,
        "--workpath", work,
        "--specpath", work,
        "--add-data", os.path.join(ASSETS) + SEP + "wav2c64/assets",
        "--exclude-module", "tkinter",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.Qt3DCore",
    ] + extra
    print("pyinstaller", " ".join(args))
    PyInstaller.__main__.run(args)


def win_version_file(path):
    nums = [int(x) for x in "".join(c if c.isdigit() or c == "." else "" for c in VERSION).split(".") if x]
    nums = (nums + [0, 0, 0, 0])[:4]
    t = tuple(nums)
    with open(path, "w", encoding="utf-8") as f:
        f.write("""VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(t)s, prodvers=%(t)s, mask=0x3f, flags=0x0, OS=0x40004,
    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '%(a)s'),
      StringStruct('FileDescription', '%(n)s - WAV to C64 4-bit samples'),
      StringStruct('FileVersion', '%(v)s'),
      StringStruct('InternalName', '%(n)s'),
      StringStruct('LegalCopyright', 'Copyright (c) %(a)s, MIT License'),
      StringStruct('OriginalFilename', '%(n)s.exe'),
      StringStruct('ProductName', '%(n)s'),
      StringStruct('ProductVersion', '%(v)s')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""" % {"t": t, "a": AUTHOR, "n": APP_NAME, "v": VERSION})


def build_windows():
    work = os.path.join(ROOT, "build", "win")
    os.makedirs(work, exist_ok=True)
    vf = os.path.join(work, "version.txt")
    win_version_file(vf)
    pyinstaller(["--onefile", "--icon", os.path.join(ASSETS, "icon.ico"),
                 "--version-file", vf], os.path.join(ROOT, "dist", "win"), work)
    out = os.path.join(REL, "%s-%s-windows-x64.exe" % (APP_NAME, VERSION))
    shutil.copy2(os.path.join(ROOT, "dist", "win", APP_NAME + ".exe"), out)
    return [out]


def build_macos():
    work = os.path.join(ROOT, "build", "mac")
    dist = os.path.join(ROOT, "dist", "mac")
    pyinstaller(["--icon", os.path.join(ASSETS, "icon.png"),
                 "--osx-bundle-identifier", "de.it-dummkopfen.wav2c64"], dist, work)
    app = os.path.join(dist, APP_NAME + ".app")
    plist = os.path.join(app, "Contents", "Info.plist")
    for key, val in (("CFBundleShortVersionString", VERSION), ("CFBundleVersion", VERSION),
                     ("NSHumanReadableCopyright", "Copyright (c) %s, MIT License" % AUTHOR),
                     ("CFBundleDisplayName", APP_NAME)):
        subprocess.run(["plutil", "-replace", key, "-string", val, plist], check=True)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True)
    arch = "arm64" if platform.machine() == "arm64" else platform.machine()
    stage = os.path.join(work, "dmg")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    subprocess.run(["ditto", app, os.path.join(stage, APP_NAME + ".app")], check=True)
    os.symlink("/Applications", os.path.join(stage, "Applications"))
    out = os.path.join(REL, "%s-%s-macos-%s.dmg" % (APP_NAME, VERSION, arch))
    subprocess.run(["hdiutil", "create", "-volname", "%s %s" % (APP_NAME, VERSION),
                    "-srcfolder", stage, "-ov", "-format", "UDZO", out], check=True)
    return [out]


def build_linux():
    outs = []
    # 1) single binary
    work = os.path.join(ROOT, "build", "linux1")
    dist1 = os.path.join(ROOT, "dist", "linux1")
    pyinstaller(["--onefile"], dist1, work)
    name = "%s-%s-linux-x86_64" % (APP_NAME, VERSION)
    tgz = os.path.join(REL, name + ".tar.gz")
    with tarfile.open(tgz, "w:gz") as tf:
        tf.add(os.path.join(dist1, APP_NAME), arcname="%s/%s" % (name, APP_NAME))
        tf.add(os.path.join(ROOT, "LICENSE"), arcname="%s/LICENSE" % name)
        tf.add(os.path.join(ROOT, "packaging", "linux", "wav2c64.desktop"),
               arcname="%s/wav2c64.desktop" % name)
        tf.add(os.path.join(ASSETS, "icon_256.png"), arcname="%s/wav2c64.png" % name)
    outs.append(tgz)

    # 2) AppImage from a one-folder build
    work = os.path.join(ROOT, "build", "linux2")
    dist2 = os.path.join(ROOT, "dist", "linux2")
    pyinstaller([], dist2, work)
    appdir = os.path.join(work, "AppDir")
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(os.path.join(dist2, APP_NAME), os.path.join(appdir, "usr", "lib", "wav2c64"))
    shutil.copy2(os.path.join(ROOT, "packaging", "linux", "wav2c64.desktop"), appdir)
    shutil.copy2(os.path.join(ASSETS, "icon_256.png"), os.path.join(appdir, "wav2c64.png"))
    shutil.copy2(os.path.join(ASSETS, "icon_256.png"), os.path.join(appdir, ".DirIcon"))
    apprun = os.path.join(appdir, "AppRun")
    with open(apprun, "w") as f:
        f.write('#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\n'
                'exec "$HERE/usr/lib/wav2c64/%s" "$@"\n' % APP_NAME)
    os.chmod(apprun, 0o755)
    tool = os.path.join(work, "appimagetool.AppImage")
    if not os.path.exists(tool):
        urllib.request.urlretrieve(APPIMAGETOOL, tool)
    os.chmod(tool, os.stat(tool).st_mode | stat.S_IEXEC)
    out = os.path.join(REL, name + ".AppImage")
    env = dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    subprocess.run([tool, "--no-appstream", appdir, out], check=True, env=env)
    outs.append(out)
    return outs


def main():
    os.makedirs(REL, exist_ok=True)
    if sys.platform.startswith("win"):
        outs = build_windows()
    elif sys.platform == "darwin":
        outs = build_macos()
    else:
        outs = build_linux()
    for o in outs:
        print("built", o, os.path.getsize(o) // 1024, "KB")


if __name__ == "__main__":
    main()
