@echo off
setlocal EnableDelayedExpansion

rem CYT4BB7 IAR build script
rem Double-click: incremental build (same as IAR F7 Make), with multi-core parallel compile
rem Usage:
rem   build.bat            incremental build CM7_0 + CM7_1
rem   build.bat rebuild    full rebuild CM7_0 + CM7_1
rem   build.bat cm7_0      incremental build CM7_0 only
rem   build.bat cm7_1      incremental build CM7_1 only

cd /d "%~dp0"

set "MODE=-make"
set "CONFIG=Debug"
set "BUILD_CM7_0=1"
set "BUILD_CM7_1=1"

if /i "%~1"=="rebuild" set "MODE=-build"
if /i "%~1"=="make" set "MODE=-make"
if /i "%~1"=="cm7_0" set "BUILD_CM7_1=0"
if /i "%~1"=="cm7_1" set "BUILD_CM7_0=0"
if /i "%~2"=="rebuild" set "MODE=-build"
if /i "%~2"=="make" set "MODE=-make"

if not defined NUMBER_OF_PROCESSORS set "NUMBER_OF_PROCESSORS=4"
set "PARALLEL=-parallel %NUMBER_OF_PROCESSORS%"

set "PROJ_DIR=%~dp0project_config"
set "IARBUILD="

if exist "%ProgramFiles%\IAR Systems\Embedded Workbench 9.2\common\bin\iarbuild.exe" (
    set "IARBUILD=%ProgramFiles%\IAR Systems\Embedded Workbench 9.2\common\bin\iarbuild.exe"
    goto found_iarbuild
)

if exist "%ProgramFiles%\IAR Systems\Embedded Workbench 9.4\common\bin\iarbuild.exe" (
    set "IARBUILD=%ProgramFiles%\IAR Systems\Embedded Workbench 9.4\common\bin\iarbuild.exe"
    goto found_iarbuild
)

if exist "%ProgramFiles(x86)%\IAR Systems\Embedded Workbench 9.2\common\bin\iarbuild.exe" (
    set "IARBUILD=%ProgramFiles(x86)%\IAR Systems\Embedded Workbench 9.2\common\bin\iarbuild.exe"
    goto found_iarbuild
)

where iarbuild >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%i in ('where iarbuild 2^>nul') do (
        set "IARBUILD=%%i"
        goto found_iarbuild
    )
)

echo [ERROR] iarbuild.exe not found. Please install IAR Embedded Workbench.
goto end_fail

:found_iarbuild
if /i "%MODE%"=="-make" (
    echo Mode: Make incremental, same as IAR F7
) else (
    echo Mode: Rebuild All, same as IAR Project-Rebuild All
)
echo IAR Build: !IARBUILD!
echo Parallel: %NUMBER_OF_PROCESSORS% cores
echo Config: !CONFIG!
echo.

set "EXIT_CODE=0"

if "!BUILD_CM7_0!"=="1" (
    echo === cyt4bb7_cm_7_0.ewp ===
    "!IARBUILD!" "!PROJ_DIR!\cyt4bb7_cm_7_0.ewp" !MODE! !CONFIG! !PARALLEL! -log warnings
    if errorlevel 1 set "EXIT_CODE=1"
)

if "!EXIT_CODE!"=="0" if "!BUILD_CM7_1!"=="1" (
    echo.
    echo === cyt4bb7_cm_7_1.ewp ===
    "!IARBUILD!" "!PROJ_DIR!\cyt4bb7_cm_7_1.ewp" !MODE! !CONFIG! !PARALLEL! -log warnings
    if errorlevel 1 set "EXIT_CODE=1"
)

echo.
if "!EXIT_CODE!"=="0" (
    echo Build succeeded.
    echo CM7_0 HEX: !PROJ_DIR!\Debug_m7_0\Exe\cyt4bb7_cm_7_0.hex
    echo CM7_1 HEX: !PROJ_DIR!\Debug_m7_1\Exe\cyt4bb7_cm_7_1.hex
) else (
    echo Build failed.
)

goto end

:end_fail
set "EXIT_CODE=1"

:end
echo.
pause
exit /b %EXIT_CODE%
