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
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms;[void][System.Windows.Forms.MessageBox]::Show([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5pyq5om+5YiwIFB5dGhvbuOAggrmnIDnroDljZU65Y675Y+R5biD6aG15LiL6L29IEZ1bGwo5a6M5pW0KeeJiOKAlOKAlOaJgOacieS+nei1luW3suaJk+WMhSzop6PljovljbPnlKjjgIIK5oiW6K6p5bel5YW36Ieq5Yqo6YWN572u5LiA5Lu956eB5pyJIFB5dGhvbijnuqYgMjBNQizpnIDogZTnvZEs5LiN5pS55Yqo57O757ufKeOAggrngrnlh7vnoa7lrprlkI7lnKjpu5HoibLnqpflj6PkuK3mjIkgMSAvIDIgLyAzIOmAieaLqeOAggoKUHl0aG9uIG5vdCBmb3VuZC4KRWFzaWVzdDogZG93bmxvYWQgdGhlIEZVTEwgcGFja2FnZSBmcm9tIHRoZSByZWxlYXNlcyBwYWdlIC0gZXZlcnl0aGluZyBidW5kbGVkLCB1bnppcCBhbmQgcnVuLgpPciBsZXQgdGhlIHRvb2wgc2V0IHVwIGEgcHJpdmF0ZSBQeXRob24gKH4yMCBNQiwgbmVlZHMgaW50ZXJuZXQsIG5vIHN5c3RlbSBjaGFuZ2VzKS4KQWZ0ZXIgT0ssIHByZXNzIDEgLyAyIC8gMyBpbiB0aGUgY29uc29sZSB3aW5kb3cu')),'VRM Perfect Sync')"

echo.
echo Python was not found on this PC. Options:
echo.
echo   [1] Set up a private Python automatically
echo       (20 MB download, nothing system-wide, needs internet)
echo   [2] Get the FULL version instead - everything already bundled,
echo       unzip and run (best if downloads keep failing)
echo   [3] Open python.org to install Python manually
echo.
choice /c 123 /n /m "Choose 1, 2 or 3: "
if errorlevel 3 goto manual
if errorlevel 2 goto fullver

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
if defined PS_AUTOINSTALL ( echo BOOTSTRAP_FAILED & exit /b 1 )
echo.
echo Download failed (network problem?).
echo The easiest fix: download the FULL version - everything is already
echo bundled inside, no downloads needed. Opening the releases page ...
start https://github.com/elainyilanchen/blender-vrm-perfect-sync/releases
echo Alternatively install Python manually from python.org and tick
echo "Add python.exe to PATH".
echo.
pause
exit /b 1

:fullver
start https://github.com/elainyilanchen/blender-vrm-perfect-sync/releases
echo.
echo Opening the releases page in your browser. Download the file ending
echo in "full-win64.zip" (everything bundled), unzip it anywhere, then
echo double-click Perfect-Sync.bat inside - it starts right away.
echo.
pause
exit /b 1

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
