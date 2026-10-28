@echo off
setlocal
cd /d "%~dp0code"
if not exist "..\runs" mkdir "..\runs"
set "PYTHONDONTWRITEBYTECODE=1"
where py >nul 2>nul
if not errorlevel 1 (set "PYCMD=py -3") else (set "PYCMD=python")
%PYCMD% --version > "..\runs\python_version.txt" 2>&1
%PYCMD% -m unittest -q test_s32_core_sufficiency > "..\runs\tests.txt" 2>&1
set TEST_RC=%errorlevel%
if not "%TEST_RC%"=="0" (echo Tests FAILED; see runs\tests.txt&pause&exit /b %TEST_RC%)
rem comparison writes summary files in code; copy to runs and restore packaged originals
%PYCMD% s32_comparison.py > "..\runs\comparison.txt" 2>&1
set CAMPAIGN_RC=%errorlevel%
if "%CAMPAIGN_RC%"=="0" (copy /y S32_SUMMARY.json "..\runs\S32_SUMMARY.json" >nul&copy /y S32_RAW_RESULTS.json "..\runs\S32_RAW_RESULTS.json" >nul)
del /q S32_SUMMARY.json S32_RAW_RESULTS.json >nul 2>nul
if "%CAMPAIGN_RC%"=="0" (echo Tests and comparison finished. See runs folder.) else (echo Comparison failed. See runs\comparison.txt)
pause
exit /b %CAMPAIGN_RC%
