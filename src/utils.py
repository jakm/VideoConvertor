# -*- coding: utf8 -*-

import functools

from twisted.internet import protocol


def singleton(cls):
    """
    Decorator. Create singleton from decorated class.
    """

    instances = {}

    def getinstance():
        if cls not in instances:
            instances[cls] = cls()
        return instances[cls]
    return getinstance


def get_install_dir():
    import os.path
    import sys

    return os.path.dirname(sys.argv[0])


def get_app_dir():
    import os
    import os.path

    user_home = os.path.expanduser('~')
    app_dir = os.path.join(user_home, '.videoconvertor')

    if not os.path.exists(app_dir):
        os.mkdir(app_dir)

    return app_dir


def setup_logging():
    import logging
    import os.path
    from config import Configuration

    config = Configuration()

    levels_map = {'CRITICAL': logging.CRITICAL, 'ERROR': logging.ERROR,
                  'WARNING': logging.WARNING, 'INFO': logging.INFO,
                  'DEBUG': logging.DEBUG}

    level_str = config.get('logging', 'level')
    filename = config.get('logging', 'filename')

    try:
        level = levels_map[level_str]
    except KeyError:
        default = logging.INFO
        print ('Unknown logging level %s, using default %s'
               % (level_str, logging.getLevelName(default)))
        level = default

    if filename is None or filename == '':
        filename = 'stdout'

    if filename == 'stdout':
        filepath = None
    else:
        filepath = os.path.join(get_app_dir(), filename)

    print ("Openning log '%s' with level %s"
           % (filepath if filepath else filename, logging.getLevelName(level)))

    logging.basicConfig(level=level, filename=filepath)


def async_function(fnc):
    """
    Dekorator. Dekorovana funkce bude spustena v samostatnem vlakne a vracet
    bude t.i.d.Deferred.
    """
    from twisted.internet import threads

    @functools.wraps(fnc)
    def wrapper(*args, **kwargs):
        return threads.deferToThread(fnc, *args, **kwargs)
    return wrapper


class WatchingProcessProtocol(protocol.ProcessProtocol):
    """
    Process protocol, ktery sleduje ukonceni procesu a vyvola callback sveho
    deferredu.
    """
    def __init__(self, deferred):
        """
        Ulozi si identifikator procesu (vypisuje se do logu), vytvori novy
        deferred a ziska logger.
        @param deferred t.i.d.Deferred
        """
        self.deferred = deferred

    def processExited(self, status):
        """
        Po ukonceni procesu vyvola errback deferredu protokolu. Jako parametr
        predava t.i.e.ProcessDone nebo t.i.e.ProcessTerminated obsahujici
        navratovou hodnotu nebo cislo signalu, ktery proces zabil.
        """
        self.deferred.errback(status)
