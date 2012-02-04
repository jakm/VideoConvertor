# -*- coding: utf8 -*-

#TODO: pozdeji prepracovat vsechny moduly, aby pouzivali nativni implementaci

import logging

logging.basicConfig(filename='VideoConvertor.log',level=logging.DEBUG)

def writeLines(message):
  if message is list:
      message = '\n'.join(message)
  debug(message)

def debug(msg):
  logging.debug(msg)

def info(msg):
  logging.info(msg)

def warning(msg):
  logging.warning(msg)
