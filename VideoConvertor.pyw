#!/usr/bin/env python
# -*- coding: utf8 -*-

import os
import sys

import VideoConvertorGUI

if __name__ == '__main__':
    os.chdir(os.path.dirname(sys.argv[0]))
    
    gui = VideoConvertorGUI.VideoConvertorGUI()
    gui.main()
