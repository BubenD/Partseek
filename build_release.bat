@echo off
rem Builds the protected Partseek release: obfuscated exe + Windows installer.
rem Output: release_out\Partseek.exe  and  release_out\Partseek-Setup-1.0.0.exe
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo ERROR: .venv not found. Create it first:
  echo   py -3 -m venv .venv
  echo   .venv\Scripts\python -m pip install -r requirements.txt pyinstaller pyarmor pillow
  exit /b 1
)

echo === [1/2] Building protected exe (PyArmor + PyInstaller) ===
.venv\Scripts\python installer\build_protected.py || exit /b 1

set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
  echo ERROR: Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup
  exit /b 1
)

echo === [2/2] Building installer (Inno Setup) ===
"%ISCC%" installer\Partseek.iss || exit /b 1

echo.
echo Done:
echo   release_out\Partseek.exe
echo   release_out\Partseek-Setup-1.0.0.exe
