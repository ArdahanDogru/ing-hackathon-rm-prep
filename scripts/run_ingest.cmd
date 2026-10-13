@echo off
rem One ingest with a log entry; called by the task of scripts/schedule_ingest.ps1.
rem Exit code 3 = another ingest runs (docs/ingest.md I6).
cd /d "%~dp0.."
if not exist "data\logs" mkdir "data\logs"
echo ==== %DATE% %TIME% start>> "data\logs\ingest.log"
".venv\Scripts\python.exe" -m rmprep ingest >> "data\logs\ingest.log" 2>&1
set RC=%ERRORLEVEL%
echo ==== %DATE% %TIME% exit %RC%>> "data\logs\ingest.log"
exit /b %RC%
