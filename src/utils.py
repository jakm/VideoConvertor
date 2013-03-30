# -*- coding: utf8 -*-
"""
Provides miscellaneous useful functions and classes.
"""

import functools

from twisted.internet import protocol


def encode(string):
    """
    Encode string with preferred encoding.
    @param string str, String to encode
    @return str
    """
    import locale
    encoding = locale.getpreferredencoding()
    return string.encode(encoding)


def decode(string):
    """
    Decode string with preferred encoding.
    @param string str, String to decode
    @return str
    """
    import locale
    encoding = locale.getpreferredencoding()
    return string.decode(encoding)


def singleton(cls):
    """
    Decorator. Create singleton from decorated class.
    @param cls type, Singleton class
    @return object, Instance of class
    """

    instances = {}

    def getinstance():
        if cls not in instances:
            instances[cls] = cls()
        return instances[cls]
    return getinstance


def get_version():
    """
    Return application's version. Use module _pkgdata generated by setup.py.
    If _pkgdata doesn't exist return None.
    @return str
    """
    try:
        from _pkgdata import version

        return version
    except ImportError:
        return None


def get_install_dir():
    """
    Return path where application is installed. Use module _pkgdata generated
    by setup.py. If _pkgdata doesn't exist get directory from first command
    argument (path to executable).
    @return str
    """
    try:
        from _pkgdata import install_path

        return install_path
    except ImportError:
        import os.path
        import sys

        return os.path.dirname(sys.argv[0])


def get_app_dir():
    """
    Return application's directory in user's home directory. Create new if
    doesn't exist.
    @return str
    """
    import os
    import os.path

    user_home = os.path.expanduser('~')
    app_dir = os.path.join(user_home, '.videoconvertor')

    if not os.path.exists(app_dir):
        os.mkdir(app_dir)

    return app_dir


def setup_logging():
    """
    Set up logging module according to options in application's configuration
    file.
    """
    import logging
    import os.path
    from twisted.python import log
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

    # http://twistedmatrix.com/documents/current/core/howto/logging.html#auto3
    observer = log.PythonLoggingObserver()
    observer.start()

    print ("Openning log '%s' with level %s"
           % (filepath if filepath else filename, logging.getLevelName(level)))

    logging.basicConfig(level=level, filename=filepath)


def async_function(fnc):
    """
    Decorator. Decorated function will by executed in standalone thread and
    will return t.i.d.Deferred.
    @param fnc callable, Function or method to decorate
    @return function
    """
    from twisted.internet import threads

    @functools.wraps(fnc)
    def wrapper(*args, **kwargs):
        return threads.deferToThread(fnc, *args, **kwargs)
    return wrapper


# see http://code.activestate.com/recipes/576563-cached-property/
def cached_property(f):
    """returns a cached property that is calculated by function f"""
    def get(self):
        try:
            return self._property_cache[f]
        except AttributeError:
            self._property_cache = {}
            x = self._property_cache[f] = f(self)
            return x
        except KeyError:
            x = self._property_cache[f] = f(self)
            return x

    return property(get)


class WatchingProcessProtocol(protocol.ProcessProtocol):
    """
    ProcessProtocol that is watching termination of process and callbacks owns
    deferred.
    """
    def __init__(self, deferred):
        """
        Save deferred.
        @param deferred t.i.d.Deferred
        """
        self.deferred = deferred

    def processExited(self, status):
        """
        Raise errback of protocol's deferred after process termination. Pass
        t.i.e.ProcessDone or t.i.e.ProcessTerminated as parameter. It contains
        return value or signal number (that killed the process)
        """
        self.deferred.errback(status)
