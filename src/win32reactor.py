# -*- coding: utf8 -*-
"""
Provides GtkWin32Reactor class used on win32 platform.
"""

from twisted.internet import gtk2reactor
from twisted.internet.posixbase import win32process
from twisted.python.runtime import platformType


from twisted.internet import _dumbwin32proc

import os

# Win32 imports
import win32api
import win32con
import win32file
import win32pipe
import win32security

import pywintypes

# security attributes for pipes
PIPE_ATTRS_INHERITABLE = win32security.SECURITY_ATTRIBUTES()
PIPE_ATTRS_INHERITABLE.bInheritHandle = 1

from twisted.python.win32 import quoteArguments

from twisted.internet import _pollingfile
from twisted.internet._baseprocess import BaseProcess


class GtkWin32Reactor(gtk2reactor.PortableGtkReactor):
    """
    GtkReactor for Windows. Allows call spawnProcess with win32flags.
    It is useful when executing console application with CREATE_NO_WINDOW flag.
    """
    _wakerFactory = gtk2reactor.PortableGtkReactor._wakerFactory

    def __init__(self, useGtk=True):
        gtk2reactor.PortableGtkReactor.__init__(self, useGtk)

    # IReactorProcess

    def spawnProcess(self, processProtocol, executable, args=(),
                     env={}, path=None,
                     uid=None, gid=None, usePTY=0, childFDs=None,
                     win32flags=0):
        args, env = self._checkProcessArgs(args, env)

        if platformType == "win32":
            if uid is not None:
                raise ValueError("Setting UID is unsupported on this platform.")
            if gid is not None:
                raise ValueError("Setting GID is unsupported on this platform.")
            if usePTY:
                raise ValueError("The usePTY parameter is not supported on Windows.")
            if childFDs:
                raise ValueError("Customizing childFDs is not supported on Windows.")

            if win32process:
                return Win32Process(self, processProtocol, executable, args,
                                    env, path, win32flags)
            else:
                raise NotImplementedError(
                    "spawnProcess not available since pywin32 is not installed.")
        else:
            raise NotImplementedError(
                "Win32Reactor.spawnProcess only available on Windows.")


class Win32Process(_dumbwin32proc.Process):
    def __init__(self, reactor, protocol, command, args, environment, path,
                 win32flags=0):
        """
        Create a new child process.
        """
        _pollingfile._PollingTimer.__init__(self, reactor)
        BaseProcess.__init__(self, protocol)

        # security attributes for pipes
        sAttrs = win32security.SECURITY_ATTRIBUTES()
        sAttrs.bInheritHandle = 1

        # create the pipes which will connect to the secondary process
        self.hStdoutR, hStdoutW = win32pipe.CreatePipe(sAttrs, 0)
        self.hStderrR, hStderrW = win32pipe.CreatePipe(sAttrs, 0)
        hStdinR,  self.hStdinW  = win32pipe.CreatePipe(sAttrs, 0)

        win32pipe.SetNamedPipeHandleState(self.hStdinW,
                                          win32pipe.PIPE_NOWAIT,
                                          None,
                                          None)

        # set the info structure for the new process.
        StartupInfo = win32process.STARTUPINFO()
        StartupInfo.hStdOutput = hStdoutW
        StartupInfo.hStdError  = hStderrW
        StartupInfo.hStdInput  = hStdinR
        StartupInfo.dwFlags = win32process.STARTF_USESTDHANDLES

        # Create new handles whose inheritance property is false
        currentPid = win32api.GetCurrentProcess()

        tmp = win32api.DuplicateHandle(currentPid, self.hStdoutR, currentPid, 0, 0,
                                       win32con.DUPLICATE_SAME_ACCESS)
        win32file.CloseHandle(self.hStdoutR)
        self.hStdoutR = tmp

        tmp = win32api.DuplicateHandle(currentPid, self.hStderrR, currentPid, 0, 0,
                                       win32con.DUPLICATE_SAME_ACCESS)
        win32file.CloseHandle(self.hStderrR)
        self.hStderrR = tmp

        tmp = win32api.DuplicateHandle(currentPid, self.hStdinW, currentPid, 0, 0,
                                       win32con.DUPLICATE_SAME_ACCESS)
        win32file.CloseHandle(self.hStdinW)
        self.hStdinW = tmp

        # Add the specified environment to the current environment - this is
        # necessary because certain operations are only supported on Windows
        # if certain environment variables are present.

        env = os.environ.copy()
        env.update(environment or {})

        cmdline = quoteArguments(args)
        # TODO: error detection here.  See #2787 and #4184.
        def doCreate():
            self.hProcess, self.hThread, self.pid, dwTid = win32process.CreateProcess(
                command, cmdline, None, None, 1, win32flags, env, path, StartupInfo)
        try:
            try:
                doCreate()
            except TypeError, e:
                # win32process.CreateProcess cannot deal with mixed
                # str/unicode environment, so we make it all Unicode
                if e.args != ('All dictionary items must be strings, or '
                              'all must be unicode',):
                    raise
                newenv = {}
                for key, value in env.items():
                    newenv[unicode(key)] = unicode(value)
                env = newenv
                doCreate()
        except pywintypes.error, pwte:
            if not _dumbwin32proc._invalidWin32App(pwte):
                # This behavior isn't _really_ documented, but let's make it
                # consistent with the behavior that is documented.
                raise OSError(pwte)
            else:
                # look for a shebang line.  Insert the original 'command'
                # (actually a script) into the new arguments list.
                sheb = _dumbwin32proc._findShebang(command)
                if sheb is None:
                    raise OSError(
                        "%r is neither a Windows executable, "
                        "nor a script with a shebang line" % command)
                else:
                    args = list(args)
                    args.insert(0, command)
                    cmdline = quoteArguments(args)
                    origcmd = command
                    command = sheb
                    try:
                        # Let's try again.
                        doCreate()
                    except pywintypes.error, pwte2:
                        # d'oh, failed again!
                        if _dumbwin32proc._invalidWin32App(pwte2):
                            raise OSError(
                                "%r has an invalid shebang line: "
                                "%r is not a valid executable" % (
                                    origcmd, sheb))
                        raise OSError(pwte2)

        # close handles which only the child will use
        win32file.CloseHandle(hStderrW)
        win32file.CloseHandle(hStdoutW)
        win32file.CloseHandle(hStdinR)

        # set up everything
        self.stdout = _pollingfile._PollableReadPipe(
            self.hStdoutR,
            lambda data: self.proto.childDataReceived(1, data),
            self.outConnectionLost)

        self.stderr = _pollingfile._PollableReadPipe(
                self.hStderrR,
                lambda data: self.proto.childDataReceived(2, data),
                self.errConnectionLost)

        self.stdin = _pollingfile._PollableWritePipe(
            self.hStdinW, self.inConnectionLost)

        for pipewatcher in self.stdout, self.stderr, self.stdin:
            self._addPollableResource(pipewatcher)


        # notify protocol
        self.proto.makeConnection(self)

        self._addPollableResource(_dumbwin32proc._Reaper(self))


def install(useGtk=True):
    """
    Configure the twisted mainloop to be run inside the gtk mainloop.

    @param useGtk: should glib rather than GTK+ event loop be
        used (this will be slightly faster but does not support GUI).
    """
    reactor = GtkWin32Reactor(useGtk)
    from twisted.internet.main import installReactor
    installReactor(reactor)
    return reactor


__all__ = ['install']
