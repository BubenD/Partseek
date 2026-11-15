@echo off
rem Publishes Partseek to a NEW GitHub repo and uploads the installer as a release.
rem Prerequisites:
rem   1. GitHub CLI installed (winget install GitHub.cli)
rem   2. Authenticated once:  gh auth login
rem   3. Installer built:     build_release.bat
rem
rem Usage:  installer\publish_github.bat [repo-name]
setlocal
cd /d "%~dp0\.."

set REPO=%1
if "%REPO%"=="" set REPO=Partseek

set GH=gh
where gh >nul 2>nul || set GH=%ProgramFiles%\GitHub CLI\gh.exe

"%GH%" auth status >nul 2>nul || (echo Not logged in. Run: gh auth login & exit /b 1)

if not exist release_out\Partseek-Setup-1.0.0.exe (
  echo Installer not found. Run build_release.bat first.
  exit /b 1
)

echo Creating public repo "%REPO%" and pushing main...
"%GH%" repo create "%REPO%" --public --source=. --remote=origin --push || exit /b 1

echo Creating release v1.0.0 and uploading the installer...
"%GH%" release create v1.0.0 "release_out\Partseek-Setup-1.0.0.exe#Partseek Setup 1.0.0 (Windows installer)" ^
  --title "Partseek 1.0.0" ^
  --notes "Partseek 1.0.0 - part number search for PDF and CSV files. (c) Expand Technology Solutions. Download Partseek-Setup-1.0.0.exe below and run it." || exit /b 1

echo.
echo Done. Repo and release published.
"%GH%" repo view --web
endlocal
