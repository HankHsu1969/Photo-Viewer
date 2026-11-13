@echo off
rem Builds dist\PhotoViewer\PhotoViewer.exe (requires: python -m pip install -r requirements.txt pyinstaller)
cd /d "%~dp0"
python packaging\make_icon.py || goto :error
python -m PyInstaller packaging\PhotoViewer.spec --noconfirm --distpath dist --workpath build || goto :error
copy /y packaging\register_open_with.ps1 dist\PhotoViewer\ >nul
copy /y packaging\unregister_open_with.ps1 dist\PhotoViewer\ >nul
copy /y packaging\Register-OpenWith.bat dist\PhotoViewer\ >nul
copy /y packaging\Unregister-OpenWith.bat dist\PhotoViewer\ >nul
echo.
echo Done: dist\PhotoViewer\PhotoViewer.exe
goto :eof
:error
echo Build failed.
exit /b 1
