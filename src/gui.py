# -*- coding: utf8 -*-

import pygtk
pygtk.require20()
import gtk

from twisted.internet import gtk2reactor
gtk2reactor.install()

import logging
import locale
import os
import os.path
from datetime import datetime
from decimal import Decimal

from twisted.internet import defer, reactor
from twisted.python import failure

from config import Configuration
from utils import get_install_dir, setup_logging, async_function
from process import ConversionProcess


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

        self.logger = logging.getLogger(self.__class__.__name__)

        self.processes = set()
        self.conversion_running = False
        self.conversion_paused = False
        self.tasks_done = []
        self.tasks_incomplete = []
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
                   'on_files_treeview_cursor_changed': self.on_files_treeview_cursor_changed,
                   'on_remove_file_button_clicked': self.on_remove_file_button_clicked,
                   'on_start_stop_button_clicked': self.on_start_stop_button_clicked,
                   'on_pause_button_clicked': self.on_pause_button_clicked}
        builder.connect_signals(signals)

        self._set_widget_objects(builder)

        self.main_window.connect('destroy', lambda widget, *data: self.close())
        self.main_window.show_all()

    def _set_widget_objects(self, builder):
        widgets = ('add_file_button', 'remove_file_button', 'up_button',
                   'down_button', 'files_treeview', 'tasks_liststore',
                   'subtitles_entry', 'add_subtitles_button',
                   'remove_subtitles_button',
                   'start_stop_button', 'pause_button', 'spinner',
                   'play_image', 'stop_image', 'subpix_image',
                   'main_window')
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
        if self.has_files():
            self.files_treeview.set_sensitive(True)

    def on_files_liststore_row_deleted(self, widget, *data):
        self.set_rows_selected(False)
        if not self.has_files():
            self.files_treeview.set_sensitive(False)

    @defer.inlineCallbacks
    def on_files_treeview_cursor_changed(self, widget, *data):
        tree_iters = yield self.get_selected_rows_iters()
        if tree_iters is None:
            self.set_rows_selected(False)
        else:
            any_running = any([self._get_value(tree_iter, 'running')
                               for tree_iter in tree_iters])
            self.set_rows_selected(not any_running)

    def has_files(self):
        return (self.tasks_liststore.get_iter_first() is not None)

    @defer.inlineCallbacks
    def get_selected_rows_iters(self):
        # HACK: becouse we are in single thread, we need some delay before
        # checking actual selection
        from twisted.internet import task
        yield task.deferLater(reactor, 0, lambda: None)

        selection = self.files_treeview.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)

        if selection.count_selected_rows() == 0:
            defer.returnValue(None)

        tree_model, tree_paths = selection.get_selected_rows()

        tree_iters = [tree_model.get_iter(tree_path) for tree_path in tree_paths]

        defer.returnValue(tree_iters)

    def set_rows_selected(self, file_in_queue):
        self.remove_file_button.set_sensitive(file_in_queue)
        self.up_button.set_sensitive(file_in_queue)
        self.down_button.set_sensitive(file_in_queue)
        self.add_subtitles_button.set_sensitive(file_in_queue)
        self.remove_subtitles_button.set_sensitive(file_in_queue)

    @defer.inlineCallbacks
    def set_conversion_running(self, set_running):
        self.conversion_running = set_running

        if set_running:
            yield self.spinner.start()
        else:
            yield self.spinner.stop()

        image = (self.stop_image if set_running else self.play_image)
        self.start_stop_button.set_image(image)
        text = ('Zastavit' if set_running else 'Spustit')
        self.start_stop_button.set_label(text)
        self.pause_button.set_sensitive(set_running)

    @defer.inlineCallbacks
    def on_remove_file_button_clicked(self, widget, *data):
        tree_iters = yield self.get_selected_rows_iters()
        for tree_iter in tree_iters:
            self.logger.debug('Removing file: %s',
                              self._get_value(tree_iter, 'file_path'))
            self.tasks_liststore.remove(tree_iter)

    @defer.inlineCallbacks
    def on_start_stop_button_clicked(self, widget, *data):
        if not self.conversion_running:
            if not self.any_task_exists():
                self.show_info_dialog('Není naplánována žádná úloha')
                return

            self.logger.debug('Starting conversion')
            yield self.start_conversion()
        else:
            self.logger.debug('Stopping conversion')
            yield defer.succeed(self.cancel_conversion())

    @defer.inlineCallbacks
    def on_pause_button_clicked(self, widget, *data):
        assert self.conversion_running

        if not self.conversion_paused:
            self.logger.debug('Pausing conversion')
            yield self.set_conversion_paused(True)
        else:
            self.logger.debug('Resuming conversion')
            yield self.set_conversion_paused(False)

    @defer.inlineCallbacks
    def start_conversion(self):
        try:
            yield self.set_conversion_running(True)

            self.reset_finished_tasks()

            yield self.schedule_tasks()

            yield self.show_report_and_log_errors()

        finally:
            yield self.set_conversion_running(False)

    def cancel_conversion(self):
        self.stop_running_processes()
        self.reset_tasks_queue()

    def stop_running_processes(self):
        while True:
            try:
                process = self.processes.pop()
                self.logger.debug('Terminating: %s', process)
                process.terminate()
            except KeyError:
                break

    def reset_tasks_queue(self):
        is_running = lambda it: (self._get_value(it, 'running') is True)

        tree_iter = self.tasks_liststore.get_iter_first()
        while tree_iter is not None and is_running(tree_iter):
            self._set_value(tree_iter, 'running', False)
            tree_iter = self.tasks_liststore.iter_next(tree_iter)

    def reset_finished_tasks(self):
        del self.tasks_done[:]
        del self.tasks_failed[:]
        del self.tasks_incomplete[:]

    @defer.inlineCallbacks
    def set_conversion_paused(self, set_paused):
        self.conversion_paused = set_paused

        if set_paused:
            yield self.spinner.stop()
        else:
            yield self.spinner.start()

        for process in self.processes:
            if set_paused:
                process.pause()
            else:
                process.resume()

    @defer.inlineCallbacks
    def resume_conversion(self):
        yield self.spinner.start()
        self.conversion_paused = False

    def schedule_tasks(self):
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

    def start_process(self):
        if self.any_task_exists():
            task = self.get_top_task()
            self.logger.debug('Task: %s', task)

            if task is None:
                return

            process = ConversionProcess(task.input_file,
                                        task.sub_file,
                                        task.output_file)

            self.logger.info('Created new process object: %s', process)

            process.run()
            self.processes.add(process)

            task.process = process

            self.set_task_started(task)

            process.deferred.addBoth(self.task_finished, task)
            process.deferred.addBoth(lambda _: self.processes.remove(process))
            process.deferred.addBoth(lambda _: self.start_process())

            return process.deferred

    def any_task_exists(self):
        return (self.get_iter_not_running() is not None)

    def get_top_task(self):
        tree_iter = self.get_iter_not_running()

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

    def get_iter_not_running(self):
        is_running = lambda it: (self._get_value(it, 'running') is True)

        tree_iter = self.tasks_liststore.get_iter_first()
        while tree_iter is not None and is_running(tree_iter):
            tree_iter = self.tasks_liststore.iter_next(tree_iter)

        if tree_iter is None:
            return None

        return tree_iter

    def set_task_started(self, task):
        self._set_value(task.tree_iter, 'running', True)

    @defer.inlineCallbacks
    def task_finished(self, result, task):

        cancelled = (isinstance(result, failure.Failure)
                     and isinstance(result.value, defer.CancelledError))
        if cancelled:
            self.logger.debug('Task cancelled: %s', task)
            defer.returnValue(None)

        returncode = task.process.returncode
        self.logger.info('Task %s finished with return code: %s', task,
                         returncode)

        if returncode == 0:
            is_complete = yield self.is_task_complete(task)
            if is_complete:
                self.tasks_done.append(task)
            else:
                self.logger.warning('Task %s seems be incomplete', task)
                self.tasks_incomplete.append(task)
        else:
            # TODO: pro stderr samostatny log soubor
            self.tasks_failed.append(task)

        self.tasks_liststore.remove(task.tree_iter)

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

    @defer.inlineCallbacks
    def show_report_and_log_errors(self):
        if not self.tasks_failed and not self.tasks_incomplete:
            msg = 'Úspěšně dokončeno %d úloh.' % len(self.tasks_done)
            self.show_info_dialog(msg)
        else:
            error_log_name = 'MencoderErrors_%s.log' % datetime.now()

            yield self.write_error_log(error_log_name)

            message_template = '''
Úspěšně dokončeno %d úloh, selhalo %d úloh a %d úloh je nekompletních.

Nekompletně dokončené úlohy mohou mít poškozený vstupní soubor!

Chybové výstupy byly uloženy do logu %s.

===================================================

Neúspěšné úlohy:

%s

Nekompletní úlohy:

%s
'''

            tasks_failed = '\n'.join([task.input_file
                                      for task in self.tasks_failed])
            tasks_incomplete = '\n'.join([task.input_file
                                          for task in self.tasks_incomplete])

            message = message_template % (len(self.tasks_done),
                                          len(self.tasks_failed),
                                          len(self.tasks_incomplete),
                                          error_log_name,
                                          tasks_failed,
                                          tasks_incomplete)

            self.show_error_dialog(message)

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

    @async_function
    def write_error_log(self, log_name):
        encoding = locale.getpreferredencoding()

        def format_task(task):
            return ('Task: input_file="%s", sub_file="%s", output_file="%s"'
                    % (task.input_file, task.sub_file, task.output_file))

        def write_section(f, section_title, tasks):
            record_template = '{0}\nreturncode:{1}\n\n\n{2}'
            data = (record_template.format(format_task(task),
                                           task.process.returncode,
                                           task.process.stderr)
                    for task in tasks)

            msg = '>>>>>> {0}\n\n\n'.format(section_title)

            separator = '\n\n\n------------------------------------------\n\n\n'
            msg += separator.join(data)

            f.write(msg.encode(encoding))

        try:
            log_dir_path = os.path.join(get_install_dir(), 'log')
            log_file_path = os.path.join(log_dir_path, log_name)

            if not os.path.exists(log_dir_path):
                os.mkdir(log_dir_path)

            with file(log_file_path, 'a') as f:
                write_section(f, 'FAILED TASKS', self.tasks_failed)
                write_section(f, 'INCOMPLETE TASKS', self.tasks_incomplete)
        except:
            import traceback
            self.logger.critical(traceback.format_exc())

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
