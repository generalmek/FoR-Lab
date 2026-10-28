@echo off
setlocal
cd /d "%~dp0"
if not exist "runs" mkdir "runs"
set "PYTHONDONTWRITEBYTECODE=1"
where py >nul 2>nul
if not errorlevel 1 (set "PYCMD=py -3") else (set "PYCMD=python")
%PYCMD% --version > "runs\python_version.txt" 2>&1

rem Tests read packaged code without changing it.
pushd "code"
%PYCMD% -m unittest -q test_s32_core_sufficiency > "..\runs\tests.txt" 2>&1
set "TEST_RC=%errorlevel%"
popd
if not "%TEST_RC%"=="0" (echo Tests FAILED; see runs\tests.txt&pause&exit /b %TEST_RC%)

rem Run campaign from a disposable copy: s32_comparison.py writes next to itself.
rem Never delete or overwrite source and packaged control results in code/.
if not exist "runs\working_code" mkdir "runs\working_code"
xcopy "code\*" "runs\working_code\" /E /I /Y /Q > "runs\copy.txt"
if errorlevel 1 (echo Copy FAILED; see runs\copy.txt&pause&exit /b 1)
pushd "runs\working_code"
%PYCMD% s32_comparison.py > "..\comparison.txt" 2>&1
set "CAMPAIGN_RC=%errorlevel%"
popd
if "%CAMPAIGN_RC%"=="0" (
  copy /y "runs\working_code\S32_SUMMARY.json" "runs\S32_SUMMARY.json" >nul
  copy /y "runs\working_code\S32_RAW_RESULTS.json" "runs\S32_RAW_RESULTS.json" >nul
  echo Tests and comparison finished. See runs folder.
) else (echo Comparison failed. See runs\comparison.txt)
pause
exit /b %CAMPAIGN_RC%
