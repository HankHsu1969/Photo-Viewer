@echo off
rem Builds dist\PhotoViewer\PhotoViewer.exe and, if Inno Setup is installed, dist\installer\PhotoViewer-Setup-*.exe
rem Requires: python -m pip install -r requirements.txt pyinstaller   (installer: winget install JRSoftware.InnoSetup)
cd /d "%~dp0"
python packaging\make_icon.py || goto :error
python -m PyInstaller packaging\PhotoViewer.spec --noconfirm --distpath dist --workpath build || goto :error
copy /y packaging\register_open_with.ps1 dist\PhotoViewer\ >nul
copy /y packaging\unregister_open_with.ps1 dist\PhotoViewer\ >nul
copy /y packaging\Register-OpenWith.bat dist\PhotoViewer\ >nul
copy /y packaging\Unregister-OpenWith.bat dist\PhotoViewer\ >nul
echo.
echo Portable app: dist\PhotoViewer\  (PhotoViewer.exe = manager/editor, QuickView.exe = fast viewer)

set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC goto :noinno
"%ISCC%" /Q packaging\installer.iss || goto :error
echo Installer:    dist\installer\  (PhotoViewer-Setup-^<version^>.exe)
goto :eof

:noinno
echo Inno Setup not found - installer skipped. Install it with: winget install JRSoftware.InnoSetup
goto :eof

:error
echo Build failed.
exit /b 1
