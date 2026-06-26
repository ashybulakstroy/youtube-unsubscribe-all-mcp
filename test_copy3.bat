@echo off
copy "C:\Work\Prj_32_YouTube\unsub_all.bat" "C:\Users\Maryam\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\UnsubAllYoutube.bat" > C:\Work\Prj_32_YouTube\copy_result.txt 2>&1
echo %errorlevel% > C:\Work\Prj_32_YouTube\copy_exitcode.txt
