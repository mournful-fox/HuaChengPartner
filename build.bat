@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt pyinstaller
pyinstaller --noconfirm --noconsole --onefile --name HuaCheng --icon assets\icon.ico --add-data "assets;assets" --hidden-import PySide6.QtWebSockets --hidden-import PySide6.QtNetwork --hidden-import winsound --exclude-module tkinter main.py
echo.
echo Done: dist\HuaCheng.exe
pause
