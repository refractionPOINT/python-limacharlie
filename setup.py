import os
import re
from setuptools import setup

# Read __version__ from __init__.py
PACKAGE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "limacharlie")
VERSION_RE = re.compile(
    r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]',
    flags=re.MULTILINE
)

with open(os.path.join(PACKAGE_DIR, "__init__.py"), "r", encoding="utf-8") as f:
    file_content = f.read()

version_match = VERSION_RE.search(file_content)

if version_match:
    version = version_match.group(1)
else:
    raise RuntimeError("Unable to find version string in __init__.py.")

# Read the README.md file for the long description
with open("README.md", "r", encoding="utf-8") as f:
    LONG_DESCRIPTION = f.read()

__version__ = version
__author__ = "Maxime Lamothe-Brassard ( Refraction Point, Inc )"
__author_email__ = "maxime@refractionpoint.com"
__license__ = "Apache v2"
__copyright__ = "Copyright (c) 2020 Refraction Point, Inc"

setup( name = 'limacharlie',
       version = __version__,
       description = 'Python API for LimaCharlie.io',
       long_description = LONG_DESCRIPTION,
       long_description_content_type='text/markdown',
       url = 'https://limacharlie.io',
       author = __author__,
       author_email = __author_email__,
       license = __license__,
       packages = [ 'limacharlie' ],
       zip_safe = True,
       install_requires = [ 'requests', 'passlib', 'pyyaml', 'tabulate', 'termcolor' ],
       entry_points = {
           'console_scripts': [
               'limacharlie=limacharlie.__main__:main',
           ],
       },
)
