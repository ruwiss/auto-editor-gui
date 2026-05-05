@echo off
chcp 65001 > nul
cd /d "%~dp0"
py app.py
if errorlevel 1 (
  python app.py
)
if errorlevel 1 (
  echo.
  echo Python baslatilamadi veya uygulama hata verdi.
  echo Kurulum icin: py -m pip install -r requirements.txt
  pause
)
