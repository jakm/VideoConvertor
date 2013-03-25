# -*- coding: utf8 -*-

import logging
import os
import sys

from decimal import Decimal

from twisted.internet import defer
from twisted.python import failure

from config import Configuration
from process import ConversionProcess
from utils import async_function


class Queue(object):
    def __init__(self, liststore):
        self.liststore = liststore

    def __getitem__(self, key):
        row = self.liststore[key]
        return QueueRow(row)

    def __iter__(self):
        for row in iter(self.liststore):
            yield QueueRow(row)

    def __len__(self):
        return len(self.liststore)

    def empty(self):
        return (len(self.liststore) == 0)

    def append(self, row):
        self.liststore.append(row)

    def remove(self, row):
        for i in range(len(self.liststore)):
            path = (i,)

            row_ = QueueRow(self.liststore[path])

            if row_['id'] == row['id']:
                iter_ = self.liststore.get_iter(path)
                self.liststore.remove(iter_)
                return True
        else:
            return False


class QueueRow(object):
    column_map = {'id': 0,  'file_path': 1, 'sub_path': 2, 'has_sub': 3,
                  'subpix': 4, 'running': 5}

    def __init__(self, row):
        self.row = row

    def __eq__(self, other):
        if not isinstance(other, QueueRow):
            return False

        return (self['id'] == other['id'])

    def __getitem__(self, key):
        column = self._get_column(key)
        return self.row[column]

    def __setitem__(self, key, value):
        column = self._get_column(key)
        self.row[column] = value

    def _get_column(self, key):
        if isinstance(key, int):
            return key
        if isinstance(key, str):
            return self.column_map[key]
        raise TypeError('Key should be int or str')


class Task(object):
    input_file = None
    sub_file = None
    output_file = None
    row_id = None
    process = None

    def __str__(self):
        return "<Task '%s'>" % self.input_file


class Scheduler(object):
    def __init__(self, tasks_queue):
        self.tasks_queue = tasks_queue

        self.logger = logging.getLogger(self.__class__.__name__)

        self._running = False
        self._paused = False
        self._cancelled = False
        self.processes = set()
        self.tasks_done = []
        self.tasks_incomplete = []
        self.tasks_failed = []

        self.config = Configuration()

    @property
    def running(self):
        return self._running

    @property
    def paused(self):
        return self._paused

    @property
    def cancelled(self):
        return self._cancelled

    def start(self):
        assert not self.running

        self._cancelled = False  # reset previous state
        self._running = True

        self.reset_finished_tasks()

        d = self.schedule_tasks()

        def reset_scheduler(res):
            self._running = False

        d.addBoth(reset_scheduler)

        return d

    def cancel(self):
        assert self.running

        self._cancelled = True

        # in this section we callback on processes's deferreds, it's
        # callbacks need to know that conversion is cancelled
        self.stop_running_processes()
        self.reset_tasks_queue()

    def pause(self):
        assert self.running

        self._paused = True

        for process in self.processes:
            process.pause()

    def resume(self):
        assert self.running

        self._paused = False

        for process in self.processes:
            process.resume()

    def reset_finished_tasks(self):
        del self.tasks_done[:]
        del self.tasks_failed[:]
        del self.tasks_incomplete[:]

    def schedule_tasks(self):
        if self.has_tasks():
            processes_count = self.config.getint('processes', 'count')
            self.logger.debug('Count of processes to run: %s', processes_count)

            defers = []
            while len(self.processes) < processes_count:
                d = self.start_process()

                if d is None:
                    break

                defers.append(d)

            if not defers:
                return

            dl = defer.DeferredList(defers)
            return dl

    def start_process(self):
        if self.cancelled:
            return

        if self.has_tasks():
            task = self.get_top_task()
            self.logger.debug('Task: %s', task)

            if task is None:
                return

            process = ConversionProcess(task.input_file,
                                        task.sub_file,
                                        task.output_file)

            self.logger.debug('Created new process object: %s', process)

            process.run()
            self.processes.add(process)

            task.process = process

            self.set_task_started(task)

            process.deferred.addBoth(self.task_finished, task)
            process.deferred.addBoth(lambda _: self.processes.remove(process))
            process.deferred.addBoth(lambda _: self.start_process())

            return process.deferred

    def has_tasks(self):
        return (len(self.get_rows_not_running()) > 0)

    def get_top_task(self):
        rows = self.get_rows_not_running()

        if len(rows) == 0:
            return None

        row = rows[0]

        input_file_name = row['file_path']
        output_file_name = self.extend_file_name(input_file_name)

        self.logger.debug('Input file: %s, output file: %s', input_file_name,
                          output_file_name)

        task = Task()
        task.input_file = input_file_name
        task.sub_file = row['sub_path']
        task.output_file = output_file_name
        task.row_id = row['id']

        return task

    def get_rows_not_running(self):
        rows_not_running = []

        for row in self.tasks_queue:
            if row['running'] is not True:
                rows_not_running.append(row)

        return rows_not_running

    def set_task_started(self, task):
        row = self.get_row_by_id(task.row_id)
        row['running'] = True

    def get_row_by_id(self, row_id):
        for row in iter(self.tasks_queue):
            if row['id'] == row_id:
                return row

        return None

    @defer.inlineCallbacks
    def task_finished(self, result, task):

        cancelled = (isinstance(result, failure.Failure)
                     and isinstance(result.value, defer.CancelledError))
        if cancelled:
            self.logger.debug('Task cancelled: %s', task)
            defer.returnValue(None)

        returncode = task.process.returncode
        self.logger.debug('Task %s finished with return code: %s', task,
                          returncode)

        if returncode == 0:
            # FIXME: doesn't work on win32 platform
            if sys.platform != 'win32':
                is_complete = yield self.is_task_complete(task)

                if is_complete:
                    self.tasks_done.append(task)
                else:
                    self.logger.warning('Task %s seems be incomplete', task)
                    self.tasks_incomplete.append(task)
            else:
                self.tasks_done.append(task)
        else:
            self.tasks_failed.append(task)

        row = self.get_row_by_id(task.row_id)
        self.tasks_queue.remove(row)

        defer.returnValue(result)

    @async_function
    def is_task_complete(self, task):
        input_file_stat = os.stat(task.input_file)
        output_file_stat = os.stat(task.output_file)

        input_file_size = input_file_stat.st_size
        output_file_size = output_file_stat.st_size

        size_ratio = Decimal(output_file_size) / Decimal(input_file_size)

        return (size_ratio > Decimal('0.5'))

    def extend_file_name(self, file_name):
        elements = file_name.split('.')
        if len(elements) > 1:
            new_file_name = '.'.join(elements[0:-1] + ['NEW'])
        else:
            new_file_name = '.'.join(elements + ['NEW'])

        new_file_name += '.avi'

        return new_file_name

    def stop_running_processes(self):
        while True:
            try:
                process = self.processes.pop()
                self.logger.debug('Terminating: %s', process)
                process.terminate()
            except KeyError:
                break

    def reset_tasks_queue(self):
        for row in iter(self.tasks_queue):
            row['running'] = False
