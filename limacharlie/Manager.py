import urllib2
import urllib
import uuid
import json
import traceback
import cmd
import getpass
import sys
from functools import wraps

from .Sensor import Sensor
from .utils import *

ROOT_URL = 'https://api.limacharlie.io'
API_VERSION = 'v1'

API_TO_JWT_URL = 'https://app.limacharlie.io/jwt?oid=%s&secret=%s'

HTTP_UNAUTHORIZED = 401

class Manager( object ):
    '''General interface to a limacharlie.io Organization.'''

    def __init__( self, oid, secret_api_key, inv_id = None, print_debug_fn = None ):
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
        self._inv_id = inv_id

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
                                       urllib.urlencode( params, doseq = True ),
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
            errorBody = e.read()
            try:
                ret = ( e.getcode(), json.loads( errorBody ) )
            except:
                ret = ( e.getcode(), errorBody )

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

    def sensor( self, sid, inv_id = None ):
        '''Get a Sensor object for the specific Sensor ID.

        The sensor may or may not be online.

        Args:
            sid (uuid str): the Sensor ID to represent.
            inv_id (str): investigation ID to add to all actions done using this object.

        Returns:
            a Sensor object.
        '''

        s = Sensor( self, sid )
        if inv_id is not None:
            s.setInvId( inv_id )
        elif self._inv_id is not None:
            s.setInvId( self._inv_id )
        return s

    def sensors( self, inv_id = None ):
        '''Get the list of all Sensors in the Organization.

        The sensors may or may not be online.

        Args:
            inv_id (str): investigation ID to add to all actions done using these objects.

        Returns:
            a list of Sensor objects.
        '''

        sensors = []
        resp = self._apiCall( 'sensors/%s' % self._oid, GET )
        if inv_id is None:
            inv_id = self._inv_id
        for s in resp:
            sensors.append( self.sensor( s[ 'sid' ], inv_id ) )
        return sensors

    def outputs( self ):
        '''Get the list of all Outputs configured for the Organization.

        Returns:
            a list of Output descriptions (JSON).
        '''

        resp = self._apiCall( 'outputs/%s' % self._oid, GET )
        return resp[ self._oid ]

    def del_output( self, name ):
        '''Remove an Output from the Organization.

        Args:
            name (str): the name of the Output to remove.

        Returns:
            the REST API response (JSON).
        '''

        return self._apiCall( 'outputs/%s' % self._oid, DELETE, { 'name' : name } )

    def add_output( self, name, module, type, **kwargs ):
        '''Add an Output to the Organization.

        For detailed explanation and possible Output module parameters
        see the official documentation, naming is the same as for the
        REST interface.

        Args:
            name (str): name to give to the Output.
            module (str): name of the Output module to use.
            type (str): type of Output stream.
            **kwargs: arguments specific to the Output module, see official doc.

        Returns:
            a list of Output descriptions (JSON).
        '''

        req = { 'name' : name, 'module' : module, 'type' : type }
        for k, v  in kwargs.iteritems():
            req[ k ] = v
        return self._apiCall( 'outputs/%s' % self._oid, POST, req )

def _eprint( msg ):
    print >> sys.stderr, msg

def _report_errors( func ):
    @wraps( func )
    def silenceit( *args, **kwargs ):
        try:
            return func( *args,**kwargs )
        except:
            _eprint( traceback.format_exc() )
            return None
    return( silenceit )

class LCIOShell ( cmd.Cmd ):
    intro = 'Welcome to LimaCharlie.io shell.   Type help or ? to list commands.\n'
    prompt = '(limacharlie.io) '

    def __init__( self, oid, secretApiKey ):
        cmd.Cmd.__init__( self )
        self.sid = ''
        self.sensor = None
        self.inv_id = None
        self.updatePrompt()
        self.man = Manager( oid = oid, secret_api_key = secretApiKey )

    def updatePrompt( self ):
        self.prompt = '(limacharlie.io/%s/%s)> ' % ( self.sid, ( '' if self.inv_id is None else self.inv_id ) )

    def printOut( self, data ):
        print( json.dumps( data, indent = 4 ) )

    def do_quit( self, s ):
        '''Exit this CLI.'''
        return True

    def do_exit( self, s ):
        '''Exit this CLI.'''
        return True

    @_report_errors
    def do_sid( self, s ):
        '''Set the sensor context to this SID.'''
        if s == '':
            self.sid = ''
            self.sensor = None
        try:
            s = str( uuid.UUID( s ) )
        except:
            _eprint( 'Invalid SID format, should be a UUID.' )
            return
        self.sid = s
        self.sensor = self.man.sensor( self.sid )
        self.updatePrompt()

    def do_inv( self, s ):
        '''Set the current investigation id context.'''
        if s == '':
            self.inv_id = None
        else:
            self.inv_id = s
        self.updatePrompt()

    @_report_errors
    def do_task( self, s ):
        '''Send a task to the sensor set in current SID context.'''
        if self.sensor is None:
            _eprint( 'Missing sensor context, use command "sid".' )
            return
        self.printOut( self.sensor.task( s, self.inv_id ) )

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie.io cli' )
    parser.add_argument( 'oid',
                         type = lambda x: str( uuid.UUID( x ) ),
                         help = 'the OID to authenticate as.' )
    args = parser.parse_args()
    secretApiKey = getpass.getpass( prompt = 'Enter secret API key: ' )

    app = LCIOShell( args.oid, secretApiKey )
    app.cmdloop()
