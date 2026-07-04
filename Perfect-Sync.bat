@echo off
rem ---------------------------------------------------------------
rem  VRM Perfect Sync Tool launcher
rem  MUST stay pure ASCII: cmd parses .bat with the OEM codepage
rem  (GBK on Chinese Windows) and UTF-8 Chinese bytes corrupt lines.
rem  Chinese text is shown via mshta \u escapes instead.
rem ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

rem "where python" can match the fake Microsoft Store stub, so run a
rem real import test instead (the stub exits 9009 without a window).
python -c "import sys" >nul 2>nul
if not errorlevel 1 (
  start "" pythonw perfect_sync_gui.py
  exit /b
)

rem ---------------- Python missing ----------------
rem Chinese via \u escapes (ASCII-safe in any codepage)
mshta "javascript:alert('\u672a\u627e\u5230 Python 3\u3002\n\u672c\u5de5\u5177\u9700\u8981\u514d\u8d39\u7684 Python 3\u3002\n\u70b9\u51fb\u786e\u5b9a\u540e\u6309\u63d0\u793a\u64cd\u4f5c:\n[1] \u81ea\u52a8\u4e0b\u8f7d\u5b89\u88c5(\u63a8\u8350)  [2] \u6253\u5f00\u5b98\u7f51\u624b\u52a8\u5b89\u88c5\n\nPython 3 not found. After clicking OK:\n[1] auto-install (recommended)  [2] open python.org');close()"

echo.
echo Python 3 was not found on this PC. It is required (about 25 MB).
echo.
echo   [1] Download and install Python automatically (recommended)
echo   [2] Open python.org and install manually
echo.
choice /c 12 /n /m "Choose 1 or 2: "
if errorlevel 2 goto manual

set "PYEXE=%TEMP%\python-3.12.8-amd64.exe"
echo.
echo Downloading Python 3.12.8 ...
curl -L --connect-timeout 20 -o "%PYEXE%" https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe
if errorlevel 1 (
  echo First source failed, trying mirror ...
  curl -L --connect-timeout 20 -o "%PYEXE%" https://registry.npmmirror.com/-/binary/python/3.12.8/python-3.12.8-amd64.exe
)
if errorlevel 1 goto dlfail
if not exist "%PYEXE%" goto dlfail

echo Installing Python (silent, per-user, 1-3 minutes) ...
"%PYEXE%" /quiet InstallAllUsers=0 PrependPath=1
if errorlevel 1 (
  echo Install failed. Falling back to manual install.
  goto manual
)
echo Done. Starting the tool ...
if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" (
  start "" "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" perfect_sync_gui.py
  exit /b
)
echo Please double-click this launcher again.
pause
exit /b

:dlfail
echo Download failed (network problem?).
goto manual

:manual
start https://www.python.org/downloads/
echo.
echo In the installer, REMEMBER to tick "Add python.exe to PATH",
echo then double-click this launcher again.
echo.
pause
exit /b
