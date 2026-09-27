@echo off
setlocal
where cl >nul 2>nul
if errorlevel 1 (
  echo Run this script from an x64 Native Tools Command Prompt for Visual Studio.
  exit /b 1
)
if not exist "%~dp0build" mkdir "%~dp0build"
cd /d "%~dp0native"
rc /nologo /fo ..\build\app.res app.rc
if errorlevel 1 exit /b 1
cl /nologo /std:c++20 /utf-8 /EHsc /MT /O2 /W4 /DUNICODE /D_UNICODE engine.cpp ..\build\app.res /Fo..\build\engine.obj /FeMSXLiveBridge.Engine.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++20 /utf-8 /EHsc /MT /O2 /W4 /DUNICODE /D_UNICODE connect.cpp ..\build\app.res /Fo..\build\connect.obj /FeMSXLiveBridge.Connect.exe
if errorlevel 1 exit /b 1
cd ..
if not exist tests\mock-bin mkdir tests\mock-bin
cl /nologo /std:c++20 /utf-8 /EHsc /MT /O2 /W4 /DUNICODE /D_UNICODE /DMSXLB_TEST native\engine.cpp /Fobuild\test-engine.obj /Fetests\mock-bin\msx-vsif-sender.exe
if errorlevel 1 exit /b 1
cl /nologo /EHsc /MT /O2 /LD tests\fake_ftdi.cpp /Fobuild\fake.obj /Fetests\mock-bin\ftd2xx.dll /link /IMPLIB:build\fake.lib
exit /b %errorlevel%
