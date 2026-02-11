from setuptools import setup, find_packages

__version__ = "4.11.3"
__author__ = "Maxime Lamothe-Brassard ( Refraction Point, Inc )"
__author_email__ = "maxime@refractionpoint.com"
__license__ = "Apache v2"
__copyright__ = "Copyright (c) 2020 Refraction Point, Inc"

setup( name = 'limacharlie',
       version = __version__,
       description = 'Python API for LimaCharlie.io',
       url = 'https://limacharlie.io',
       author = __author__,
       author_email = __author_email__,
       license = __license__,
       packages = find_packages(exclude=['tests', 'tests.*']),
       zip_safe = True,
       install_requires = [ 'requests', 'passlib', 'pyyaml', 'tabulate', 'termcolor', 'pygments', 'rich', 'cryptography>=44.0.1', 'click>=8.0', 'jmespath' ],
       long_description = 'Python API for limacharlie.io, an endpoint detection and response service.',
       entry_points = {
           'console_scripts': [
               'limacharlie=limacharlie.cli:main',
           ],
       },
)
