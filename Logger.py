# -*- coding: utf8 -*-

import datetime

class Logger(object):
    def __init__(self, filepath):
        self.file = open(filepath, 'w')

    def writeLines(self, message):
        lines = message.split('\n')
        for line in lines:
            self.file.write('[' + str(datetime.datetime.now()) + ']\t' + line + '\n')

    def close(self):
        if not self.file.closed:
            self.file.close()

    def __del__(self):
        self.close()