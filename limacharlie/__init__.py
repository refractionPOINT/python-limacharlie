"""limacharlie API for limacharlie.io"""

__version__ = "3.13.0"
__author__ = "Maxime Lamothe-Brassard ( Refraction Point, Inc )"
__author_email__ = "maxime@refractionpoint.com"
__license__ = "Apache v2"
__copyright__ = "Copyright (c) 2020 Refraction Point, Inc"

# Global API Credentials
import os
import yaml

def _getEnvironmentCreds( name ):
    credsFile = os.environ.get( 'LC_CREDS_FILE', None )
    if credsFile is None:
        credsFile = os.path.expanduser( '~/.limacharlie' )
    if not os.path.isfile( credsFile ):
        return ( None, None, None )
    with open( credsFile, 'rb' ) as f:
        credsFile = yaml.safe_load( f.read() )

        if name == 'default':
            # Default creds are at the top of the creds file.
            oid = credsFile.get( 'oid', None )
            uid = credsFile.get( 'uid', None )
            key = credsFile.get( 'api_key', None )

            return ( oid, uid, key )

        if name not in credsFile.get( 'env', {} ):
            return ( None, None, None )

        envData = credsFile[ 'env' ][ name ]
        oid = envData.get( 'oid', None )
        uid = envData.get( 'uid', None )
        key = envData.get( 'api_key', None )

        return ( oid, uid, key )

# Global credentials are acquired in the following order:
# 1- LC_OID and LC_API_KEY environment variables.
# 2- LC_CREDS_FILE environment variable points to a YAML file with "oid: <OID>" and "api_key: <KEY>".
# 3- Assumes a creds file (like #2) is present at "~/.limacharlie".
GLOBAL_OID = os.environ.get( 'LC_OID', None )
GLOBAL_UID = os.environ.get( 'LC_UID', None )
GLOBAL_API_KEY = os.environ.get( 'LC_API_KEY', None )
if GLOBAL_API_KEY is None:
    _lcEnv = os.environ.get( 'LC_CURRENT_ENV', 'default' )
    if _lcEnv == '':
        _lcEnv = 'default'
    GLOBAL_OID, GLOBAL_UID, GLOBAL_API_KEY = _getEnvironmentCreds( _lcEnv )

if not os.environ.get( 'LC_NO_MONKEY_PATCHING', False ):
    try:
        from gevent import monkey
        monkey.patch_all()
    except monkey.MonkeyPatchWarning as e:
        import sys
        sys.stderr.write( "%s\n" % ( e, ) )
        sys.stderr.flush()

from .Manager import Manager
from .Firehose import Firehose
from .Spout import Spout
from .Webhook import Webhook
from .Sync import Sync
from .SpotCheck import SpotCheck
from .Payloads import Payloads
from .Logs import Logs
from .Logs import Logs as Artifacts
from .utils import LcApiException
from . import Replicants as services
