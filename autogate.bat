@echo off
chcp 65001 >nul
setlocal
set "RUN_KEEPALIVE=1"
for %%A in (%*) do (
  if /I "%%~A"=="stop" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="status" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="logs" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="help" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="-h" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="--help" set "RUN_KEEPALIVE=0"
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
echo  Cach dung (cmd/PowerShell):
echo   autogate.bat                  = bat stack (mode all)
echo   autogate.bat US,JP 10 ovpn    = multi-country, 10 port, chi OpenVPN
echo   autogate.bat US 10            = filter US, full egress
echo   autogate.bat restart KR 5 all = restart 5 workers mode all
echo   autogate.bat stop | status | logs haproxy
echo.
echo  EGRESS_MODE: all | ovpn | ovpn+psiphon | ovpn+warp | custom
echo  COUNTRY_FILTER chi loc .ovpn — khong con tu dong tat warp.
echo  Muon chi OpenVPN: them arg ovpn
echo.
echo   Proxy xoay vong : http://localhost:56789
echo   Proxy list UI   : http://localhost:2087
echo   Worker proxies  : bat dau tu http://127.0.0.1:56800
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
