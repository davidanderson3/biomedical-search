@echo off
setlocal
set "PUBLIC_SEARCH_ROOT=%~dp0.."
for %%I in ("%PUBLIC_SEARCH_ROOT%") do set "PUBLIC_SEARCH_ROOT=%%~fI"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PUBLIC_SEARCH_ROOT%\docker\umls\windows-launcher.ps1" -Mode install -RootDir "%PUBLIC_SEARCH_ROOT%"
exit /b %ERRORLEVEL%
