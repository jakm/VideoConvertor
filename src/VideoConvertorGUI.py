#!/usr/bin/env python
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

#import VideoConvertor


class VideoConvertorGUI(object):
    def __init__(self):
        logging.basicConfig(file='convertor.log')

        self.logger = logging.getLogger(__name__)

        builder = gtk.Builder()
        builder.add_from_file('ui/main.glade')

        signals = {
            'on_add_file_button_clicked': self.on_add_file_button_clicked}
        builder.connect_signals(signals)

        self._set_widget_objects(builder)

        self.main_window.connect('destroy', lambda widget, *data: self.close())
        self.main_window.show_all()

    def _set_widget_objects(self, builder):
        widgets = ('add_file_button', 'remove_file_button', 'up_button',
                   'down_button', 'files_treeview', 'subtitles_entry',
                   'add_subtitles_button', 'remove_subtitles_button',
                   'pause_button', 'start_stop_button', 'play_image',
                   'stop_image', 'subpix_image', 'main_window')
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

        print file_names

        # TODO: ### toto by asi melo reagovat na vlozeni do treeview ###
        self.remove_file_button.set_sensitive(True)
        self.up_button.set_sensitive(True)
        self.down_button.set_sensitive(True)
        self.add_subtitles_button.set_sensitive(True)
        self.remove_subtitles_button.set_sensitive(True)
        self.start_stop_button.set_sensitive(True)
        # ### ... ###

    def open_file_chooser_dialog(self, title, filters=(), select_multiple=True):
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                   gtk.STOCK_OPEN, gtk.RESPONSE_OK)

        dialog = gtk.FileChooserDialog(title=title,
                                       parent=self.main_window,
                                       action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                       buttons=buttons,
                                       backend=None)
        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.set_current_folder(os.path.expanduser('~'))
        dialog.set_select_multiple(select_multiple)
        for filter_ in filters:
            dialog.set_filter(filter_)

        try:
            response = dialog.run()
            if response == gtk.RESPONSE_CANCEL:
                return []

            file_names = dialog.get_filenames() # TODO: decode ???
            return file_names
        finally:
            dialog.destroy()

if __name__ == '__main__':
    os.chdir(os.path.dirname(sys.argv[0]))

    gui = VideoConvertorGUI()
    gui.main()
