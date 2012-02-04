#!/usr/bin/env python
# -*- coding: utf8 -*-

import os
import sys

import VideoConvertor

#logger = Logger.Logger('VideoConvertor.' + datetime.datetime.now().time().isoformat() + '.log')
convertor = None

def visitDir(_, directory, files):
    for file in files:
        path = os.path.join(directory, file)
        if os.path.isdir(path):
            continue
        
        fileName, extension = os.path.splitext(path)
        if extension.lower() not in ('.avi', '.mpg', '.mpeg', '.ogv', '.mkv', '.mov', '.mp4', '.vob', '.wmv'):
            continue
                
        bakPath = path + '.bak'
        tmpPath = fileName + '.tmp'
        outPath = fileName + '.avi'
        
        print 'zpracovávám soubor: %s, výstup: %s' % (path, outPath)
        
        if doConversion(path, tmpPath):
            print 'chyba při převodu souboru %s' % path
        
        os.rename(path, bakPath)
        os.rename(tmpPath, outPath)

def doConversion(inputFile, outputFile):
    if not os.access(inputFile, os.R_OK):
        print 'soubor %s není přístupný pro čtení' % inputFile
        return False
    
    if not os.access(os.path.dirname(outputFile), os.X_OK | os.W_OK):
        print 'adresář %s není přístupný pro zápis' % outputFile
        return False
    
    convertor.startProcess(inputFile, None, outputFile)
    convertor._process.wait()
    
    return (convertor.getReturnCode() == 0)

def main(args):
    if len(args) != 1:
        sys.exit(1)
    
    path = args[0]
    
    if not os.path.isdir(path):
        sys.exit(1)
    
    global convertor
    convertor = VideoConvertor.VideoConvertor()
    convertor.loadConfig('VideoConvertor.config')
    
    os.path.walk(path, visitDir, None)

if __name__ == '__main__':
    os.chdir(os.path.dirname(sys.argv[0]))
    main(sys.argv[1:])
