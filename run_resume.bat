@echo off
cd /d "C:\Users\XPENG_USER\Documents\docs\文献\feedforward"
python -u resume_rewrite.py --dry-run > dryrun_out.txt 2>&1
echo Dry run complete. Exit code: %ERRORLEVEL%

