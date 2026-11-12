@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt pyinstaller
pyinstaller --noconfirm --noconsole --onefile --name HuaChengPartner --icon assets\icon.ico --add-data "assets;assets" --exclude-module tkinter main.py
echo.
echo Done: dist\HuaChengPartner.exe
pause
