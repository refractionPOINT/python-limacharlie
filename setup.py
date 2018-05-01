from setuptools import setup, Command
import glob
import os
import limacharlie

setup( name = 'limacharlie',
       version = limacharlie.__version__,
       description = 'Python API for LimaCharlie.io',
       url = 'https://limacharlie.io',
       author = limacharlie.__author__,
       author_email = limacharlie.__author_email__,
       license = limacharlie.__license__,
       packages = [ 'limacharlie' ],
       zip_safe = True,
       install_requires = ['gevent'],
       long_description = 'Python API for limacharlie.io, an endpoint detection and response service.' )
