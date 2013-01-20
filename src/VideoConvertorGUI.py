#!/usr/bin/env python
# -*- coding: utf8 -*-

import os
import cStringIO
import sys
import traceback

import pygtk
pygtk.require20()
import gtk
import gobject

import Logger as logger

import VideoConvertor

class VideoConvertorGUI(object):
    def __init__(self):
        builder = gtk.Builder()
        builder.add_from_file('Resources/VideoConvertor.glade')
        
        signals = { 'on_inputFile_file-set': self.__on_inputFile_fileset,
                    'on_processBtn_clicked': self.on_processBtn_clicked,
                    'on_mainWindow_delete_event': gtk.main_quit }
        builder.connect_signals(signals)
    
        self.mainWindow = builder.get_object('mainWindow')
        self.inputFile = builder.get_object('inputFile')
        self.subFile = builder.get_object('subtitleFile')
        self.outputDir = builder.get_object('outputDir')
        
        self.__setupFilters(builder.get_object('videoFilter'), builder.get_object('subFilter'))
        
        self.mainWindow.show_all()
    
    def main(self):
        logger.writeLines(sys.argv[0] + ' spuštěn')
        try:
            gtk.main()
        except BaseException as err:
            logger.writeLines('zachycena neošetřená výjimka v metodě main()')
            logger.writeLines(str(err))
            buff = cStringIO.StringIO()
            traceback.print_exc(file=buff)
            logger.writeLines(buff.readlines())
            buff.close()
            raise
        finally: # posledni moznost ukoncit potomka
            if hasattr(self, 'videoConvertor') and self.videoConvertor._process and self.videoConvertor.isProcessing(): # TODO: zde musim kontrolovat tridu VideoConvertor
                logger.writeLines('konverzní proces ukončen v metodě main()')
                self.videoConvertor.cancelProcess()
        logger.writeLines(sys.argv[0] + ' ukončen')
    
    def on_processBtn_clicked(self, widget, data = None):
        inputFile = self.inputFile.get_filename()
        outputDir = self.outputDir.get_filename()
        subFile = self.subFile.get_filename()
        
        if not inputFile or not outputDir:
            self.__showErrorDialog('Vyplňte pole vstup a výstup!')
            return
        
        outputFile = os.path.join(outputDir, os.path.split(inputFile)[1] + '.AVI')
        
        if not self.__canAccessFiles(inputFile, subFile, outputFile):
            return
        
        if self.__startProcess(inputFile, subFile, outputFile):
            self.mainWindow.set_sensitive(False)
            self.progressWindow = ProgressWindow(self)
            self.progressWindow.show()
            self.timer = gobject.timeout_add (36000, self.__updateProgress)
        else:
            self.__showErrorDialog('Při spouštění konverzního procesu vznikla chyba.')
    
    def __canAccessFiles(self, inputFile, subFile, outputFile):
        if not os.access(inputFile, os.R_OK):
            msg = 'Soubor %s není přístupný pro čtení' % inputFile
            logger.writeLines(msg)
            self.__showErrorDialog(msg)
            return False
        
        if subFile:
            if not os.access(subFile, os.R_OK):
                msg = 'Soubor %s není přístupný pro čtení' % inputFile
                logger.writeLines(msg)
                self.__showErrorDialog(msg)
                return False
        
        if not os.access(os.path.split(outputFile)[0], os.X_OK | os.W_OK):
            msg = 'Adresář %s není přístupný pro zápis' % outputFile
            logger.writeLines(msg)
            self.__showErrorDialog(msg)
            return False
        
        if os.path.exists(outputFile):
            if not self.__showQuestion('Soubor %s existuje. Přepsat?' % outputFile):
                logger.writeLines('akce zrušena uživatelem')
                return False
        
        return True
    
    def __on_inputFile_fileset(self, widget, data = None):
        path = self.inputFile.get_filename()
        _dir = os.path.split(path)[0]
        self.outputDir.set_current_folder(_dir)
    
    def __setupFilters(self, videoFilter, subFilter):
        videoFilter.set_name('Video soubory')
        for extension in ('avi', 'mpg', 'mpeg', 'ogv', 'mkv', 'mov', 'mp4', 'vob', 'wmv'):
            videoFilter.add_pattern('*.' + extension)

        subFilter.set_name('Soubory titulků')
        subFilter.add_pattern('*.sub')
        subFilter.add_pattern('*.srt')
    
    def __startProcess(self, inputFile, subFile, outputFile):
        try:
            factory = VideoConvertor.VideoConvertorFactory('VideoConvertor.config')
            self.videoConvertor = factory.createInstance(inputFile, subFile, outputFile)
            self.videoConvertor.process()
        except Exception as e:
            logger.writeLines('zachycena výjimka konverzního procesu: ' + str(e))
            return False
        
        return True
    
    def cancelProcess(self):
        self.videoConvertor.cancelProcess()
        self.progressWindow.close()
        self.__showInfoDialog('Proces přerušen uživatelem.')
        self.mainWindow.set_sensitive(True)
    
    def __updateProgress(self):
        if self.videoConvertor.isProcessing():
            progress = self.progressWindow.progressbar.get_fraction() + 0.01
            if progress > 1.0:
                progress = 0.0
            self.progressWindow.progressbar.set_fraction(progress)
            return True
        else:
            logger.writeLines('konverzní proces byl ukončen s kódem %d' % self.videoConvertor.getReturnCode())
            self.progressWindow.close()
            if (self.videoConvertor.getReturnCode() == 0):
                self.__showInfoDialog('Proces řádně ukončen.')
            else:
                self.__showInfoDialog('Proces ukončen s chybami.')
            self.mainWindow.set_sensitive(True)
            return False
    
    def __showInfoDialog(self, message):
        md = gtk.MessageDialog(self.mainWindow,
            gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_INFO,
            gtk.BUTTONS_CLOSE, message)
        md.run()
        md.hide()
        md.destroy()
    
    def __showErrorDialog(self, message):
        md = gtk.MessageDialog(self.mainWindow, 
            gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, 
            gtk.BUTTONS_CLOSE, message)
        md.run()
        md.hide()
        md.destroy()

    def __showQuestion(self, message):
        md = gtk.MessageDialog(self.mainWindow, 
            gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_QUESTION, 
            message_format=message)
        md.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        md.add_button(gtk.STOCK_OK, gtk.RESPONSE_OK)
        try:
            response = md.run()
            return response == gtk.RESPONSE_OK
        finally:
            md.hide()
            md.destroy()
        

class ProgressWindow(object):
    def __init__(self, parentObject):
        self.__parentObject = parentObject
        
        builder = gtk.Builder()
        builder.add_from_file('Resources/ProgressWindow.glade')
        
        signals = { 'on_cancelBtn_clicked': self.on_cancelBtn_clicked }
        builder.connect_signals(signals)
    
        self.window = builder.get_object('progressWindow')
        self.window.set_modal(True)
        
        self.progressbar = builder.get_object('progressbar')

    def show(self):
        self.window.show()

    def close(self):
        self.window.hide()
        self.window.destroy()
    
    def on_cancelBtn_clicked(self, widget, data = None):
        VideoConvertorGUI.cancelProcess(self.__parentObject)
    
if __name__ == '__main__':
    os.chdir(os.path.dirname(sys.argv[0]))
    
    gui = VideoConvertorGUI()
    gui.main()
