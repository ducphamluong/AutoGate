@echo off
chcp 65001 >nul
setlocal
set "RUN_KEEPALIVE=1"
for %%A in (%*) do (
  if /I "%%~A"=="stop" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="status" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="logs" set "RUN_KEEPALIVE=0"
)

for /f "usebackq delims=" %%I in (`wsl -d Ubuntu-24.04 -u root -- wslpath -a "%~dp0."`) do set "WSL_DIR=%%I"
if "%WSL_DIR%"=="" (
  echo Khong lay duoc WSL path tu thu muc hien tai.
  goto after_action
)

echo ============================================
echo   AutoGate Manager  (WSL2 - Ubuntu-24.04)
echo ============================================
echo.
echo Workdir WSL: %WSL_DIR%
echo.

wsl -d Ubuntu-24.04 -u root -- env AUTOGATE_DIR="%WSL_DIR%" bash "%WSL_DIR%/autogate.sh" %*
if errorlevel 1 goto after_action

if "%RUN_KEEPALIVE%"=="1" (
  call :keepalive
  goto end
)
:after_action
echo.
echo --------------------------------------------
echo  Cach dung khac (go trong cmd/PowerShell):
echo   autogate.bat              = bat stack
echo   autogate.bat US           = bat stack voi proxy US
echo   autogate.bat US 10        = bat proxy US voi 10 port 56800-56809
echo   autogate.bat US 20        = bat proxy US voi 20 port 56800-56819
echo   autogate.bat restart US   = khoi dong lai voi proxy US
echo   autogate.bat restart US 5 = khoi dong lai voi 5 port 56800-56804
echo   autogate.bat stop         = tat stack
echo   autogate.bat restart      = khoi dong lai
echo   autogate.bat status       = xem trang thai
echo   autogate.bat logs haproxy = xem log
echo.
echo   Proxy xoay vong : http://localhost:56789
echo   Proxy list UI   : http://localhost:2087
echo   Worker proxies  : bat dau tu http://127.0.0.1:56800 theo so port da nhap
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
