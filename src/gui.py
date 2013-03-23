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
from utils import get_install_dir, get_app_dir, setup_logging, async_function
from process import ConversionProcess


class Task(object):
    input_file = None
    sub_file = None
    output_file = None
    row_id = None
    process = None

    def __str__(self):
        return "<Task '%s'>" % self.input_file


class VideoConvertorGUI(object):
    last_row_id = 0

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

        signals = {'on_files_liststore_row_inserted': self.on_files_liststore_row_inserted,
                   'on_files_liststore_row_deleted': self.on_files_liststore_row_deleted,
                   'on_files_treeview_cursor_changed': self.on_files_treeview_cursor_changed,
                   'on_add_file_button_clicked': self.on_add_file_button_clicked,
                   'on_remove_file_button_clicked': self.on_remove_file_button_clicked,
                   'on_add_subtitles_button_clicked': self.on_add_subtitles_button_clicked,
                   'on_remove_subtitles_button_clicked': self.on_remove_subtitles_button_clicked,
                   'on_up_button_clicked': self.on_up_button_clicked,
                   'on_down_button_clicked': self.on_down_button_clicked,
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

        row_id = self.last_row_id
        self.last_row_id += 1

        datarow = (row_id, file_name, None, False, pixbuf, False)
        self.tasks_liststore.append(datarow)

    def get_image_pixbuf(self, stock_id):
        image = gtk.Image()
        pixbuf = image.render_icon(stock_id, gtk.ICON_SIZE_BUTTON)
        return pixbuf

    def on_files_liststore_row_inserted(self, widget, *data):
        if self.has_files():
            self.files_treeview.set_sensitive(True)

    @defer.inlineCallbacks
    def on_files_liststore_row_deleted(self, widget, *data):
        yield self.set_rows_selected(False)
        if not self.has_files():
            self.files_treeview.set_sensitive(False)

    @defer.inlineCallbacks
    def on_files_treeview_cursor_changed(self, widget, *data):
        rows = yield self.get_selected_rows()
        if len(rows) == 0:
            yield self.set_rows_selected(False)
        else:
            column = self._get_column_no('running')
            any_running = any([row[column] for row in rows])
            yield self.set_rows_selected(not any_running)

    def has_files(self):
        return (len(self.tasks_liststore) > 0)

    @defer.inlineCallbacks
    def get_selected_paths(self):
        # HACK: becouse we are in single thread, we need some delay before
        # checking actual selection
        from twisted.internet import task
        yield task.deferLater(reactor, 0, lambda: None)

        selection = self.files_treeview.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)

        if selection.count_selected_rows() == 0:
            defer.returnValue(None)

        tree_model, tree_paths = selection.get_selected_rows()

        defer.returnValue(tree_paths)

    @defer.inlineCallbacks
    def get_selected_rows(self):
        tree_paths = yield self.get_selected_paths()

        if tree_paths is None:
            defer.returnValue([])

        rows = [self.tasks_liststore[path] for path in tree_paths]

        defer.returnValue(rows)

    @defer.inlineCallbacks
    def set_rows_selected(self, selected):
        self.remove_file_button.set_sensitive(selected)
        self.up_button.set_sensitive(selected)
        self.down_button.set_sensitive(selected)
        self.add_subtitles_button.set_sensitive(selected)
        self.remove_subtitles_button.set_sensitive(selected)

        yield self.set_subtitles_entry()

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
        rows = yield self.get_selected_rows()
        column = self._get_column_no('file_path')
        for row in rows:
            self.logger.debug('Removing file: %s', row[column])

            self.remove_row(row)

    def remove_row(self, row_to_remove):
        column = self._get_column_no('id')

        id_to_remove = row_to_remove[column]

        for i in range(len(self.tasks_liststore)):
            path = (i,)

            row = self.tasks_liststore[path]
            row_id = row[column]

            if row_id == id_to_remove:
                iter_ = self.tasks_liststore.get_iter(path)
                self.tasks_liststore.remove(iter_)
                break

    @defer.inlineCallbacks
    def on_add_subtitles_button_clicked(self, widget, *data):
        rows = yield self.get_selected_rows()

        if len(rows) == 0:
            return

        filter_ = gtk.FileFilter()
        filter_.set_name('Soubory titulků')
        for extension in ('sub', 'srt', 'txt'):
            filter_.add_pattern('*.' + extension)

        file_names = self.open_file_chooser_dialog('Soubory titulků ...',
                                                   filters=(filter_,),
                                                   select_multiple=False)

        if not file_names:
            return

        file_name = file_names[0]

        for row in rows:
            input_file = row[self._get_column_no('file_path')]
            self.logger.debug('Adding subtitles to entry %s: %s',
                              input_file, file_name)

            row[self._get_column_no('sub_path')] = file_name
            row[self._get_column_no('has_sub')] = True

        yield self.set_subtitles_entry()

    @defer.inlineCallbacks
    def set_subtitles_entry(self):
        rows = yield self.get_selected_rows()

        column = self._get_column_no('sub_path')

        if len(rows) == 0:
            self.subtitles_entry.set_text('')

        elif len(rows) == 1:
            file_name = rows[0][column]

            if file_name is None:
                file_name = ''

            self.subtitles_entry.set_text(file_name)
        else:
            any_has_subtitles = any([row[column] for row in rows])

            if any_has_subtitles:
                self.subtitles_entry.set_text('~~~~~~')
            else:
                self.subtitles_entry.set_text('')

    @defer.inlineCallbacks
    def on_remove_subtitles_button_clicked(self, widget, *data):
        rows = yield self.get_selected_rows()

        for row in rows:
            input_file = row[self._get_column_no('file_path')]
            self.logger.debug('Removing subtitles to entry %s',
                              input_file)

            row[self._get_column_no('sub_path')] = None
            row[self._get_column_no('has_sub')] = False

        yield self.set_subtitles_entry()

    @defer.inlineCallbacks
    def on_up_button_clicked(self, widget, *data):
        paths = yield self.get_selected_paths()

        if len(paths) == 0:
            return

        model = self.tasks_liststore

        selection = self.files_treeview.get_selection()

        for path in paths:
            row = path[0]
            if row > 0:
                this = tuple(model[row])
                prev = tuple(model[row-1])
                model[row-1] = this
                model[row] = prev

                selection.unselect_path(row)
                selection.select_path(row-1)

    @defer.inlineCallbacks
    def on_down_button_clicked(self, widget, *data):
        paths = yield self.get_selected_paths()

        if len(paths) == 0:
            return

        model = self.tasks_liststore
        row_count = len(model)

        selection = self.files_treeview.get_selection()

        # we have to move bottom row first
        paths = reversed(sorted(paths))

        for path in paths:
            row = path[0]
            if row < row_count - 1:
                this = tuple(model[row])
                next = tuple(model[row+1])
                model[row+1] = this
                model[row] = next

                selection.unselect_path(row)
                selection.select_path(row+1)

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
        column = self._get_column_no('running')

        for row in iter(self.tasks_liststore):
            row[column] = False

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
        return (len(self.get_rows_not_running()) > 0)

    def get_top_task(self):
        rows = self.get_rows_not_running()

        if len(rows) == 0:
            return None

        row = rows[0]

        input_file_name = row[self._get_column_no('file_path')]
        output_file_name = self.extend_file_name(input_file_name)

        self.logger.debug('Input file: %s, output file: %s', input_file_name,
                          output_file_name)

        task = Task()
        task.input_file = input_file_name
        task.sub_file = row[self._get_column_no('sub_path')]
        task.output_file = output_file_name
        task.row_id = row[self._get_column_no('id')]

        return task

    def get_rows_not_running(self):
        rows_not_running = []

        column = self._get_column_no('running')
        for row in iter(self.tasks_liststore):
            if row[column] is not True:
                rows_not_running.append(row)

        return rows_not_running

    def set_task_started(self, task):
        column_running = self._get_column_no('running')
        row = self.get_row_by_id(task.row_id)
        row[column_running] = True

    def get_row_by_id(self, row_id):
        column_id = self._get_column_no('id')
        for row in iter(self.tasks_liststore):
            if row[column_id] == row_id:
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

        row = self.get_row_by_id(task.row_id)
        self.remove_row(row)

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
            log_dir_path = os.path.join(get_app_dir(), 'log')
            log_file_path = os.path.join(log_dir_path, log_name)

            if not os.path.exists(log_dir_path):
                os.mkdir(log_dir_path)

            with file(log_file_path, 'a') as f:
                write_section(f, 'FAILED TASKS', self.tasks_failed)
                write_section(f, 'INCOMPLETE TASKS', self.tasks_incomplete)
        except:
            import traceback
            self.logger.critical(traceback.format_exc())

    def _get_column_no(self, column):
        column_no = {'id': 0,  'file_path': 1, 'sub_path': 2, 'has_sub': 3,
                     'subpix': 4, 'running': 5}[column]
        return column_no


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
