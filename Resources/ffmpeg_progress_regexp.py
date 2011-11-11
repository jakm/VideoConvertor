## -*- coding: utf8 -*-
#
#import re
#
#class ProgressRegexp(object):
#    def __init__(self):
#        pattern = r'\A.*^[ \t]+Duration:[ \t]+(?P<duration>[\w:\.]+),.+\Z'
#        self.regexp1 = re.compile(pattern, re.MULTILINE | re.IGNORECASE | re.DOTALL)
#        pattern = r'\A.*?(^frame=.+time=\d+.+$)*?^frame=.+time=(?P<time>\d+).+$.*\Z' # TODO vyresit pattern
#        self.regexp2 = re.compile(pattern, re.MULTILINE | re.IGNORECASE | re.DOTALL)
#        
#        self.duration = None
#
#    def GetProgress(self, stdout):
#        if not self.duration:
#            result = self.regexp1.match(stdout)
#            if result:
#                d = result.group('duration')
#                # format hh:mm:ss.tt
#                d = d[:d.index('.')]
#                # format hh:mm:ss
#                d = d.split(':')
#                self.duration = int(d[0]) * 3600 + int(d[1]) * 60 + int(d[2])
#        
#        result = self.regexp2.match(stdout)
#        if result and self.duration:
#            time = int(result.group('time'))
#            return time * 100 / self.duration
#        else:
#            return 0