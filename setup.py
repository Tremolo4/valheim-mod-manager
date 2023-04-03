from distutils.core import setup
import py2exe

#setup(console=['vaelstrom/__main__.py'])

setup(
    options = {'py2exe': {'bundle_files': 1, 'compressed': True}},
    windows = [
        {
            'script': "vaelstrom/__main__.py",
            'dest_base': 'vaelstrom',
        }
    ],
    zipfile = None,
)
