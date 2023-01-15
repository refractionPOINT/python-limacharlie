from .Sensor import Sensor
from .utils import LcApiException
from .utils import _isStringCompat
import json
import yaml

from .utils import POST

class Extension( object ):
    def __init__( self, manager ):
        self._manager = manager

    def migrate( self, extName ):
        return self._manager._apiCall( 'extension/migrate/%s' % ( extName, ), POST, {
            'oid' : self._manager._oid,
        } )