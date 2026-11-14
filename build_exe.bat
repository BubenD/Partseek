@echo off
rem Builds a single standalone dist\Partseek.exe (no Python needed on the target PC)
cd /d "%~dp0"
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed --name Partseek --exclude-module pytest --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module PySide6.QtNetwork run_partseek.py
rem build\ only holds intermediate files; its Partseek.exe cannot run on its own
if exist build rmdir /s /q build
if exist dist\Partseek rmdir /s /q dist\Partseek
if exist Partseek.spec del Partseek.spec
echo.
echo Done: dist\Partseek.exe
