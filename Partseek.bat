@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  echo Setting up Partseek for the first time...
  py -3 -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe -m partseek
