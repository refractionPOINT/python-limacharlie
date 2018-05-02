import urllib2
import urllib
import uuid
import json
import traceback

from .Sensor import Sensor
from .utils import *

ROOT_URL = 'https://api.limacharlie.io'
API_VERSION = 'v1'

API_TO_JWT_URL = 'https://app.limacharlie.io/jwt?oid=%s&secret=%s'

HTTP_UNAUTHORIZED = 401

class Manager( object ):
    def __init__( self, oid, secret_api_key, print_debug_fn = None ):
        try:
            uuid.UUID( oid )
        except:
            raise LcApiException( 'Invalid oid, should be in UUID format.' )
        try:
            uuid.UUID( secret_api_key )
        except:
            raise LcApiException( 'Invalid secret API key, should be in UUID format.' )
        self._oid = oid
        self._secret_api_key = secret_api_key
        self._jwt = None
        self._debug = print_debug_fn

    def _printDebug( self, msg ):
        if self._debug is not None:
            self._debug( msg )

    def _refreshJWT( self ):
        try:
            u = urllib2.urlopen( API_TO_JWT_URL % ( self._oid, self._secret_api_key ) )
            self._jwt = json.loads( u.read() )[ 'jwt' ]
            u.close()
        except Exception as e:
            self._jwt = None
            raise LcApiException( 'Failed to get JWT from API key: %s' % e )

    def _restCall( self, url, verb, params ):
        try:
            headers = { "Authorization" : "bearer %s" % self._jwt }
            
            url = '%s/%s/%s' % ( ROOT_URL, API_VERSION, url )
            
            request = urllib2.Request( url, 
                                       urllib.urlencode( params ),
                                       headers = headers )
            request.get_method = lambda: verb
            u = urllib2.urlopen( request )
            try:
                data = u.read()
                if 0 != len( data ):
                    resp = json.loads( data )
                else:
                    resp = {}
            except ValueError as e:
                LcApiException( "Failed to decode data from API: %s" % e )
            u.close()
            ret = ( 200, resp )
        except urllib2.HTTPError as e:
            self._printDebug( "%s\n\n%s" % ( traceback.format_exc(), e ) )
            ret = ( e.getcode(), None )

        self._printDebug( "%s: %s ( %s ) ==> %s ( %s )" % ( verb, url, str( params ), ret[ 0 ], str( ret[ 1 ] ) ) )

        return ret

    def _apiCall( self, url, verb, params = {} ):
        if self._jwt is None:
            self._refreshJWT()
        
        code, data = self._restCall( url, verb, params )

        if code == HTTP_UNAUTHORIZED:
            self._refreshJWT()
            return self._restCall( url, verb, params )

        if 200 != code:
            raise LcApiException( 'Api failure (%s): %s' % ( code, str( data ) ) )

        return data

    def sensor( self, sid ):
        return Sensor( self, sid )

    def sensors( self ):
        sensors = []
        resp = self._apiCall( 'sensors/%s' % self._oid, GET )
        for s in resp:
            sensors.append( self.sensor( s[ 'sid' ] ) )
        return sensors

    def outputs( self ):
        resp = self._apiCall( 'outputs/%s' % self._oid, GET )
        return resp[ self._oid ]

    def del_output( self, name ):
        return self._apiCall( 'outputs/%s' % self._oid, DELETE, { 'name' : name } )

    def add_output( self, name, module, type, **kwargs ):
        req = { 'name' : name, 'module' : module, 'type' : type }
        for k, v  in kwargs.iteritems():
            req[ k ] = v
        return self._apiCall( 'outputs/%s' % self._oid, POST, req )