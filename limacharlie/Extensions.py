from .Sensor import Sensor
from .utils import LcApiException
from .utils import _isStringCompat
import json
import yaml

from .utils import POST
from .utils import DELETE
from .utils import GET
from .utils import PUT

class Extension( object ):
    def __init__( self, manager ):
        self._manager = manager

    def migrate( self, extName ):
        return self._manager._apiCall( 'extension/migrate/%s' % ( extName, ), POST, {
            'oid' : self._manager._oid,
        } )

    def request( self, extName, action, data = {}, isImpersonated = False ):
        req = {
            'oid' : self._manager._oid,
            'action' : action,
            'data' : json.dumps( data ),
        }
        if isImpersonated:
            if self._manager._jwt is None:
                self._manager._refreshJWT()
            req[ 'impersonator_jwt' ] = self._manager._jwt
        return self._manager._apiCall( 'extension/request/%s' % ( extName, ), POST, req )
    
    def list( self ):
        return self._manager._apiCall( 'orgs/%s/subscriptions' % ( self._manager._oid, ), GET )

    def subscribe( self, extName ):
        return self._manager._apiCall( 'orgs/%s/subscription/extension/%s' % ( self._manager._oid, extName, ), POST, {} )

    def unsubscribe( self, extName ):
        return self._manager._apiCall( 'orgs/%s/subscription/extension/%s' % ( self._manager._oid, extName, ), DELETE, {} )
    
    def getAll( self ):
        return self._manager._apiCall( 'extension/definition', GET, {} )

    def create( self, extObj ):
        return self._manager._apiCall( 'extension/definition', POST, rawBody = json.dumps( extObj ) )
    
    def update( self, extObj ):
        return self._manager._apiCall( 'extension/definition', PUT, rawBody = json.dumps( extObj ) )
    
    def get( self, extName ):
        return self._manager._apiCall( 'extension/definition/%s' % ( extName, ), GET )
    
    def delete( self, extName ):
        return self._manager._apiCall( 'extension/definition/%s' % ( extName, ), DELETE )
    
    def getSchema( self, extName ):
        return self._manager._apiCall( 'extension/schema/%s' % ( extName, ), GET )
