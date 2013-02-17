# -*- coding: utf8 -*-


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
