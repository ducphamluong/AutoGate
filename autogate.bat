@echo off
chcp 65001 >nul
setlocal
set "ACTION=%~1"
set "COUNTRY_ARG="
set "EXTRA_ARG=%~2"
if "%ACTION%"=="" set "ACTION=start"
echo %ACTION%| findstr /R /I "^[A-Z][A-Z]$" >nul
if not errorlevel 1 (
  set "COUNTRY_ARG=%ACTION%"
  set "ACTION=%~2"
  set "EXTRA_ARG=%~3"
  if "%~2"=="" set "ACTION=start"
) else (
  if not "%~2"=="" (
    echo %~2| findstr /R /I "^[A-Z][A-Z]$" >nul
    if not errorlevel 1 (
      set "COUNTRY_ARG=%~2"
      set "EXTRA_ARG=%~3"
    )
  )
)
if not "%COUNTRY_ARG%"=="" set "COUNTRY_FILTER=%COUNTRY_ARG%"
echo ============================================
echo   AutoGate Manager  (WSL2 - Ubuntu-24.04)
echo ============================================
echo.
if /I "%ACTION%"=="start" (
  wsl -d Ubuntu-24.04 -u root -- env COUNTRY_FILTER="%COUNTRY_FILTER%" bash /home/ducph/AutoGate/autogate.sh start
  if errorlevel 1 goto after_action
  call :keepalive
  goto end
) else if /I "%ACTION%"=="restart" (
  wsl -d Ubuntu-24.04 -u root -- env COUNTRY_FILTER="%COUNTRY_FILTER%" bash /home/ducph/AutoGate/autogate.sh restart
  if errorlevel 1 goto after_action
  call :keepalive
  goto end
) else (
  wsl -d Ubuntu-24.04 -u root -- env COUNTRY_FILTER="%COUNTRY_FILTER%" bash /home/ducph/AutoGate/autogate.sh %ACTION% %EXTRA_ARG%
)
:after_action
echo.
echo --------------------------------------------
echo  Cach dung khac (go trong cmd/PowerShell):
echo   autogate.bat              = bat stack
echo   autogate.bat US           = bat stack voi proxy US
echo   autogate.bat restart US   = khoi dong lai voi proxy US
echo   autogate.bat stop         = tat stack
echo   autogate.bat restart      = khoi dong lai
echo   autogate.bat status       = xem trang thai
echo   autogate.bat logs haproxy = xem log
echo.
echo   Proxy xoay vong : http://localhost:56789
echo   Proxy list UI   : http://localhost:2087
echo   Worker proxies  : http://127.0.0.1:56800 ... http://127.0.0.1:56809
echo --------------------------------------------
pause
:end
endlocal
exit /b

:keepalive
echo.
echo AutoGate dang chay. Giu cua so nay mo de WSL/Docker khong tu tat.
echo Nhan Ctrl+C hoac dong cua so khi muon ngat keepalive.
:keepalive_loop
ping -n 3 127.0.0.1 >nul
wsl -d Ubuntu-24.04 -u root -- true >nul 2>nul
goto keepalive_loop
