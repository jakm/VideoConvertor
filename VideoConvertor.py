#!/usr/bin/env python
# -*- coding: utf8 -*-

import os.path
import shlex
import subprocess
import sys
import traceback

import pygtk
pygtk.require20()
import gtk
import gobject

import ConfigReader
import Logger

#def load_module(filepath):
#    path, name = os.path.split(filepath)
#    name = name[:name.index('.')]
#    if path:
#        if not path in sys.path:
#            sys.path.append(path)
#    try:
#        return __import__(name)
#    except (ImportError, SyntaxError) as err:
#        return None
#
#def get_class(module, class_name):
#    cls = None
#    try:
#        cls = getattr(module, class_name)
#        if type(cls) is not types.TypeType:
#            raise AttributeError()
#    except AttributeError:
#        cls = None
#    return cls

logger = Logger.Logger('VideoConvertor.log')

class VideoConvertor(object):
    def __init__(self):
        self.loadConfig('VideoConvertor.config')
        
        builder = gtk.Builder()
        builder.add_from_file('Resources/mainWindow.glade')
        
        signals = { 'on_inputFileBtn_clicked': self.on_inputFileBtn_clicked,
                    'on_outputFileBtn_clicked': self.on_outputFileBtn_clicked,
                    'on_processBtn_clicked': self.on_processBtn_clicked,
                    'on_mainWindow_delete_event': gtk.main_quit }
        builder.connect_signals(signals)
    
        self.mainWindow = builder.get_object('mainWindow')
        self.inputFileTxt = builder.get_object('inputFileTxt')
        self.outputFileTxt = builder.get_object('outputFileTxt')
        
        self.mainWindow.show_all()

    def main(self):
        logger.writeLines(sys.argv[0] + ' spuštěn')
        try:
            gtk.main()
        except BaseException as err:
            logger.writeLines('zachycena neošetřená výjimka v metodě main()')
            logger.writeLines(str(err))
            traceback.print_exc(file=logger.file)
            raise
        finally: # posledni moznost ukoncit potomka
            if hasattr(self, 'process') and self.process:
                self.process.poll()
                if self.process.returncode is None:
                    logger.writeLines('konverzní proces ukončen v metodě main()')
                    self.process.terminate()
        logger.writeLines(sys.argv[0] + ' ukončen')

    def openFileChooserDialog(self, open = True):
        chooser = gtk.FileChooserDialog(title='Výběr souboru...')
        
        chooser.set_action(gtk.FILE_CHOOSER_ACTION_OPEN if open else gtk.FILE_CHOOSER_ACTION_SAVE)
        chooser.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        chooser.add_button(gtk.STOCK_OPEN, gtk.RESPONSE_OK)
        
        filter1 = gtk.FileFilter()
        filter1.set_name('Video soubory')
        for extension in ('avi', 'mpg', 'mpeg', 'ogv', 'mkv', 'mov', 'mp4', 'vob', 'wmv'):
            filter1.add_pattern('*.' + extension)
        
        filter2 = gtk.FileFilter()
        filter2.set_name('Všechny soubory')
        filter2.add_pattern('*.*')
        
        chooser.add_filter(filter1)
        chooser.add_filter(filter2)
        chooser.set_filter(filter1)
        
        chooser.set_select_multiple(False)
        chooser.set_current_folder(os.path.expanduser('~'))
        chooser.set_modal(True)
        
        path = None
        response = chooser.run()
        if response == gtk.RESPONSE_OK:
            path = os.path.join(chooser.get_current_folder(), chooser.get_filename())
        
        chooser.emit('close') # TODO destroy?
        
        return path

    def on_inputFileBtn_clicked(self, widget, data = None):
        fileName = self.openFileChooserDialog(open = True)
        if fileName:
            self.inputFileTxt.set_text(fileName)

    def on_outputFileBtn_clicked(self, widget, data = None):
        fileName = self.openFileChooserDialog(open = False)
        if fileName:
            self.outputFileTxt.set_text(fileName)

    def on_processBtn_clicked(self, widget, data = None):
        if not self.inputFileTxt.get_text() or not self.outputFileTxt.get_text():
            self.showErrorDialog('Vyplňte všechna pole!')
            return
        
        if self.startProcess():
            self.progressWindow = ProgressWindow(self)
            self.progressWindow.show()
            self.timer = gobject.timeout_add (36000, self.updateProgress, self.progressWindow)

    def loadConfig(self, filepath):
        reader = ConfigReader.ConfigReader(filepath, logger)
        config = reader.ReadConfig()
        
        for key in ('input_file_alias', 'output_file_alias', 'convert_command'):
            if not key in config:
                logger.writeLines('konfigurační klíč %s není zadán' % key)
                exit(1)
        
        self.config = config

    def updateProgress(self, progressWindow):
        if self.process:
            self.process.poll()
            if self.process.returncode is None:
                progress = progressWindow.progressbar.get_fraction() + 0.01
                if progress > 1.0:
                    progress = 0.0
                self.progressWindow.progressbar.set_fraction(progress)
                return True
            else:
                logger.writeLines('konverzní proces byl ukončen s kódem %d' % self.process.returncode)
                self.process = None
                self.progressWindow.close()
                self.showInfoDialog('Proces řádně ukončen.')
                return False
        else:
            return False
    
    def cancelProcess(self):
        if self.process:
            self.process.poll()
            if self.process.returncode is None:
                logger.writeLines('konverzní proces přerušen uživatelem')
                self.process.terminate()
                self.process = None
                self.progressWindow.close()
                self.showInfoDialog('Proces přerušen uživatelem.')

    def startProcess(self):
        inputAlias = self.config['input_file_alias']
        outputAlias = self.config['output_file_alias']
        convertCommand = self.config['convert_command']
        #convertProgressRegexpModule = self.config['convert_progress_regexp_module']
        #progressRegexpModule = load_module(convertProgressRegexpModule)
        #self.progressRegexp = get_class(progressRegexpModule, 'ProgressRegexp')()
        
        inputPath = self.inputFileTxt.get_text()
        outputPath = self.outputFileTxt.get_text()
        
        if not os.access(inputPath, os.R_OK):
            msg = 'soubor %s není přístupný pro čtení' % inputPath
            logger.writeLines(msg)
            self.showErrorDialog(msg)
            return False
            
        if not os.access(os.path.dirname(outputPath), os.X_OK | os.W_OK):
            msg = 'soubor %s není přístupný pro zápis' % outputPath
            logger.writeLines(msg)
            self.showErrorDialog(msg)
            return False
            
        if os.path.exists(outputPath):
            if not self.showQuestion('Soubor %s existuje. Přepsat?' % outputPath):
                logger.writeLines('akce zrušena uživatelem')
                return False
            
        convertCommand = convertCommand.replace(inputAlias, inputPath)
        convertCommand = convertCommand.replace(outputAlias, outputPath)
            
        logger.writeLines('spouštím konverzní proces: ' + convertCommand)
        logger.file.flush()
        args = shlex.split(convertCommand)
        self.process = subprocess.Popen(args, stdout=logger.file, stderr=logger.file)
        return True
    
    def showInfoDialog(self, message):
        md = gtk.MessageDialog(self.mainWindow,
            gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_INFO,
            gtk.BUTTONS_CLOSE, message)
        md.run()
        md.hide()
        md.destroy()
    
    def showErrorDialog(self, message):
        md = gtk.MessageDialog(self.mainWindow, 
            gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, 
            gtk.BUTTONS_CLOSE, message)
        md.run()
        md.hide()
        md.destroy()

    def showQuestion(self, message):
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
        builder.add_from_file('Resources/progressWindow.glade')
        
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
        VideoConvertor.cancelProcess(self.__parentObject)
    
if __name__ == '__main__':
    videoConvertor = VideoConvertor()
    videoConvertor.main()
