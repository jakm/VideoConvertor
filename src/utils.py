# -*- coding: utf8 -*-

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


def setup_logging():
    import logging

    #logging.basicConfig(level=logging.INFO, file='convertor.log')
    logging.basicConfig(level=logging.DEBUG)


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
