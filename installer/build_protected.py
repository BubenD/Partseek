"""Build a hardened, standalone Partseek.exe.

Pipeline:
  1. PyArmor obfuscates + encrypts the `partseek` package bytecode and adds an
     anti-tamper / anti-debug runtime (protection against reverse engineering).
  2. PyInstaller bundles the obfuscated package (plus a tiny plain entry point)
     into a single-file windowed exe, with the ETS version resource and icon.

Run from the project root:
    .venv\\Scripts\\python installer\\build_protected.py

Output: dist\\Partseek.exe
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
BUILD = os.path.join(ROOT, "build")          # PyInstaller work dir
DIST = os.path.join(ROOT, "release_out")     # final exe lands here (fresh dir,
                                             # avoids a dist\Partseek.exe locked
                                             # by a running instance)
STAGE = os.path.join(BUILD, "stage")
ICON = os.path.join(ROOT, "partseek.ico")
VERSION_FILE = os.path.join(ROOT, "installer", "version_info.txt")


def run(cmd: list[str]) -> None:
    print("\n>", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> int:
    # 1. Clean previous output (ignore files locked by a running Partseek.exe).
    for d in (BUILD, DIST):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
    os.makedirs(STAGE, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    # 2. Obfuscate the partseek package into the staging dir.
    #    Basic obfuscation + encrypted bytecode + anti-tamper runtime. (String
    #    mixing / BCC are PyArmor paid features; add --mix-str, --enable-bcc
    #    here if you hold a PyArmor license for stronger hardening.)
    run([
        PY, "-m", "pyarmor.cli", "gen",
        "-O", STAGE,
        "-r",
        os.path.join(ROOT, "partseek"),
    ])

    # 3. Detect the generated pyarmor runtime package.
    runtimes = [
        os.path.basename(p)
        for p in glob.glob(os.path.join(STAGE, "pyarmor_runtime_*"))
        if os.path.isdir(p)
    ]
    if not runtimes:
        print("ERROR: pyarmor runtime package not found in", STAGE)
        return 1
    runtime = runtimes[0]
    print("PyArmor runtime:", runtime)

    # 4. Plain entry point + icon live next to the obfuscated package.
    shutil.copy2(os.path.join(ROOT, "run_partseek.py"), os.path.join(STAGE, "run_partseek.py"))
    shutil.copy2(ICON, os.path.join(STAGE, "partseek.ico"))

    # 5. Bundle with PyInstaller.
    run([
        PY, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", "Partseek",
        "--icon", ICON,
        "--version-file", VERSION_FILE,
        "--add-data", f"{ICON}{os.pathsep}.",
        "--distpath", DIST,
        "--workpath", BUILD,
        "--specpath", BUILD,
        "--paths", STAGE,
        "--hidden-import", runtime,
        "--collect-submodules", runtime,
        # The obfuscated partseek.app hides its `from .matcher import ...` etc.,
        # so pull in every submodule of the package explicitly.
        "--collect-submodules", "partseek",
        # Imports live inside the obfuscated modules, so PyInstaller cannot see
        # them by analysis — declare every third-party dependency explicitly.
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtPrintSupport",
        "--collect-all", "pymupdf",
        "--exclude-module", "pytest",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtNetwork",
        os.path.join(STAGE, "run_partseek.py"),
    ])

    exe = os.path.join(DIST, "Partseek.exe")
    if not os.path.exists(exe):
        print("ERROR: build did not produce", exe)
        return 1
    size_mb = os.path.getsize(exe) / (1024 * 1024)
    print(f"\nDone: {exe}  ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
