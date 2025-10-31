:: @echo off
:: setlocal
:: cd /d "innertube-client1\" && python "server.py"
:: echo Press any key to quit...
:: PAUSE > nul

@echo off

::  https://stackoverflow.com/a/25719250
::  setlocal makes sure changing directory only applies inside this bat file,
::  and not in the command shell.
SETLOCAL

SET script_dir=%~dp0
SET python_exec_path=%script_dir%python\
SET youtube_local_server_path=%script_dir%innertube-client1\

::  So this bat file can be called from a different working directory.
::  %~dp0 is the directory with this bat file.
cd /d "%script_dir%"

::  This is so brotli and gevent search in the python directory for the
::  visual studio c++ runtime dlls
IF EXIST "%python_exec_path%" (
	set PATH="%python_exec_path%;%PATH%"
	set py_exe_loc="%python_exec_path%python.exe"
) ELSE (set py_exe_loc="python")

cd /d "%youtube_local_server_path%"

%py_exe_loc% -I "%youtube_local_server_path%server.py"
echo Press any key to quit...
PAUSE > nul

