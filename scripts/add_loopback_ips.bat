@echo off
REM Adds 192.168.100.200 through .228 to the "Bacnet Simulator" loopback adapter.
REM Must be run from an elevated (Run as Administrator) Command Prompt or PowerShell.
REM
REM Idempotent — netsh will skip IPs already present with a benign error.

setlocal enabledelayedexpansion
set ADAPTER=Bacnet Simulator
set MASK=255.255.255.0

for /l %%i in (200,1,228) do (
    echo Adding 192.168.100.%%i
    netsh interface ipv4 add address name="%ADAPTER%" 192.168.100.%%i %MASK%
)

echo.
echo Done. Verify with:
echo   netsh interface ipv4 show addresses name="%ADAPTER%"
endlocal
