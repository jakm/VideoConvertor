# -*- coding: utf8 -*-
"""
Provides GUI of application. Create instance of VideoConvertorGUI and run
main().
"""

import pygtk
pygtk.require20()
import gtk

import sys

if sys.platform == 'win32':
    import win32reactor
    win32reactor.install()
else:
    from twisted.internet import gtk2reactor
    gtk2reactor.install()

import logging
import os
import os.path
from datetime import datetime

from twisted.internet import defer, reactor

from config import Configuration
from scheduler import Queue, Scheduler
from utils import (get_install_dir, get_app_dir, get_version, setup_logging,
                   async_function, encode, cached_property)


class VideoConvertorGUI(object):
    """
    Main GUI class. Builds main window and handles all signals. Contains
    independent scheduler that takes tasks from queue and starts processes.
    """
    last_row_id = 0

    def __init__(self):
        """
        Initialize logging, build main window, load application's configuration
        and prepare queue of tasks and scheduler.
        """
        setup_logging()

        self.logger = logging.getLogger(self.__class__.__name__)

        self.config = Configuration()

        self._init_ui()

        self.tasks_queue = Queue(self.tasks_liststore)
        self.scheduler = Scheduler(self.tasks_queue)

    def _init_ui(self):
        """
        Build main window from xml, connect signals and bind window's widgets
        with object's atributs.
        """
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

        version = get_version()

        title = 'Video Convertor'
        if version:
            title += (' v%s' % version)

        self.main_window.set_title(title)

        self.main_window.connect('destroy', lambda widget, *data: self.close())
        self.main_window.connect('delete-event', self.check_closing)
        self.main_window.show_all()

    def _set_widget_objects(self, builder):
        '''
        Bind window's widgets with object's attributes.
        @param builder gtk.Builder
        '''
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
        """
        Run GTK application - start reactor.
        """
        self.logger.info('Starting application')
        reactor.run()

    def close(self):
        """
        Close window - stop reactor.
        """
        self.logger.info('Terminating application')
        reactor.stop()

    def check_closing(self, widget, *data):
        """
        Check if closing of window is allowed. When conversion is running we
        can't close window.
        @return True when closing is disabled, otherwise False
        """
        if self.scheduler.running:
            msg = 'Probíhá konverze! Před vypnutím aplikace ji ukončete.'
            self.show_info_dialog(msg)
            return True

    @cached_property
    def video_file_chooser(self):
        """
        Return file chooser prepared to select video files. Object is created
        by lazy way and cached.
        @return FileChooser
        """
        filter_ = gtk.FileFilter()
        filter_.set_name('Video soubory')
        for extension in ('avi', 'mpg', 'mpeg', 'ogv', 'mkv', 'mov', 'mp4',
                          'vob', 'wmv'):
            filter_.add_pattern('*.' + extension)

        file_chooser = FileChooser(self.main_window, 'Video soubory ...',
                                   filters=(filter_,))

        return file_chooser

    @cached_property
    def subtitles_file_chooser(self):
        """
        Return file chooser prepared to select subtitles files. Object is
        created by lazy way and cached.
        @return FileChooser
        """
        filter_ = gtk.FileFilter()
        filter_.set_name('Soubory titulků')
        for extension in ('sub', 'srt', 'txt'):
            filter_.add_pattern('*.' + extension)

        file_chooser = FileChooser(self.main_window, 'Soubory titulků ...',
                                   filters=(filter_,), select_multiple=False)

        return file_chooser

    def on_add_file_button_clicked(self, widget, *data):
        """
        Open dialog to choose video files and append them to queue.
        """
        file_names = self.video_file_chooser.open_dialog()

        for file_name in file_names:
            self.add_file_name(file_name)

    def add_file_name(self, file_name):
        """
        Create valid datarow and append it to queue.
        @param file_name str, Name of file to append
        """
        self.logger.debug('Appending file: %s', file_name)

        pixbuf = self.get_image_pixbuf('gtk-select-font')

        row_id = self.last_row_id
        self.last_row_id += 1

        datarow = (row_id, file_name, None, False, pixbuf, False)
        self.tasks_queue.append(datarow)

    def get_image_pixbuf(self, stock_id):
        """
        Get pixbuf of stock-image.
        @param stock_id str, stock id
        @return gtk.gdk.Pixbuf
        """
        image = gtk.Image()
        pixbuf = image.render_icon(stock_id, gtk.ICON_SIZE_BUTTON)
        return pixbuf

    def on_files_liststore_row_inserted(self, widget, *data):
        """
        Set queue's widget sensitive when some row was added.
        """
        if self.has_files():
            self.files_treeview.set_sensitive(True)

    @defer.inlineCallbacks
    def on_files_liststore_row_deleted(self, widget, *data):
        """
        Set queue's widget insensitive when last row as removed.
        @return t.i.d.Deferred
        """
        yield self.set_rows_selected(False)
        if not self.has_files():
            self.files_treeview.set_sensitive(False)

    @defer.inlineCallbacks
    def on_files_treeview_cursor_changed(self, widget, *data):
        """
        When no row is selected, set file's widgets insensitive. When some rows
        are selected and no one is running, set file's widgets sensitive.
        If any of selected is running, can't set file's widgets sensitive.
        @return t.i.d.Deferred
        """
        rows = yield self.get_selected_rows()
        if len(rows) == 0:
            yield self.set_rows_selected(False)
        else:
            column = self._get_column_no('running')
            any_running = any([row[column] for row in rows])
            yield self.set_rows_selected(not any_running)

    def has_files(self):
        """
        @return bool, True when queue contains any task, otherwise False.
        """
        return not self.tasks_queue.empty()

    @defer.inlineCallbacks
    def get_selected_paths(self):
        """
        @return tuple or None, Return treeview's paths of selected rows. Or None
            when no row is selected.
        @return t.i.d.Deferred
        """
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
        """
        Return selected rows or empty list.
        @return t.i.d.Deferred, list, List of gtk.TreeModelRow
        """
        tree_paths = yield self.get_selected_paths()

        if tree_paths is None:
            defer.returnValue([])

        rows = [self.tasks_queue[path] for path in tree_paths]

        defer.returnValue(rows)

    @defer.inlineCallbacks
    def set_rows_selected(self, selected):
        """
        Set file's widgets sensitive and show subtitles path of selected rows.
        @param selected bool, If True set sensitive, otherwise set insensitive.
        @return t.i.d.Deferred
        """
        self.remove_file_button.set_sensitive(selected)
        self.up_button.set_sensitive(selected)
        self.down_button.set_sensitive(selected)
        self.add_subtitles_button.set_sensitive(selected)
        self.remove_subtitles_button.set_sensitive(selected)

        yield self.set_subtitles_entry()

    @defer.inlineCallbacks
    def set_conversion_running(self, set_running):
        """
        Start spinner and update widgets to running state and vice versa.
        @param set_running bool
        @return t.i.d.Deferred
        """
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
        """
        Remove selected files.
        @return t.i.d.Deferred
        """
        rows = yield self.get_selected_rows()
        column = self._get_column_no('file_path')
        for row in rows:
            self.logger.debug('Removing file: %s', row[column])

            self.tasks_queue.remove(row)

    @defer.inlineCallbacks
    def on_add_subtitles_button_clicked(self, widget, *data):
        """
        Open dialog to choose subtitles file and bind them with selected rows.
        @return t.i.d.Deferred
        """
        rows = yield self.get_selected_rows()

        if len(rows) == 0:
            return

        file_names = self.subtitles_file_chooser.open_dialog()

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
        """
        Show subtitles path, when one row with subtitles is selected. If there
        are selected more rows show wildcard. Or reset entry if no row is
        selected or doesn't contain subtitles.
        @return t.i.d.Deferred
        """
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
        """
        Remove subtitles from selected rows.
        @return t.i.d.Deferred
        """
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
        """
        Move selected rows up in queue.
        @return t.i.d.Deferred
        """
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
        """
        Move selected rows down in queue.
        @return t.i.d.Deferred
        """
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
        """
        Start or stop conversion in context of scheduler. If queue is empty
        show error message and immediately return.
        @return t.i.d.Deferred
        """
        if not self.scheduler.running:
            if not self.scheduler.has_tasks():
                self.show_info_dialog('Není naplánována žádná úloha')
                return

            self.logger.debug('Starting conversion')
            yield self.start_conversion()
        else:
            self.logger.debug('Stopping conversion')
            yield defer.succeed(self.scheduler.cancel())

    @defer.inlineCallbacks
    def on_pause_button_clicked(self, widget, *data):
        """
        Pause running or resume stopped conversion in context of scheduler.
        @return t.i.d.Deferred
        """
        assert self.scheduler.running

        if not self.scheduler.paused:
            self.logger.debug('Pausing conversion')
            yield self.set_conversion_paused(True)
        else:
            self.logger.debug('Resuming conversion')
            yield self.set_conversion_paused(False)

    @defer.inlineCallbacks
    def start_conversion(self):
        """
        Switch widgets to running state, start conversion, wait to finish
        (nonblocking), show report and witch widgets back.
        @return t.i.d.Deferred
        """
        try:
            yield self.set_conversion_running(True)

            yield self.scheduler.start()

            yield self.show_report_and_log_errors()

        finally:
            yield self.set_conversion_running(False)

    @defer.inlineCallbacks
    def set_conversion_paused(self, set_paused):
        """
        If pausing stop spinner and pause scheduler, otherwise start spinner
        and resume scheduler.
        @param set_paused bool
        @return t.i.d.Deferred
        """
        if set_paused:
            yield self.spinner.stop()
        else:
            yield self.spinner.start()

        if set_paused:
            self.scheduler.pause()
        else:
            self.scheduler.resume()

    @defer.inlineCallbacks
    def show_report_and_log_errors(self):
        """
        If tasks were finished with done status, show info dialog.
        If tasks were finished with failed or incomplete status, show error
        dialog with complete report and store error log.
        @return t.i.d.Deferred
        """
        if not self.scheduler.tasks_failed and not self.scheduler.tasks_incomplete:
            msg = 'Úspěšně dokončeno %d úloh.' % len(self.scheduler.tasks_done)
            self.show_info_dialog(msg)
        else:
            error_log_name = 'MencoderErrors_%s.log' % datetime.now()
            # colon is not allowed in windows path
            error_log_name = error_log_name.replace(':', '-')

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
                                      for task in self.scheduler.tasks_failed])
            tasks_incomplete = '\n'.join([task.input_file
                                          for task in self.scheduler.tasks_incomplete])

            message = message_template % (len(self.scheduler.tasks_done),
                                          len(self.scheduler.tasks_failed),
                                          len(self.scheduler.tasks_incomplete),
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
        dialog.destroy()

    @async_function
    def write_error_log(self, log_name):
        """
        Write errorlog file.
        @param log_name str, Path to log file
        @return t.i.d.Deferred
        """

        def format_task(task):
            return ('Task: input_file="%s", sub_file="%s", output_file="%s"'
                    % (task.input_file, task.sub_file, task.output_file))

        def write_section(f, section_title, tasks):
            record_template = '{0}\n\nreturncode:{1}\n\n\n{2}'
            data = (record_template.format(format_task(task),
                                           task.process.returncode,
                                           task.process.stderr)
                    for task in tasks)

            msg = '\n>>>>>> {0}\n\n\n'.format(section_title)

            separator = '\n\n\n------------------------------------------\n\n\n'
            msg += separator.join(data)

            f.write(encode(msg))

        try:
            log_dir_path = os.path.join(get_app_dir(), 'log')
            log_file_path = os.path.join(log_dir_path, log_name)

            if not os.path.exists(log_dir_path):
                os.mkdir(log_dir_path)

            with file(log_file_path, 'a') as f:
                write_section(f, 'FAILED TASKS', self.scheduler.tasks_failed)
                write_section(f, 'INCOMPLETE TASKS', self.scheduler.tasks_incomplete)
        except:
            import traceback
            self.logger.critical(traceback.format_exc())

    def _get_column_no(self, column):
        column_no = {'id': 0,  'file_path': 1, 'sub_path': 2, 'has_sub': 3,
                     'subpix': 4, 'running': 5}[column]
        return column_no


class FileChooser(object):
    """
    Wrapper around gtk.FileChooserDialog. Stores folder from last choose and
    when is openned next time set current folder to it.
    """

    _last_folder = os.path.expanduser('~')  # shared state, variable will be
                                            # accessed by instance's properties

    def __init__(self, parent, title, filters=(), select_multiple=True):
        self.parent = parent
        self.title = title
        self.filters = filters
        self.select_multiple = select_multiple

    def open_dialog(self):
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                   gtk.STOCK_OPEN, gtk.RESPONSE_OK)

        dialog = gtk.FileChooserDialog(title=self.title,
                                       parent=self.parent,
                                       action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                       buttons=buttons,
                                       backend=None)
        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.set_select_multiple(self.select_multiple)
        for filter_ in self.filters:
            dialog.set_filter(filter_)

        if self.last_folder:
            dialog.set_current_folder(self.last_folder)

        try:
            response = dialog.run()

            if response != gtk.RESPONSE_OK:
                return []

            # user confirmed dialog

            current_folder = dialog.get_current_folder()
            if current_folder:
                self.last_folder = current_folder

            file_names = dialog.get_filenames()

            return file_names
        finally:
            dialog.destroy()

    @property
    def last_folder(self):
        return FileChooser._last_folder

    @last_folder.setter
    def last_folder(self, value):
        FileChooser._last_folder = value


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

    def destroy(self):
        self.dialog.destroy()

    def close(self):
        self.dialog.hide()
        self.dialog.destroy()

    def set_message(self, message):
        self.message_buffer.set_text(message)
