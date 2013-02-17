# -*- coding: utf8 -*-

import shlex
import cStringIO
import subprocess
import threading
import time

import ConfigReader
import Logger as logger

class VideoConvertorError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class VideoConvertorFactory(object):
    def __init__(self, configFile):
        self.__loadConfig(configFile)
    
    def __loadConfig(self, filepath):
        reader = ConfigReader.ConfigReader(filepath)
        config = reader.ReadConfig()
        
        for key in ('input_file_alias', 'output_file_alias', 'convert_command', 'subtitle_params_alias', 'subtitle_params', 'subtitle_file_alias'):
            if not key in config:
                msg = 'konfigurační klíč %s není zadán' % key
                logger.writeLines(msg)
                raise VideoConvertorError(msg)
    
        self.config = config
    
    def createInstance(self, inputFile, subFile, outputFile):
        return VideoConvertor(self.config, inputFile, subFile, outputFile)

class VideoConvertor():
    def __init__(self, config, inputFile, subFile, outputFile):
        self._process = None
        self._processOutput = None
        
        self.config = config
        self.inputFile = inputFile
        self.subFile = subFile
        self.outputFile = outputFile
    
    @property
    def _processState(self):
        assert self._process
        
        state = self._process.poll()
        if state and state != 0:
            logger.writeLines('konverze skončila s chybami')
        return state

    def process(self):
        assert not self._process or self._processState is not None
        
        inputFileAlias = self.config['input_file_alias']
        outputFileAlias = self.config['output_file_alias']
        convertCommand = self.config['convert_command']
        #convertProgressRegexpModule = self.config['convert_progress_regexp_module']
        #progressRegexpModule = load_module(convertProgressRegexpModule)
        #self.progressRegexp = get_class(progressRegexpModule, 'ProgressRegexp')()
          
        convertCommand = convertCommand.replace(inputFileAlias, self.inputFile)
        convertCommand = convertCommand.replace(outputFileAlias, self.outputFile)
        
        convertCommand = self.__extendCmdBySub(self.subFile, convertCommand)
        
        logger.writeLines('spouštím konverzní proces: ' + convertCommand)
        
        #TODO: self._processOutput <- docasny soubor, po dobehnuti procesu ulozit do logu
        
        args = shlex.split(convertCommand)
        self._process = subprocess.Popen(args, stdout=self._processOutput, stderr=self._processOutput, bufsize=4096)

    def cancelProcess(self):
        if self.isProcessing():
            logger.writeLines('konverzní proces přerušen')
            self._process.terminate()
  
    def isProcessing(self):
        return (self._processState is None)
  
    def getReturnCode(self):
        return self._processState
            
  
    def getProgress(self):
        raise NotImplementedError # TODO: progress z cli
  
    def __extendCmdBySub(self, subFile, convertCommand):
        subParams = ''
        if subFile:
            subFileAlias = self.config['subtitle_file_alias']
            subParams = self.config['subtitle_params']
            subParams = subParams.replace(subFileAlias, subFile)
        
        subParamsAlias = self.config['subtitle_params_alias']
        convertCommand = convertCommand.replace(subParamsAlias, subParams)
        return convertCommand
