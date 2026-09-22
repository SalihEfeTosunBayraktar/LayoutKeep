@echo off
rem LayoutKeep'i KAYNAKTAN calistirir - exe derlemeden denemek icin.
rem Konsol kapanmaz: bir hata olursa ekranda kalir, yoksa pencereyi kapattiginda kendiliginden gider.
rem Not: .venv hazir olmali (python -m venv .venv + pip install -e ".[dev]").
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PYTHONIOENCODING=utf-8"
echo LayoutKeep kaynaktan baslatiliyor... (pencere acilmazsa bu konsolda hata vardir)
".venv\Scripts\python.exe" -m layoutkeep.ui.app %*
set "KOD=%errorlevel%"
if not "%KOD%"=="0" (
    echo.
    echo Uygulama %KOD% koduyla kapandi.
    pause
)
