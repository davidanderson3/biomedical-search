@echo off
setlocal
set "PUBLIC_SEARCH_ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PUBLIC_SEARCH_ROOT%docker\umls\windows-launcher.ps1" -Mode auto -RootDir "%PUBLIC_SEARCH_ROOT%"
exit /b %ERRORLEVEL%
