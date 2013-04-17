#!/usr/bin/env python

from distutils.core import setup

from distutils import errors
from distutils.command import install
from distutils.command.build import build
from distutils.command.install import install as install_

import os
import os.path
import sys

VERSION = '2.3'

# platform dependend options
if sys.platform == 'win32':
    install_path = r'C:\Program Files\VideoConvertor'
    scripts = ['src/VideoConvertor.pyw']
else:
    install_path = '/opt/VideoConvertor'
    scripts = ['src/VideoConvertor']

ui_path = os.path.join(install_path, 'ui')

# distutils install package to sys.prefix directory
sys.prefix = install_path

# we want to install package into flat structure
install.INSTALL_SCHEMES.update({
    'unix_prefix': {
        'purelib': '$base',
        'platlib': '$base',
        'headers': '$base',
        'scripts': '$base',
        'data'   : '$base'},
    'nt': {
        'purelib': '$base',
        'platlib': '$base',
        'headers': '$base',
        'scripts': '$base',
        'data'   : '$base'}
})


class convertor_build(build):
    def run(self):
        # do build
        build.run(self)

        _pkgdata = os.path.join(self.build_lib, '_pkgdata.py')

        print 'writing pkgdata to %s' % _pkgdata

        data = ("version = '%s'\n"
                "install_path = r'%s'\n") % (VERSION, install_path)

        with open(_pkgdata, 'w') as f:
            f.write(data)


class convertor_install(install_):
    def finalize_options(self):
        if self.home or self.user:
            raise errors.DistutilsOptionError('Options --home and --user '
                                              'are not allowed by this '
                                              'project.')

        install_.finalize_options(self)


setup(name='VideoConvertor',
      version=VERSION,
      description=('Simple PyGTK utility to converting video to msmpeg4 format '
                   'with subtitles embedding'),
      author='Jakub Matys',
      author_email='matys.jakub@gmail.com',
      url='https://github.com/jakm/VideoConvertor',
      package_dir={'': 'src'},
      py_modules=['config', 'gui', 'process', 'scheduler', 'utils',
                  'win32reactor'],
      data_files=[('', ['config.ini']),
                  ('ui', ['ui/error_dialog.glade', 'ui/main.glade'])],
      scripts=scripts,
      cmdclass={'build': convertor_build,
                'install': convertor_install})
