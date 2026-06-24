@echo off
chcp 65001 >nul
setlocal
set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=start"
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
  wsl -d Ubuntu-24.04 -u root -- bash /home/ducph/AutoGate/autogate.sh %*
)
:after_action
echo.
echo --------------------------------------------
echo  Cach dung khac (go trong cmd/PowerShell):
echo   autogate.bat            = bat stack
echo   autogate.bat stop       = tat stack
echo   autogate.bat restart    = khoi dong lai
echo   autogate.bat status     = xem trang thai
echo   autogate.bat logs haproxy = xem log
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
