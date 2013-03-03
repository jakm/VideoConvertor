# -*- coding: utf8 -*-

import pygtk
pygtk.require20()
import gtk

from twisted.internet import gtk2reactor
gtk2reactor.install()

import logging
import os.path
import sys

from twisted.internet import defer, reactor

from utils import get_install_dir, setup_logging
from config import Configuration
#from video_convertor import VideoConvertor


class Task(object):
    input_file = None
    sub_file = None
    output_file = None
    tree_iter = None
    process = None

    def __str__(self):
        return "<Task '%s'>" % self.input_file


class VideoConvertorGUI(object):
    def __init__(self):
        setup_logging()

        self.logger = logging.getLogger(__name__)

        self.processes = set()
        self.conversion_running = False
        self.tasks_done = []
        self.tasks_failed = []

        self.config = Configuration()

        self._init_ui()

    def _init_ui(self):
        builder = gtk.Builder()
        ui_file = os.path.join(get_install_dir(), 'ui', 'main.glade')
        builder.add_from_file(ui_file)

        signals = {'on_add_file_button_clicked': self.on_add_file_button_clicked,
                   'on_files_liststore_row_inserted': self.on_files_liststore_row_inserted,
                   'on_files_liststore_row_deleted': self.on_files_liststore_row_deleted,
                   'on_start_stop_button_clicked': self.on_start_stop_button_clicked}
        builder.connect_signals(signals)

        self._set_widget_objects(builder)

        self.main_window.connect('destroy', lambda widget, *data: self.close())
        self.main_window.show_all()

    def _set_widget_objects(self, builder):
        widgets = ('add_file_button', 'remove_file_button', 'up_button',
                   'down_button', 'files_treeview', 'tasks_liststore',
                   'subtitles_entry', 'add_subtitles_button',
                   'remove_subtitles_button', 'pause_button',
                   'start_stop_button', 'play_image', 'stop_image',
                   'subpix_image', 'main_window')
        go = builder.get_object
        for widget_name in widgets:
            setattr(self, widget_name, go(widget_name))

    def main(self):
        reactor.run()

    def close(self):
        # TODO: vypnout jen tak okno pri converzi nebude mozne, musim vymyslet,
        # jak na to
        reactor.stop()

    def on_add_file_button_clicked(self, widget, *data):
        filter_ = gtk.FileFilter()
        filter_.set_name('Video soubory')
        for extension in ('avi', 'mpg', 'mpeg', 'ogv', 'mkv', 'mov', 'mp4', 'vob', 'wmv'):
            filter_.add_pattern('*.' + extension)

        file_names = self.open_file_chooser_dialog('Video soubory ...',
                                                   filters=(filter_,))

        for file_name in file_names:
            self.add_file_name(file_name)

    def open_file_chooser_dialog(self, title, filters=(), select_multiple=True):
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                   gtk.STOCK_OPEN, gtk.RESPONSE_OK)

        dialog = gtk.FileChooserDialog(title=title,
                                       parent=self.main_window,
                                       action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                       buttons=buttons,
                                       backend=None)
        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.set_select_multiple(select_multiple)
        for filter_ in filters:
            dialog.set_filter(filter_)

        try:
            response = dialog.run()
            if response == gtk.RESPONSE_CANCEL:
                return []

            file_names = dialog.get_filenames()
            return file_names
        finally:
            dialog.destroy()

    def add_file_name(self, file_name):
        self.logger.debug('Appending file: %s', file_name)

        pixbuf = self.get_image_pixbuf('gtk-select-font')

        datarow = (file_name, '', False, pixbuf, False)
        self.tasks_liststore.append(datarow)

    def get_image_pixbuf(self, stock_id):
        image = gtk.Image()
        pixbuf = image.render_icon(stock_id, gtk.ICON_SIZE_BUTTON)
        return pixbuf

    def on_files_liststore_row_inserted(self, widget, *data):
        if self.have_file_names():
            self.set_controls_sensitive(True)

    def on_files_liststore_row_deleted(self, widget, *data):
        if not self.have_file_names():
            self.set_controls_sensitive(False)

    def have_file_names(self):
        return (self.tasks_liststore.get_iter_first() is not None)

    def set_controls_sensitive(self, sensitive):
        self.files_treeview.set_sensitive(sensitive)
        self.remove_file_button.set_sensitive(sensitive)
        self.up_button.set_sensitive(sensitive)
        self.down_button.set_sensitive(sensitive)
        self.add_subtitles_button.set_sensitive(sensitive)
        self.remove_subtitles_button.set_sensitive(sensitive)
        self.start_stop_button.set_sensitive(sensitive)

    @defer.inlineCallbacks
    def on_start_stop_button_clicked(self, widget, *data):
        if not self.conversion_running:
            self.logger.debug('Starting conversion')
            # TODO: zmena ikonky
            # TODO: kontrola tasku
            yield self.start_conversion()
            # TODO: info o ukonceni
            if self.tasks_failed:
                msg = ('Úspěšně dokončeno %d úloh, %d selhalo:\n'
                       % (len(self.tasks_done), len(self.tasks_failed)))
                msg += '\n'.join([task.input_file for task in self.tasks_failed])
                self.show_error_dialog(msg)
                # TODO: zalogovani chyb (task.process.returncode, ...stderr)
            else:
                msg = 'Úspěšně dokončeno %d úloh.' % len(self.tasks_done)
                self.show_info_dialog(msg)
        else:
            self.logger.debug('Stopping conversion')
            yield defer.succeed(self.cancel_conversion)

        # TODO: zmena ikonky

    def start_conversion(self):
        if self.any_task_exists():
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

    def cancel_conversion(self):
        self.remove_all_tasks()

        for process in self.processes:
            self.logger.debug('Terminating: %s', process)
            process.terminate() # TODO: mel by cancelovat i deferredy

    def start_process(self):
        if self.any_task_exists():
            task = self.get_top_task()
            self.logger.debug('Task: %s', task)

            if task is None:
                return

            # >>> TEST

            from mock import MagicMock

            _deferred = defer.Deferred()

            process = MagicMock()
            process.run.return_value = _deferred
            process.deferred = _deferred
            process.terminate.return_value = None

            #_deferred.callback(0)
            _deferred.errback(ValueError('fail'))

            # >>> TEST

            # process = VideoConvertor(task.input_file,
            #                          task.sub_file,
            #                          task.output_file)

            self.logger.info('Created new process object: %s', process)

            process.run()
            self.processes.add(process)

            task.process = process

            self.set_task_started(task)

            process.deferred.addCallback(self.set_task_done, task)
            process.deferred.addErrback(self.set_task_failed, task)
            process.deferred.addBoth(self.task_finished, task)
            process.deferred.addBoth(lambda _: self.processes.remove(process))
            process.deferred.addBoth(lambda _: self.start_process())

            return process.deferred

    def any_task_exists(self):
        return (self.tasks_liststore.get_iter_first() is not None)

    def get_top_task(self):
        # FIXME: napromazava se queue

        tree_iter = self.tasks_liststore.get_iter_first()

        is_running = lambda it: (self._get_value(it, 'running') is True)

        while tree_iter is not None and is_running(tree_iter):
            tree_iter = self.tasks_liststore.iter_next(tree_iter)

        if tree_iter is None:
            return None

        input_file_name = self._get_value(tree_iter, 'file_path')
        output_file_name = self.extend_file_name(input_file_name)

        self.logger.debug('Input file: %s, output file: %s', input_file_name,
                          output_file_name)

        task = Task()
        task.input_file = input_file_name
        task.sub_file = self._get_value(tree_iter, 'sub_path')
        task.output_file = output_file_name
        task.tree_iter = tree_iter

        return task

    def set_task_started(self, task):
        self._set_value(task.tree_iter, 'running', True)

    def set_task_done(self, result, task):
        self.logger.info('Task done: %s', task)
        self.tasks_done.append(task)

        return result

    def set_task_failed(self, failure, task):
        # TODO: zachytit t.i.d.CancelledError, nesmi se zobrazovat v logu

        self.logger.info('Task failed: %s Error: %s', task, failure)
        self.tasks_failed.append(task)

        return failure

    def task_finished(self, result, task):
        self.logger.debug('Task finished: %s', task)

        tree_iter = task.tree_iter
        self._set_value(tree_iter, 'running', False)
        self.tasks_liststore.remove(tree_iter)

        return result

    def remove_all_tasks(self):
        # while self.any_task_exists():
        #     tree_iter = self.tasks_liststore.get_iter_first()
        #     self.tasks_liststore.remove(tree_iter)

        self.logger.debug('Removing all tasks from queue')

        tree_iter = self.tasks_liststore.get_iter_first()
        while tree_iter is not None:
            previous = tree_iter
            tree_iter = self.tasks_liststore.get_iter_first()
            self.tasks_liststore.remove(previous)

    def extend_file_name(self, file_name):
        elements = file_name.split('.')
        if len(elements) > 1:
            return '.'.join(elements[0:-1] + ['NEW'] + elements[-1:])
        else:
            return '.'.join(elements + ['NEW'])

    def show_info_dialog(self, message):
        dialog = gtk.MessageDialog(self.main_window,
                                   gtk.DIALOG_DESTROY_WITH_PARENT,
                                   gtk.MESSAGE_INFO,
                                   gtk.BUTTONS_CLOSE, message)
        dialog.run()
        dialog.destroy()

    def show_error_dialog(self, message):
        dialog = ErrorDialog(message)
        dialog.run()

    def _get_value(self, tree_iter, column):
        column_no = {'file_path': 0, 'sub_path': 1, 'has_sub': 2, 'subpix': 3,
                     'running': 4}[column]
        return self.tasks_liststore.get_value(tree_iter, column_no)

    def _set_value(self, tree_iter, column, value):
        column_no = {'file_path': 0, 'sub_path': 1, 'has_sub': 2, 'subpix': 3,
                     'running': 4}[column]
        return self.tasks_liststore.set_value(tree_iter, column_no, value)


class ErrorDialog(object):
    def __init__(self, message):
        assert isinstance(message, str)

        builder = gtk.Builder()
        ui_file = os.path.join(get_install_dir(), 'ui', 'error_dialog.glade')
        builder.add_from_file(ui_file)

        signals = {'on_close_button_clicked': lambda widget, *data: self.close()}
        builder.connect_signals(signals)

        self._set_widget_objects(builder)

        self.set_message(message)

        self.dialog.connect('destroy', lambda widget, *data: self.close())

    def _set_widget_objects(self, builder):
        widgets = ('dialog', 'message_buffer')
        go = builder.get_object
        for widget_name in widgets:
            setattr(self, widget_name, go(widget_name))

    def run(self):
        self.dialog.run()

    def close(self):
        self.dialog.hide()
        self.dialog.destroy()

    def set_message(self, message):
        self.message_buffer.set_text(message)
