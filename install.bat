@echo off

echo Installing dependencies...
echo.

rem --------------------------------------

echo Python
set errorlevel=
libs\python-2.7.1.msi
IF NOT %errorlevel% == 0 GOTO ERROR

rem --------------------------------------

echo GTK
set errorlevel=
libs\gtk2-runtime-2.22.0-2010-10-21-ash.exe
IF NOT %errorlevel% == 0 GOTO ERROR

rem --------------------------------------

echo pygobject
set errorlevel=
libs\pygobject-2.26.0-1.win32-py2.7.msi
IF NOT %errorlevel% == 0 GOTO ERROR

rem --------------------------------------

echo pycairo
set errorlevel=
libs\pycairo-1.8.10.win32-py2.7.msi
IF NOT %errorlevel% == 0 GOTO ERROR

rem --------------------------------------

echo pygtk
set errorlevel=
libs\pygtk-2.22.0-1.win32-py2.7.msi
IF NOT %errorlevel% == 0 GOTO ERROR

rem --------------------------------------

echo zopeinterface
set errorlevel=
libs\zope.interface-4.0.5.win32-py2.7.exe
IF NOT %errorlevel% == 0 GOTO ERROR

rem --------------------------------------

echo Twisted
set errorlevel=
libs\Twisted-12.3.0.win32-py2.7.msi
IF NOT %errorlevel% == 0 GOTO ERROR

rem --------------------------------------

echo pywin32
set errorlevel=
libs\pywin32-218.win32-py2.7.exe
IF NOT %errorlevel% == 0 GOTO ERROR

rem --------------------------------------

echo psutil
set errorlevel=
libs\psutil-0.6.1.win32-py2.7.exe
IF NOT %errorlevel% == 0 GOTO ERROR

rem --------------------------------------

echo mplayer
set errorlevel=
md "C:\Program Files\MPlayer"
IF NOT %errorlevel% == 0 GOTO ERROR

md mplayer
copy libs\7za.exe mplayer
copy libs\MPlayer-p4-svn-34401.7z mplayer
cd mplayer

set errorlevel=
7za e -y MPlayer-p4-svn-34401.7z
IF NOT %errorlevel% == 0 GOTO ERROR

rmdir MPlayer-p4-svn-34401
del 7za.exe
del MPlayer-p4-svn-34401.7z

set errorlevel=
xcopy /E . "C:\Program Files\MPlayer"
IF NOT %errorlevel% == 0 GOTO ERROR
cd ..
rmdir /Q /S mplayer


echo.
echo OK
echo.
echo =================================
echo.
echo.

echo Installing VideoConvertor...
echo.

set errorlevel=
C:\Python27\python.exe setup.py install
IF NOT %errorlevel% == 0 GOTO ERROR


echo.
echo OK
echo.
echo =================================
echo.
echo.
echo.
echo.
echo Installation done.


:ERROR
exit /b %errorlevel%