@echo off

xcopy /E/I/y .\assets ..\youtube-local_git\assets /EXCLUDE:.\copy_files_ignore_list.txt
xcopy /E/I/y .\fork1\youtube ..\youtube-local_git\fork1\youtube /EXCLUDE:.\copy_files_ignore_list.txt
xcopy /E/I/y .\innertube-client1\youtube ..\youtube-local_git\innertube-client1\youtube /EXCLUDE:.\copy_files_ignore_list.txt

xcopy /y .\fork1\server.py ..\youtube-local_git\fork1\server.py* /EXCLUDE:.\copy_files_ignore_list.txt
xcopy /y .\fork1\settings.py ..\youtube-local_git\fork1\settings.py* /EXCLUDE:.\copy_files_ignore_list.txt
xcopy /y .\fork1\settings.txt ..\youtube-local_git\fork1\settings.txt* /EXCLUDE:.\copy_files_ignore_list.txt

xcopy /y .\innertube-client1\server.py ..\youtube-local_git\innertube-client1\server.py* /EXCLUDE:.\copy_files_ignore_list.txt
xcopy /y .\innertube-client1\settings.py ..\youtube-local_git\innertube-client1\settings.py* /EXCLUDE:.\copy_files_ignore_list.txt
xcopy /y .\innertube-client1\settings.txt ..\youtube-local_git\innertube-client1\settings.txt* /EXCLUDE:.\copy_files_ignore_list.txt

pause




