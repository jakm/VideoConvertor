# -*- coding: utf8 -*-
"""
Provides class implementing conversion process.
"""

import logging
import shlex
import sys
import tempfile

from twisted.internet import defer, error, reactor

from config import Configuration
from utils import WatchingProcessProtocol, async_function, encode, decode


class ConversionProcess():
    """
    Class impolementing conversion process. Run command defined in application's
    configuration file and control it. When process is finished unexpectedly,
    log its returncode and stderr and stdout.

    State of process coluld be checked by this properties: started, finished,
    paused, cancelled, pid. When process is finished its status is in additional
    properties: returncode, stderr, stdout.

    Process support this operations: run, terminate, pause, resume.
    """
    def __init__(self, input_file, sub_file, output_file, log_stdout=False):
        """
        Store information about input and output files and subtitles. Store if
        log stdout and set object's attributes.
        @param input_file str, Path to input file
        @param sub_file str, Path to subtitles file
        @param output_file str, Path to output file
        @param log_stdout bool, Store stdout after process finish
        """
        self.input_file = input_file
        self.sub_file = sub_file
        self.output_file = output_file
        self.log_stdout = log_stdout

        self.config = Configuration()
        self.logger = logging.getLogger(self.__class__.__name__)

        self.process_transport = None
        self.process_protocol = None

        self.started = False
        self.finished = False
        self.paused = False
        self.cancelled = False
        self.deferred = defer.Deferred()
        self.deferred.addErrback(self.process_exited)

        self.pid = None
        self.returncode = None
        self.stderr = None
        self.stdout = None

    def run(self):
        """
        Star conversion process.
        @return t.i.d.Deferred
        """
        assert not self.started

        conversion_command = self.get_conversion_command()
        conversion_command = encode(conversion_command)

        args = shlex.split(conversion_command)
        executable = args[0]

        self.open_stdout_log()
        self.open_stderr_log()

        proto = WatchingProcessProtocol(self.deferred)

        proto.outReceived = lambda data: self.stdout_log.write(data)
        proto.errReceived = lambda data: self.stderr_log.write(data)

        self.logger.info('Starting conversion process of %s', self.input_file)

        kwargs = {}

        if sys.platform == 'win32':
            import win32process
            kwargs['win32flags'] = win32process.CREATE_NO_WINDOW

        self.process_transport = reactor.spawnProcess(proto, executable, args, **kwargs)

        self.process_protocol = proto
        self.pid = self.process_transport.pid
        self.started = True

        return self.deferred

    def terminate(self):
        """
        Terminate running process. It means terminate OS's process and cancel
        deferred.
        """
        if self.finished:
            return

        self.logger.info('Terminating conversion process of %s', self.input_file)

        try:
            self.process_transport.signalProcess('TERM')
        except error.ProcessExitedAlready:
            return  # process already exited, so it was callbacked

        self.deferred.cancel()

    def pause(self):
        """
        Pause process running.
        """
        assert self.started
        assert not self.finished
        assert not self.paused

        p = self._get_psutil_process()
        if p:
            p.suspend()
            self.paused = True
        else:
            self.logger.debug('psutil process is None')

    def resume(self):
        """
        Resume paused process.
        """
        assert self.started
        assert not self.finished
        assert self.paused

        self.paused = False

        p = self._get_psutil_process()
        if p:
            p.resume()
        else:
            self.logger.debug('psutil process is None')

    def get_conversion_command(self):
        """
        Make conversion command from patterns in application's config file and
        process's attributes.
        @return str, Conversion command to execute
        """
        if sys.platform in ('win32', 'cygwin'):
            convertor_exe = self.config.get('command', 'convertor_exe_win')
        else:
            convertor_exe = self.config.get('command', 'convertor_exe_unix')

        convertor_exe = '"' + convertor_exe + '"'  # spaces in path

        input_file_alias = self.config.get('command', 'input_file_alias')
        output_file_alias = self.config.get('command', 'output_file_alias')
        convertor_args = self.config.get('command', 'convertor_args')

        convertor_args = convertor_args.replace(input_file_alias,
                                                self.input_file)
        convertor_args = convertor_args.replace(output_file_alias,
                                                self.output_file)

        convertor_args = self.extend_command_by_sub(self.sub_file,
                                                    convertor_args)

        conversion_command = convertor_exe + ' ' + convertor_args

        self.logger.debug('Convert command: ' + conversion_command)

        return conversion_command

    def extend_command_by_sub(self, sub_file, conversion_command):
        """
        Expand command's alias for subtitles with params or nothing
        if subtitles are not requested.
        @param sub_file str, Path of subtitles file
        @param conversion_command str, Command without expanded alias for
            subtitles
        @return str, Expanded command
        """
        sub_params = ''
        if sub_file:
            sub_file_alias = self.config.get('command', 'subtitle_file_alias')
            sub_params = self.config.get('command', 'subtitle_params')
            sub_params = sub_params.replace(sub_file_alias, sub_file)

        sub_params_alias = self.config.get('command', 'subtitle_params_alias')
        conversion_command = conversion_command.replace(sub_params_alias,
                                                        sub_params)
        return conversion_command

    def open_stderr_log(self):
        """
        Open temporary file to write stderr of process.
        @return int, FD of file
        """
        self.stderr_log = tempfile.TemporaryFile()
        return self.stderr_log.fileno()

    def open_stdout_log(self):
        """
        Open temporary file to write stdout of process.
        @return int, FD of file
        """
        self.stdout_log = tempfile.TemporaryFile()
        return self.stdout_log.fileno()

    @defer.inlineCallbacks
    def process_exited(self, failure):
        """
        Callbacked when OS's process is finished. Set status finished, store
        returncode and process's logs.
        @param failure t.p.f.Failure, t.i.e.ProcessDone or
            t.i.e.ProcessTerminated
        @return t.i.d.Deferred
        """
        self.finished = True

        status_type = failure.trap(error.ProcessDone, error.ProcessTerminated)

        try:
            status = failure.value
            if status_type is error.ProcessDone:
                self.returncode = 0
            elif status_type is error.ProcessTerminated:
                if status.exitCode is not None:
                    self.returncode = status.exitCode
                elif status.signal is not None:
                    self.returncode = -1 * status.signal
                else:
                    raise ValueError('Unknown exit status')

            self.logger.info('Conversion process of %s exited with status %s',
                             self.input_file, self.returncode)

            self.stderr = yield self.read_from_temp_file(self.stderr_log)

            if self.log_stdout:
                self.stdout = yield self.read_from_temp_file(self.stdout_log)
        finally:
            self.stdout_log.close()
            self.stderr_log.close()

    @async_function
    def read_from_temp_file(self, log_file):
        """
        Read data from log of process.
        @param log_file str, Path to file with log
        @return t.i.d.Deferred, str
        """
        log_file.seek(0)
        buff = log_file.read()
        data = decode(buff)
        return data

    def _get_psutil_process(self):
        # psutil provides cross-platform process stop & cont orders
        import psutil
        p = psutil.Process(self.pid)
        return (None if p.status in (psutil.STATUS_DEAD, psutil.STATUS_ZOMBIE) else p)
