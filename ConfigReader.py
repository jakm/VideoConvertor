# -*- coding: utf8 -*-

import os
import os.path
import sys

class ConfigReader(object):
    def __init__(self, filepath, logger):
        self.filepath = filepath

    def ReadConfig(self):
        if not os.path.exists(self.filepath):
            logger.writeLines('konfigurační soubor %s neexistuje' % filepath)
            sys.exit(1)
        
        if not os.access(self.filepath, os.R_OK):
            logger.writeLines('konfigurační soubor %s není přístupný pro čtení' % filepath)
            sys.exit(1)
        
        try:
            with open(self.filepath, 'r') as f:
                config = {}
                line = self.__readLine(f)
                while line:
                    exec line in {}, config
                    line = self.__readLine(f)
                return config
        except IOError as err:
            logger.writeLines('chyba při čtení konfiguračního souboru %s : %s' % (filepath, str(err)))

    def __readLine(self, f):
        line = f.readline()
        if not line:
            return line
        
        line.split()
        
        while line.endswith('\\'):
            line.replace('\\', '')
            tmp = f.readline()
            if not tmp:
                tmp.split()
                line += tmp
        
        return line        