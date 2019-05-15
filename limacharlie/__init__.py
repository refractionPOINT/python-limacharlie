"""limacharlie API for limacharlie.io"""

__version__ = "2.11.6"
__author__ = "Maxime Lamothe-Brassard ( Refraction Point, Inc )"
__author_email__ = "maxime@refractionpoint.com"
__license__ = "Apache v2"
__copyright__ = "Copyright (c) 2018 Refraction Point, Inc"

# Global API Credentials
import os
import yaml

# Global credentials are acquired in the following order:
# 1- LC_OID and LC_API_KEY environment variables.
# 2- LC_CREDS_FILE environment variable points to a YAML file with "oid: <OID>" and "api_key: <KEY>".
# 3- Assumes a creds file (like #2) is present at "~/.limacharlie".
GLOBAL_OID = os.environ.get( 'LC_OID', None )
GLOBAL_UID = os.environ.get( 'LC_UID', None )
GLOBAL_API_KEY = os.environ.get( 'LC_API_KEY', None )
if GLOBAL_API_KEY is None:
    _credsFile = os.environ.get( 'LC_CREDS_FILE', None )
    if _credsFile is None:
        _credsFile = os.path.expanduser( '~/.limacharlie' )
    if os.path.isfile( _credsFile ):
        with open( _credsFile, 'rb' ) as f:
            _credsFile = yaml.load( f.read() )
            _lcEnv = os.environ.get( 'LC_CURRENT_ENV', 'default' )
            if _lcEnv == '':
                _lcEnv = 'default'
            if _lcEnv == 'default':
                GLOBAL_OID = _credsFile.get( 'oid', None )
                GLOBAL_API_KEY = _credsFile.get( 'api_key', None )
                GLOBAL_UID = _credsFile.get( 'uid', None )
            else:
                if _credsFile.get( 'env', {} ).get( _lcEnv, None ) is None:
                    raise Exception( "LimaCharlie environment specified in LC_CURRENT_ENV could not be found in local config file: ~/.limacharlie" )
                GLOBAL_OID = _credsFile[ 'env' ][ _lcEnv ][ 'oid' ]
                GLOBAL_UID = _credsFile[ 'env' ][ _lcEnv ][ 'uid' ]
                GLOBAL_API_KEY = _credsFile[ 'env' ][ _lcEnv ][ 'api_key' ]

from .Manager import Manager
from .Firehose import Firehose
from .Spout import Spout
from .Hunter import Hunter
from .Webhook import Webhook
from .Sync import Sync
from .SpotCheck import SpotCheck
from .utils import LcApiException