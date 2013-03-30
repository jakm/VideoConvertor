# -*- coding: utf8 -*-
"""
Provides classes used to schedule tasks.
"""

import logging
import os
import sys

from decimal import Decimal

from twisted.internet import defer
from twisted.internet import task as tx_task
from twisted.python import failure

from config import Configuration
from process import ConversionProcess
from utils import async_function


class Queue(object):
    """
    Wrapper around gtk.ListStore used in GUI.
    """
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
    """
    Wrapper around gtk.TreeModelRow used in GUI.
    """
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
    """
    Simple structure that keeps information about running task.
    """
    input_file = None
    sub_file = None
    output_file = None
    row_id = None
    process = None

    def __str__(self):
        return "<Task '%s'>" % self.input_file


class Scheduler(object):
    """
    Class that is scheduling tasks in queue and executing processes. Maximum
    count of running processes is given by configuration. Next task is scheduled
    in occurence of two types of events:
    1. When some process is finished and count of running processes is lower
       than maximum.
    2. When timeout expires and count of running processes is lower than
       maximum. This is useful when user add smaller amount of files than
       available count to queue and ran conversion. And then added next files.
       In this case scheduler check new files and schedule tasks.

    When scheduler is selecting new task from queue, takes top row that is not
    marked as running. Then new process is started and task is marked as runnig.
    Task is removed from queue and according to status of process added to
    tasks_done, tasks_incomplete or tasks_failed after finish of process.

    Scheduler supports this operations: start, cancel, pause and resume. They
    are propagated to running processes. State of of scheduler could be checked
    by this properties: running, paused, cancelled.
    """
    def __init__(self, tasks_queue):
        """
        Store queue of tasks and set object's attributes.
        @param tasks_queue Queue, Queue of tasks
        """
        self.tasks_queue = tasks_queue

        self.logger = logging.getLogger(self.__class__.__name__)

        self._running = False
        self._paused = False
        self._cancelled = False
        self.processes = set()
        self.tasks_done = []
        self.tasks_incomplete = []
        self.tasks_failed = []

        self.scheduler = tx_task.LoopingCall(self.schedule_tasks)
        self.deferred = defer.Deferred()

        self.config = Configuration()

        self.processes_count = self.config.getint('scheduler',
                                                  'processes_count')
        self.logger.debug('Count of processes to run: %s', self.processes_count)

        self.scheduler_timeout = self.config.getint('scheduler',
                                                    'scheduler_timeout')
        self.logger.debug('Scheduler timeout: %s', self.scheduler_timeout)

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
        """
        Start scheduling of queue.
        @return t.i.d.Deferred, None
        """
        assert not self.running

        self._running = True

        self.reset_finished_tasks()

        self.logger.debug('Starting scheduler')
        d = self.scheduler.start(self.scheduler_timeout)

        def scheduler_stopped(res):
            """
            Called when LoopingCall is stopped. Reset scheduler state and
            callback deferred.
            """
            self.logger.debug('Scheduler stopped')

            # reset previous state
            self._running = False
            self._paused = False
            self._cancelled = False

            # set NEW deferred
            d, self.deferred = self.deferred, defer.Deferred()

            d.callback(None)

        d.addBoth(scheduler_stopped)

        return d

    def cancel(self):
        """
        Cancel scheduler and running processes. Reset queue to new processing.
        """
        assert self.running

        self._cancelled = True

        # in this section we callback on processes's deferreds, it's
        # callbacks need to know that conversion is cancelled
        self.stop_running_processes()
        self.reset_tasks_queue()

        self.stop_scheduler()

    def pause(self):
        """
        Pause scheduler and running processes.
        """
        assert self.running

        self._paused = True

        for process in self.processes:
            process.pause()

    def resume(self):
        """
        Resume scheduler and paused processes.
        """
        assert self.running

        self._paused = False

        for process in self.processes:
            process.resume()

    def reset_finished_tasks(self):
        """
        Clear lists with tasks marked as done, failed and incomplete.
        """
        del self.tasks_done[:]
        del self.tasks_failed[:]
        del self.tasks_incomplete[:]

    def schedule_tasks(self):
        """
        Try to schedule tasks. If scheduler is not running or is cancelled or
        paused quietly return back. If there is no task to schedule, stop
        scheduler. Schedule so much tasks how much can, i.e. up to
        maximum of processes. Add rescheduling callback to each started
        process.
        """
        if not self.running:
            return

        if self.cancelled or self.paused:
            return

        if self.nothing_to_schedule():
            self.stop_scheduler()
            return

        self.logger.debug('Schedule tasks')

        def reschedule(res):
            """
            Reschedule immediately after process was finished. When scheduler is
            not running do nothing.
            """
            if self.running:
                self.logger.debug('Reschedule immediately')
                self.schedule_tasks()

        while self.can_schedule_task():
            task = self.get_top_task()
            self.logger.debug('Task: %s', task)

            d = self.start_process(task)
            d.addBoth(reschedule)  # don't wait for timeout, schedule now

    def nothing_to_schedule(self):
        """
        @return bool, True if we have no task to schedule nor running process,
        otherwise False
        """
        return len(self.processes) == 0 and not self.has_tasks()

    def can_schedule_task(self):
        """
        @return bool, True if we have tasks in queue and can start new
        processes, otherwise False
        """
        return len(self.processes) < self.processes_count and self.has_tasks()

    def stop_scheduler(self):
        """
        Stop scheduler when running.
        """
        if self.scheduler.running:
            self.logger.debug('Stopping scheduler')
            self.scheduler.stop()

    def start_process(self, task):
        """
        Prepare process object, start it, add to set of processes and add
        callbacks to clean.
        @param task Task, Task to process
        @return t.i.d.Deferred
        """
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

        return process.deferred

    def has_tasks(self):
        """
        @return bool, True queue contains (non running) tasks, otherwise False
        """
        return (len(self.get_rows_not_running()) > 0)

    def get_top_task(self):
        """
        Return top task in queue that is not set as running.
        @return Task
        """
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
        """
        Return rows in queue that are not marked as running. Rows are sorted
        from top to bottom.
        @return list, List of rows (type QueueRow)
        """
        rows_not_running = []

        for row in self.tasks_queue:
            if row['running'] is not True:
                rows_not_running.append(row)

        return rows_not_running

    def set_task_started(self, task):
        """
        Mark task as running.
        @param task Task
        """
        row = self.get_row_by_id(task.row_id)
        row['running'] = True

    def get_row_by_id(self, row_id):
        """
        Find row in queue by its id. Return row or None if not found.
        @param row_id int, ID of row
        @return QueueRow or None, Row or None if not foud
        """
        for row in iter(self.tasks_queue):
            if row['id'] == row_id:
                return row

        return None

    @defer.inlineCallbacks
    def task_finished(self, result, task):
        """
        Callbacked when process is finished. If deferred has beed cancelled
        return immediately. Otherwise get status of process and append task to
        tasks_done, tasks_incomplete or tasks_failed. Remove task's row from
        queue.
        @return t.i.d.Deferred
        """

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
        """
        Check if task is complete. When size of new file is lower than half of
        original task were probably stopped early.
        @param task Task
        @return t.i.d.Deferred, bool
        """
        input_file_stat = os.stat(task.input_file)
        output_file_stat = os.stat(task.output_file)

        input_file_size = input_file_stat.st_size
        output_file_size = output_file_stat.st_size

        size_ratio = Decimal(output_file_size) / Decimal(input_file_size)

        return (size_ratio > Decimal('0.5'))

    def extend_file_name(self, file_name):
        """
        Extend file name by this pattern: <<some name>>.<<extension>> -->
        <<some name>>.NEW.avi.
        @param file_name str
        @return str
        """
        elements = file_name.split('.')
        if len(elements) > 1:
            new_file_name = '.'.join(elements[0:-1] + ['NEW'])
        else:
            new_file_name = '.'.join(elements + ['NEW'])

        new_file_name += '.avi'

        return new_file_name

    def stop_running_processes(self):
        "Stop every running process."
        while True:
            try:
                process = self.processes.pop()
                self.logger.debug('Terminating: %s', process)
                process.terminate()
            except KeyError:
                break

    def reset_tasks_queue(self):
        """
        Reset queue to new processing, i.e. mark running rows as non-running.
        """
        for row in iter(self.tasks_queue):
            row['running'] = False
