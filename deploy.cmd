@echo off
rem Runs deploy.sh from PowerShell or cmd (Windows opens a .sh file in an editor instead of running it).
setlocal
set "BASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%BASH%" set "BASH=bash.exe"
"%BASH%" "%~dp0deploy.sh" %*
exit /b %ERRORLEVEL%
