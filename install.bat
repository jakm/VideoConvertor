@echo off

echo Installing dependencies...
echo.

echo Python
set errorlevel=
libs\python-2.7.1.msi
IF NOT %errorlevel% == 0 GOTO ERROR

echo GTK
set errorlevel=
libs\gtk2-runtime-2.22.0-2010-10-21-ash.exe
IF NOT %errorlevel% == 0 GOTO ERROR

echo pygobject
set errorlevel=
libs\pygobject-2.26.0-1.win32-py2.7.msi
IF NOT %errorlevel% == 0 GOTO ERROR

echo pycairo
set errorlevel=
libs\pycairo-1.8.10.win32-py2.7.msi
IF NOT %errorlevel% == 0 GOTO ERROR

echo pygtk
set errorlevel=
libs\pygtk-2.22.0-1.win32-py2.7.msi
IF NOT %errorlevel% == 0 GOTO ERROR

echo zopeinterface
set errorlevel=
libs\zope.interface-4.0.5.win32-py2.7.exe
IF NOT %errorlevel% == 0 GOTO ERROR

echo Twisted
set errorlevel=
libs\Twisted-12.3.0.win32-py2.7.msi
IF NOT %errorlevel% == 0 GOTO ERROR

echo pywin32
set errorlevel=
libs\pywin32-218.win32-py2.7.exe
IF NOT %errorlevel% == 0 GOTO ERROR

echo psutil
set errorlevel=
libs\psutil-0.6.1.win32-py2.7.exe
IF NOT %errorlevel% == 0 GOTO ERROR


echo.
echo OK
echo.
echo =================================
echo.
echo.

echo Installing VideoConvertor...
echo.

set errorlevel=
md "C:\Program Files\VideoConvertor"
IF NOT %errorlevel% == 0 GOTO ERROR

set errorlevel=
md "C:\Program Files\VideoConvertor\ui"
IF NOT %errorlevel% == 0 GOTO ERROR

set errorlevel=
copy src\* "C:\Program Files\VideoConvertor"
IF NOT %errorlevel% == 0 GOTO ERROR

set errorlevel=
copy ui\* "C:\Program Files\VideoConvertor\ui"
IF NOT %errorlevel% == 0 GOTO ERROR

set errorlevel=
copy config.ini "C:\Program Files\VideoConvertor"
IF NOT %errorlevel% == 0 GOTO ERROR


echo.
echo OK
echo.
echo =================================
echo.
echo.

echo Please copy content of MPlayer-p4-svn-34401.7z into
echo C:\Program Files\MPlayer by hand.

echo.
echo Installation done.


:ERROR
exit /b %errorlevel%