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

#import video_convertor
from utils import get_install_dir, setup_logging


class VideoConvertorGUI(object):
    def __init__(self):
        setup_logging()

        self.logger = logging.getLogger(__name__)

        self.processes = set()

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
                   'down_button', 'files_treeview', 'files_liststore',
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
        self.files_liststore.append(datarow)

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
        return self.files_liststore.get_iter_first() != None

    def set_controls_sensitive(self, sensitive):
        self.files_treeview.set_sensitive(sensitive)
        self.remove_file_button.set_sensitive(sensitive)
        self.up_button.set_sensitive(sensitive)
        self.down_button.set_sensitive(sensitive)
        self.add_subtitles_button.set_sensitive(sensitive)
        self.remove_subtitles_button.set_sensitive(sensitive)
        self.start_stop_button.set_sensitive(sensitive)

    def on_start_stop_button_clicked(self, widget, *data):
        pass
