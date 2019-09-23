import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

if _IS_PYTHON_2:
    from urllib2 import HTTPError
    from urllib2 import Request as URLRequest
    from urllib2 import urlopen
    from urllib import urlencode
else:
    from urllib.error import HTTPError
    from urllib.request import Request as URLRequest
    from urllib.request import urlopen
    from urllib.parse import urlencode

from .utils import GET
from .utils import POST
from .utils import DELETE
from .utils import LcApiException

class Payloads( object ):
    '''Helper object to manage executable Payloads for sensors.'''

    def __init__( self, manager ):
        '''Create a Payload object.

        Args:
            manager (limacharlie.Manager): manager providing authentication.
        '''

        self._manager = manager

    def list( self ):
        '''List all available payloads.
        '''
        data = self._manager._apiCall( 'payload/%s' % ( self._manager._oid, ), GET, {} )
        return data

    def get( self, name ):
        '''Get a specific payload content.

        Args:
            name (str): the name of the payload to get.
        '''
        data = self._manager._apiCall( 'payload/%s/%s' % ( self._manager._oid, name ), GET, {} )
        getUrl = data.get( 'get_url', None )
        if getUrl is None:
            return None

        request = URLRequest( getUrl )
        request.get_method = lambda: "GET"
        u = urlopen( request )

        return u.read()

    def create( self, name, payloadPath = None, payloadContent = None ):
        '''Create a new payload.

        Args:
            name (str): the name of the payload to create.
            payloadPath (str): path to the file containing the payload.
            payloadContent (bytes): content of the new payload.
        '''
        if payloadPath is None and payloadContent is None:
            raise LcApiException( 'no payload content or path specified' )
        data = self._manager._apiCall( 'payload/%s/%s' % ( self._manager._oid, name ), POST, {} )
        putUrl = data.get( 'put_url', None )
        if putUrl is None:
            return None

        if payloadContent is None:
            with open( payloadPath, 'rb' ) as f:
                payloadContent = f.read()

        request = URLRequest( str( putUrl ), headers = {
            'Content-Type' : 'application/octet-stream'
        } )
        request.get_method = lambda: "PUT"
        u = urlopen( request, data = payloadContent )

        return u.read()

    def delete( self, name ):
        '''Delete a payload.

        Args:
            name (str): the name of the payload to delete.
        '''
        data = self._manager._apiCall( 'payload/%s/%s' % ( self._manager._oid, name ), DELETE, {} )
        return data