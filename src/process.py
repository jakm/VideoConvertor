# -*- coding: utf8 -*-

import locale
import logging
import shlex
import sys
import tempfile

from twisted.internet import defer, error, reactor

from config import Configuration
from utils import WatchingProcessProtocol, async_function


class ConversionProcess():
    def __init__(self, input_file, sub_file, output_file, log_stdout=False):
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
        assert not self.started

        conversion_command = self.get_conversion_command()

        args = shlex.split(conversion_command)
        executable = args[0]

        self.open_stdout_log()
        self.open_stderr_log()

        proto = WatchingProcessProtocol(self.deferred)

        proto.outReceived = lambda data: self.stdout_log.write(data)
        proto.errReceived = lambda data: self.stderr_log.write(data)

        self.process_transport = reactor.spawnProcess(proto, executable, args)

        self.process_protocol = proto
        self.pid = self.process_transport.pid
        self.started = True

        return self.deferred

    def terminate(self):
        if self.finished:
            return

        try:
            self.process_transport.signalProcess('TERM')
        except error.ProcessExitedAlready:
            return  # process already exited, so it was callbacked

        self.deferred.cancel()

    def pause(self):
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
        if sys.platform in ('win32', 'cygwin'):
            convertor_exe = self.config.get('command', 'convertor_exe_win')
        else:
            convertor_exe = self.config.get('command', 'convertor_exe_unix')

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
        self.stderr_log = tempfile.TemporaryFile()
        return self.stderr_log.fileno()

    def open_stdout_log(self):
        self.stdout_log = tempfile.TemporaryFile()
        return self.stdout_log.fileno()

    @defer.inlineCallbacks
    def process_exited(self, failure):
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

            self.stderr = yield self.read_from_temp_file(self.stderr_log)

            if self.log_stdout:
                self.stdout = yield self.read_from_temp_file(self.stdout_log)
        finally:
            self.stdout_log.close()
            self.stderr_log.close()

    @async_function
    def read_from_temp_file(self, temp_file):
        temp_file.seek(0)
        buff = temp_file.read()
        encoding = locale.getpreferredencoding()
        data = buff.decode(encoding)
        return data

    def _get_psutil_process(self):
        # psutil provides cross-platform process stop & cont orders
        import psutil
        p = psutil.Process(self.pid)
        return (None if p.status in (psutil.STATUS_DEAD, psutil.STATUS_ZOMBIE) else p)
