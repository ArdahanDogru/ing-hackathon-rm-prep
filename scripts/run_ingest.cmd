@echo off
rem One ingest with a log entry; called by the task of scripts/schedule_ingest.ps1.
rem Exit code 3 = another ingest runs (docs/ingest.md I6).
cd /d "%~dp0.."
if not exist "data\logs" mkdir "data\logs"
rem The redirection comes first: "exit 0>> file" would redirect handle 0, not write "0".
>> "data\logs\ingest.log" echo ==== %DATE% %TIME% start
".venv\Scripts\python.exe" -m rmprep ingest --summary >>"data\logs\ingest.log" 2>&1
set RC=%ERRORLEVEL%
>> "data\logs\ingest.log" echo ==== %DATE% %TIME% exit %RC%
exit /b %RC%
