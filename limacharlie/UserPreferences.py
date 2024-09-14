# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

import json

from .utils import GET
from .utils import DELETE
from .utils import POST

if _IS_PYTHON_2:
    from urllib import quote as urlescape
else:
    from urllib.parse import quote as urlescape


class UserPreferences( object ):
    '''Representation of user preferences in limacharlie.io.'''

    def __init__( self, manager ):
        self._manager = manager

    def getAll( self ):
        return self._manager._apiCall( 'preferences', GET, altRoot = 'https://user-preferences.limacharlie.io/' )

    def get( self, key ):
        return self._manager._apiCall( 'preferences/' + urlescape( key, safe = '' ), GET, altRoot = 'https://user-preferences.limacharlie.io/' )

    def set( self, key, value ):
        return self._manager._apiCall( 'preferences/' + urlescape( key, safe = '' ), POST, params = {'data': json.dumps(value)}, altRoot = 'https://user-preferences.limacharlie.io/' )

    def delete( self, key ):
        return self._manager._apiCall( 'preferences/' + urlescape( key, safe = '' ), DELETE, altRoot = 'https://user-preferences.limacharlie.io/' )