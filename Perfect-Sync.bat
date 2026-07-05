@echo off
rem ---------------------------------------------------------------
rem  VRM Perfect Sync Tool launcher
rem  MUST stay pure ASCII: cmd parses .bat with the OEM codepage
rem  (GBK on Chinese Windows) and UTF-8 Chinese bytes corrupt lines.
rem  Chinese text is shown via a PowerShell MessageBox fed Base64 UTF-8
rem  (mshta javascript: is blocked on modern Windows 11).
rem
rem  Python resolution order:
rem    1) runtime\python   (private portable copy, set up by this bat)
rem    2) system python on PATH
rem    3) offer to download a portable copy (~20 MB) into runtime\
rem  Portable source: astral-sh/python-build-standalone (includes
rem  tkinter), SHA-256 verified after download.
rem  Env hooks for tests/CI:
rem    PS_CHECKONLY=1    report which python would be used, no launch
rem    PS_AUTOINSTALL=1  no prompts; go straight to portable setup
rem ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PYDIR=%~dp0runtime\python"

if exist "%PYDIR%\pythonw.exe" (
  if defined PS_CHECKONLY ( echo RESULT_PYTHON_PORTABLE & exit /b 0 )
  start "" "%PYDIR%\pythonw.exe" perfect_sync_gui.py
  exit /b
)

rem "where python" can match the fake Microsoft Store stub, so run a
rem real import test instead (the stub exits 9009 without a window).
rem "call" is required: python may resolve to a .bat shim (pyenv-win),
rem and invoking a .bat without call would never return control here.
call python -c "import sys" >nul 2>nul
if not errorlevel 1 (
  if defined PS_CHECKONLY ( echo RESULT_PYTHON_SYSTEM & exit /b 0 )
  start "" pythonw perfect_sync_gui.py
  exit /b
)

if defined PS_CHECKONLY ( echo RESULT_PYTHON_MISSING & exit /b 3 )
if defined PS_AUTOINSTALL goto portable

rem ---------------- Python missing ----------------
rem Bilingual popup (Base64 UTF-8 keeps this file pure ASCII)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms;[void][System.Windows.Forms.MessageBox]::Show([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5pyq5om+5YiwIFB5dGhvbuOAggrmnKzlt6Xlhbflj6/ku6XmiorkuIDku73np4HmnIkgUHl0aG9uKOe6piAyME1CKemFjee9ruWIsOW3peWFt+aWh+S7tuWkueWGhSzkuI3mlLnliqjns7vnu5/jgIIK54K55Ye756Gu5a6a5ZCO5Zyo6buR6Imy56qX5Y+j5Lit6YCJ5oupOgpbMV0g6Ieq5Yqo6YWN572uKOaOqOiNkCkgIFsyXSDmiZPlvIDlrpjnvZHmiYvliqjlronoo4UKClB5dGhvbiBub3QgZm91bmQuClRoZSB0b29sIGNhbiBzZXQgdXAgYSBwcml2YXRlIGNvcHkgKH4yMCBNQikgaW5zaWRlIGl0cyBvd24gZm9sZGVyIC0gbm90aGluZyBzeXN0ZW0td2lkZS4KQWZ0ZXIgT0ssIGNob29zZSBpbiB0aGUgY29uc29sZSB3aW5kb3c6ClsxXSBhdXRvLXNldHVwIChyZWNvbW1lbmRlZCkgIFsyXSBvcGVuIHB5dGhvbi5vcmc=')),'VRM Perfect Sync')"

echo.
echo Python was not found on this PC. The tool can set up its own
echo private copy inside the tool folder (about 20 MB download).
echo Nothing is installed system-wide; deleting the runtime folder
echo removes it completely.
echo.
echo   [1] Set up private Python automatically (recommended)
echo   [2] Open python.org to install Python manually
echo.
choice /c 12 /n /m "Choose 1 or 2: "
if errorlevel 2 goto manual

:portable
set "PBSVER=cpython-3.12.13+20260623-x86_64-pc-windows-msvc-install_only_stripped"
set "SHA256=de3e362376859b060fa8b856c434efa81fcf6d4ede3d6e177c7e2169670cac50"
set "TARBALL=%~dp0runtime\downloads\%PBSVER%.tar.gz"
if not exist "%~dp0runtime\downloads" mkdir "%~dp0runtime\downloads"

if exist "%TARBALL%" (
  echo Found cached download, verifying ...
  certutil -hashfile "%TARBALL%" SHA256 | findstr /i "%SHA256%" >nul
  if not errorlevel 1 goto extract
  del "%TARBALL%" >nul 2>nul
)

echo Downloading portable Python 3.12 (about 20 MB) ...
curl -fL --connect-timeout 20 -o "%TARBALL%" "https://github.com/astral-sh/python-build-standalone/releases/download/20260623/cpython-3.12.13+20260623-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
if not errorlevel 1 if exist "%TARBALL%" goto checksum
echo First source failed, trying mirror 1 ...
curl -fL --connect-timeout 20 -o "%TARBALL%" "https://registry.npmmirror.com/-/binary/python-build-standalone/20260623/cpython-3.12.13+20260623-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
if not errorlevel 1 if exist "%TARBALL%" goto checksum
echo Mirror 1 failed, trying mirror 2 ...
curl -fL --connect-timeout 20 -o "%TARBALL%" "https://ghfast.top/https://github.com/astral-sh/python-build-standalone/releases/download/20260623/cpython-3.12.13+20260623-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
if errorlevel 1 goto dlfail
if not exist "%TARBALL%" goto dlfail

:checksum
echo Verifying download integrity (SHA-256) ...
certutil -hashfile "%TARBALL%" SHA256 | findstr /i "%SHA256%" >nul
if errorlevel 1 goto badhash

:extract
echo Extracting ...
tar -xf "%TARBALL%" -C "%~dp0runtime"
if errorlevel 1 goto extractfail
"%PYDIR%\python.exe" -c "import tkinter" >nul 2>nul
if errorlevel 1 goto verifyfail
echo Private Python is ready (runtime\python).
if defined PS_AUTOINSTALL ( echo BOOTSTRAP_DONE & exit /b 0 )
echo Starting the tool ...
start "" "%PYDIR%\pythonw.exe" perfect_sync_gui.py
exit /b

:dlfail
echo.
echo Download failed (network problem?). You can also install Python
echo manually from python.org - remember to tick "Add python.exe to PATH".
goto manual

:badhash
del "%TARBALL%" >nul 2>nul
echo.
echo The downloaded file failed the integrity check and was deleted.
echo Please run this launcher again. If it keeps failing, install
echo Python manually from python.org.
goto manual

:extractfail
echo.
echo Could not extract the archive (tar.exe missing?). Windows 10
echo version 1803 or newer is required. Please install Python manually.
goto manual

:verifyfail
echo.
echo The portable Python did not pass verification. Please delete the
echo runtime\python folder and run this launcher again, or install
echo Python manually.
goto manual

:manual
if defined PS_AUTOINSTALL ( echo BOOTSTRAP_FAILED & exit /b 1 )
start https://www.python.org/downloads/
echo.
echo In the installer, REMEMBER to tick "Add python.exe to PATH",
echo then double-click this launcher again.
echo.
pause
exit /b 1
