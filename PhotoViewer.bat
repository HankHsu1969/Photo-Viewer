@echo off
rem Kirapix launcher. Drag an image or folder onto this file, or double-click it.
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0main.py" %*
) else (
    start "" python "%~dp0main.py" %*
)
