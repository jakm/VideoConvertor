# -*- coding: utf8 -*-
"""
Provides class to access application's configuration.
"""

import os.path
from ConfigParser import RawConfigParser

from utils import singleton, get_install_dir


@singleton
class Configuration(object):
    """
    Singleton class to access application's configuration.
    """
    def __init__(self):
        self.parser = RawConfigParser()
        config_file = os.path.join(get_install_dir(), 'config.ini')
        self.parser.read(config_file)

    def get(self, section, option):
        return self.parser.get(section, option)

    def getboolean(self, section, option):
        return self.parser.getboolean(section, option)

    def getfloat(self, section, option):
        return self.parser.getfload(section, option)

    def getint(self, section, option):
        return self.parser.getint(section, option)

    def has_option(self, section, option):
        return self.parser.has_option(section, option)

    def has_section(self, section):
        return self.parser.has_section(section)
