from .Sensor import Sensor
from .utils import LcApiException
from .utils import _isStringCompat
import json
import yaml

from .utils import POST
from .utils import GET

class Extension( object ):
    def __init__( self, manager ):
        self._manager = manager

    def migrate( self, extName ):
        return self._manager._apiCall( 'extension/migrate/%s' % ( extName, ), POST, {
            'oid' : self._manager._oid,
        } )

    def request( self, extName, action, data = {} ):
        return self._manager._apiCall( 'extension/request/%s' % ( extName, ), POST, {
            'oid' : self._manager._oid,
            'action' : action,
            'data' : json.dumps( data ),
        } )

    def getSchema( self, extName ):
        return self._manager._apiCall( 'extension/schema/%s' % ( extName, ), GET, {} )