# Detect if this is Python 2 or 3
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

import uuid
import json
import traceback
import cmd
import zlib
import base64
from functools import wraps

from .Sensor import Sensor
from .Spout import Spout
from .utils import LcApiException
from .utils import GET
from .utils import POST
from .utils import DELETE

from limacharlie import GLOBAL_OID
from limacharlie import GLOBAL_UID
from limacharlie import GLOBAL_API_KEY

ROOT_URL = 'https://api.limacharlie.io'
API_VERSION = 'v1'

API_TO_JWT_URL = 'https://app.limacharlie.io/jwt'

HTTP_UNAUTHORIZED = 401

class Manager( object ):
    '''General interface to a limacharlie.io Organization.'''

    def __init__( self, oid, secret_api_key, inv_id = None, print_debug_fn = None, is_interactive = False, extra_params = {}, jwt = None, uid = None, onRefreshAuth = None ):
        '''Create a session manager for interaction with limacharlie.io, much of the Python API relies on this object.

        Args:
            oid (str): a limacharlie.io organization ID.
            secret_api_key (str): an API key for the organization, as provided by limacharlie.io.
            inv_id (str): an investigation ID that will be used/propagated to other APIs using this Manager instance.
            print_debug_fn (function(message)): a callback function that will receive detailed debug messages.
            is_interactive (bool): if True, the manager will provide a root investigation and Spout so that tasks sent to Sensors can be tracked in realtime automatically; requires an inv_id to be set.
            extra_params (dict): optional key / values passed to interactive spout.
            jwt (str): optionally specify a single JWT to use for authentication.
            uid (str): a limacharlie.io user ID, if present authentication will be based on it instead of organization ID.
            onRefreshAuth (func): if provided, function is called whenever a JWT would be refreshed using the API key.
        '''
        # If no creds were provided, use the global ones.
        if oid is None:
            if GLOBAL_OID is None:
                raise Exception( 'LimaCharlie "default" environment not set, please use "limacharlie login".' )
            oid = GLOBAL_OID
        if uid is None:
            if GLOBAL_UID is not None:
                uid = GLOBAL_UID
        if secret_api_key is None:
            if GLOBAL_API_KEY is None and jwt is None:
                raise Exception( 'LimaCharlie "default" environment not set, please use "limacharlie login".' )
            secret_api_key = GLOBAL_API_KEY

        try:
            uuid.UUID( oid )
        except:
            raise LcApiException( 'Invalid oid, should be in UUID format.' )
        try:
            uuid.UUID( secret_api_key )
        except:
            if jwt is None:
                raise LcApiException( 'Invalid secret API key, should be in UUID format.' )
        self._oid = oid
        self._uid = uid
        self._onRefreshAuth = onRefreshAuth
        self._secret_api_key = secret_api_key
        self._jwt = jwt
        self._debug = print_debug_fn
        self._lastSensorListContinuationToken = None
        self._inv_id = inv_id
        self._spout = None
        self._is_interactive = is_interactive
        self._extra_params = extra_params
        if self._is_interactive:
            if not self._inv_id:
                raise LcApiException( 'Investigation ID must be set for interactive mode to be enabled.' )
            self._refreshSpout()

    def _unwrap( self, data ):
        return json.loads( zlib.decompress( base64.b64decode( data ), 16 + zlib.MAX_WBITS ).decode() )

    def _refreshSpout( self ):
        if not self._is_interactive:
            return
        if self._spout is not None:
            self._spout.shutdown()
            self._spout = None
        self._spout = Spout( self, 'event', is_parse = True, inv_id = self._inv_id, extra_params = self._extra_params )

    def _printDebug( self, msg ):
        if self._debug is not None:
            self._debug( msg )

    def _refreshJWT( self ):
        try:
            if self._secret_api_key is None:
                raise Exception( 'No API key set' )
            authData = { "secret" : self._secret_api_key }
            if self._uid is not None:
                authData[ 'uid' ] = self._uid
            else:
                authData[ 'oid' ] = self._oid
            request = URLRequest( API_TO_JWT_URL,
                                  urlencode( authData ).encode() )
            request.get_method = lambda: "POST"
            u = urlopen( request )
            self._jwt = json.loads( u.read().decode() )[ 'jwt' ]
            u.close()
        except Exception as e:
            self._jwt = None
            raise LcApiException( 'Failed to get JWT from API key: %s' % e )

    def _restCall( self, url, verb, params, altRoot = None, queryParams = None, rawBody = None, contentType = None ):
        try:
            headers = { "Authorization" : "bearer %s" % self._jwt }

            if altRoot is None:
                url = '%s/%s/%s' % ( ROOT_URL, API_VERSION, url )
            else:
                url = '%s/%s' % ( altRoot, url )

            if queryParams is not None:
                url = '%s?%s' % ( url, urlencode( queryParams ) )

            request = URLRequest( url,
                                  rawBody if rawBody is not None else urlencode( params, doseq = True ).encode(),
                                  headers = headers )
            request.get_method = lambda: verb
            request.add_header( 'User-Agent', 'lc-py-api' )
            if contentType is not None:
                request.add_header( 'Content-Type', contentType )
            u = urlopen( request )
            try:
                data = u.read()
                if 0 != len( data ):
                    resp = json.loads( data.decode() )
                else:
                    resp = {}
            except ValueError as e:
                LcApiException( "Failed to decode data from API: %s" % e )
            u.close()
            ret = ( 200, resp )
        except HTTPError as e:
            errorBody = e.read()
            try:
                ret = ( e.getcode(), json.loads( errorBody.decode() ) )
            except:
                ret = ( e.getcode(), errorBody )

        self._printDebug( "%s: %s ( %s ) ==> %s ( %s )" % ( verb, url, str( params ), ret[ 0 ], str( ret[ 1 ] ) ) )

        return ret

    def _apiCall( self, url, verb, params = {}, altRoot = None, queryParams = None, rawBody = None, contentType = None ):
        if self._jwt is None:
            if self._onRefreshAuth is not None:
                self._onRefreshAuth( self )
            else:
                self._refreshJWT()

        code, data = self._restCall( url, verb, params, altRoot = altRoot, queryParams = queryParams, rawBody = rawBody, contentType = contentType )

        if code == HTTP_UNAUTHORIZED:
            if self._onRefreshAuth is not None:
                self._onRefreshAuth( self )
            else:
                self._refreshJWT()
            code, data = self._restCall( url, verb, params, altRoot = altRoot, queryParams = queryParams, rawBody = rawBody, contentType = contentType )

        if 200 != code:
            raise LcApiException( 'Api failure (%s): %s' % ( code, str( data ) ) )

        return data

    def shutdown( self ):
        '''Shut down any active mechanisms like interactivity.
        '''
        if self._spout is not None:
            self._spout.shutdown()
            self._spout = None

    def make_interactive( self ):
        '''Enables interactive mode on this instance if it was not created with is_interactive.
        '''
        if self._is_interactive:
            return

        if not self._inv_id:
            raise LcApiException( 'Investigation ID must be set for interactive mode to be enabled.' )

        self._is_interactive = True
        self._refreshSpout()

    def testAuth( self, permissions = [] ):
        '''Tests authentication with limacharlie.io.

        Args:
            permissions (list): optional list of permissions validate we have.

        Returns:
            a boolean indicating whether authentication succeeded.
        '''
        try:
            perms = None

            # First make sure we have an API key or JWT.
            if self._secret_api_key is not None:
                try:
                    if self._onRefreshAuth is not None:
                        self._onRefreshAuth( self )
                    else:
                        self._refreshJWT()
                except:
                    return False
            elif self._jwt is not None:
                try:
                    perms = self.whoAmI()
                except:
                    return False
            else:
                return False

            # If there are no permissions to check, we're good since
            # the previous part of this check made sure our auth was
            # at least valid.
            if permissions is None or 0 == len( permissions ):
                return True

            # We need to check the permissions we have.
            if perms is None:
                perms = self.whoAmI()
            if 'user_perms' in perms:
                # This is from a user token with permissions to multiple
                # organizations.
                effective = perms[ 'user_perms' ].get( self._oid, [] )
            else:
                # This is a machine token. Check the current OID is in there.
                if self._oid in perms.get( 'orgs', [] ):
                    effective = perms.get( 'perms', [] )
                else:
                    effective = []

            # Now just check if we have them all.
            for p in permissions:
                if p not in effective:
                    return False
            return True
        except:
            return False

    def whoAmI( self ):
        '''Query the API to see which organizations we are authenticated for.

        Returns:
            A list of organizations and permissions, or a dictionary of organizations with the related permissions.
        '''

        resp = self._apiCall( 'who', GET, {}, altRoot = ROOT_URL )
        return resp

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

    def sensors( self, inv_id = None, is_next = False ):
        '''Get the list of all Sensors in the Organization.

        The sensors may or may not be online.

        Args:
            inv_id (str): investigation ID to add to all actions done using these objects.
            is_next (bool): if set to True, will get the next slice of Sensors (if previous call to .sensors() hit the maximum number returned).

        Returns:
            a list of Sensor objects.
        '''

        if is_next and self._lastSensorListContinuationToken is None:
            return None

        params = {}
        if is_next:
            if self._lastSensorListContinuationToken is None:
                return []
            params[ 'continuation_token' ] = self._lastSensorListContinuationToken
            self._lastSensorListContinuationToken = None

        sensors = []
        resp = self._apiCall( 'sensors/%s' % self._oid, GET, queryParams = params )
        if inv_id is None:
            inv_id = self._inv_id
        for s in resp[ 'sensors' ]:
            sensors.append( self.sensor( s[ 'sid' ], inv_id ) )
        self._lastSensorListContinuationToken = resp.get( 'continuation_token', None )

        return sensors

    def outputs( self ):
        '''Get the list of all Outputs configured for the Organization.

        Returns:
            a list of Output descriptions (JSON).
        '''

        resp = self._apiCall( 'outputs/%s' % self._oid, GET )
        return resp.get( self._oid, {} )

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
            the REST API response (JSON).
        '''

        req = { 'name' : name, 'module' : module, 'type' : type }
        for k, v in kwargs.items():
            req[ k ] = v
        return self._apiCall( 'outputs/%s' % self._oid, POST, req )

    def hosts( self, hostname_expr ):
        '''Get the Sensor objects for hosts matching a hostname expression.

        Args:
            hostname_expr (str): hostname to look for, where '%' is a wildcard.

        Returns:
            a list of Sensor IDs matching the hostname expression.
        '''

        return self.getSensorsWithHostname( hostname_expr )

    def rules( self, namespace = None ):
        '''Get the list of all Detection & Response rules for the Organization.

        Args:
            namespace (str): optional namespace to operator on, defaults to "general".

        Returns:
            a list of D&R rules (JSON).
        '''

        req = {}
        if namespace is not None:
            req[ 'namespace' ] = namespace

        resp = self._apiCall( 'rules/%s' % self._oid, GET, queryParams = req )
        return resp

    def del_rule( self, name, namespace = None ):
        '''Remove a Rule from the Organization.

        Args:
            name (str): the name of the Rule to remove.
            namespace (str): optional namespace to operator on, defaults to "general".

        Returns:
            the REST API response (JSON).
        '''

        req = {
            'name' : name,
        }
        if namespace is not None:
            req[ 'namespace' ] = namespace

        return self._apiCall( 'rules/%s' % self._oid, DELETE, req )

    def add_rule( self, name, detection, response, isReplace = False, namespace = None ):
        '''Add a Rule to the Organization.

        For detailed explanation and possible Rules parameters
        see the official documentation, naming is the same as for the
        REST interface.

        Args:
            name (str): name to give to the Rule.
            namespace (str): optional namespace to operator on, defaults to "general".
            isReplace (boolean): if True, replace existing Rule with the same name.
            detection (dict): dictionary representing the detection component of the Rule.
            response (list): list representing the response component of the Rule.

        Returns:
            the REST API response (JSON).
        '''

        req = {
            'name' : name,
            'is_replace' : 'true' if isReplace else 'false',
            'detection' : json.dumps( detection ),
            'response' : json.dumps( response ),
        }

        if namespace is not None:
            req[ 'namespace' ] = namespace

        return self._apiCall( 'rules/%s' % self._oid, POST, req )

    def isInsightEnabled( self ):
        '''Check to see if Insight (retention) is enabled on this organization.

        Returns:
            True if Insight is enabled.
        '''
        data = self._apiCall( 'insight/%s' % ( self._oid, ), GET )
        if data.get( 'insight_bucket', None ):
            return True
        return False

    def getHistoricDetections( self, start, end, limit = None, cat = None ):
        '''Get the detections for this organization between the two times, requires Insight (retention) enabled.

        Args:
            start (int): start unix (seconds) timestamp to fetch detects from.
            end (int): end unix (seconds) timestamp to feth detects to.
            limit (int): maximum number of detects to return.
            cat (str): return dects only from this category.

        Returns:
            a list of detects.
        '''
        start = int( start )
        end = int( end )
        if limit is not None:
            limit = int( limit )

        req = {
            'start' : start,
            'end' : end,
            'is_compressed' : 'true',
        }

        if limit is not None:
            req[ 'limit' ] = limit

        if cat is not None:
            req[ 'cat' ] = cat

        data = self._apiCall( 'insight/%s/detections' % ( self._oid, ), GET, queryParams = req )
        return self._unwrap( data[ 'detects' ] )

    def getObjectInformation( self, objType, objName, info, isCaseSensitive = True, isWithWildcards = False ):
        '''Get information about an object (indicator) using Insight (retention) data.

        Args:
            objType (str): the object type to query for, one of: user, domain, ip, hash, file_path, file_name.
            objName (str): the name of the object to query for, like "cmd.exe".
            info (str): the type of information to query for, one of: summary, locations.
            isCaseSensitive (bool): False to ignore case in the object name.
            isWithWildcards (bool): True to enable use of "%" wildcards in the object name.

        Returns:
            a dict with the requested information.
        '''
        infoTypes = ( 'summary', 'locations' )
        objTypes = ( 'user', 'domain', 'ip', 'hash', 'file_path', 'file_name' )

        if info not in infoTypes:
            raise Exception( 'invalid information type: %s, choose one of %s' % ( info, infoTypes ) )

        if objType not in objTypes:
            raise Exception( 'invalid object type: %s, choose one of %s' % ( objType, objTypes ) )

        req = {
            'name' : objName,
            'info' : info,
            'case_sensitive' : 'true' if isCaseSensitive else 'false',
            'with_wildcards' : 'true' if isWithWildcards else 'false',
            'per_object' : 'true' if ( isWithWildcards and 'summary' == info ) else 'false',
        }

        data = self._apiCall( 'insight/%s/objects/%s' % ( self._oid, objType ), GET, queryParams = req )
        return data

    def getBatchObjectInformation( self, objects, isCaseSensitive = True ):
        '''Get object prevalence information in a batch.

        Args:
            objects (dict): dictionary of object type to list of object names to query for (objects["file_name"] = ["a.exe", "b.exe"]).
            isCaseSensitive (bool): False to ignore case in the object name.

        Returns:
            a dict with keys as time ranges and values are maps of object types to object name lists.
        '''
        for objType, objNames in objects.items():
            objects[ objType ] = list( objNames )
        req = {
            'objects' : json.dumps( objects ),
            'case_sensitive' : 'true' if isCaseSensitive else 'false',
        }
        data = self._apiCall( 'insight/%s/objects' % ( self._oid, ), POST, req )
        return data

    def getInsightHostCountPerPlatform( self ):
        '''Get the number of hosts for each platform for which we have long term Insight data.

        Returns:
            a dict with "mac", "linux" and "windows" and their count tuples [1,7,30].
        '''
        macBin = 'launchd'
        winBin = 'ntdll.dll'
        data = self.getBatchObjectInformation( {
            'file_name' : [
                macBin,
                winBin,
            ]
        } )

        if data is None:
            return data

        return {
            'mac' : ( data.get( 'last_1_days', {} ).get( 'file_name', {} ).get( macBin, 0 ), data.get( 'last_7_days', {} ).get( 'file_name', {} ).get( macBin, 0 ), data.get( 'last_30_days', {} ).get( 'file_name', {} ).get( macBin, 0 ) ),
            'windows' : ( data.get( 'last_1_days', {} ).get( 'file_name', {} ).get( winBin, 0 ), data.get( 'last_7_days', {} ).get( 'file_name', {} ).get( winBin, 0 ), data.get( 'last_30_days', {} ).get( 'file_name', {} ).get( winBin, 0 ) ),
            'linux' : ( None, None, None ),
        }

    def getSensorsWithHostname( self, hostnamePrefix ):
        '''Get the list of sensor IDs and hostnames that match the given prefix.

        Args:
            hostnamePrefix (str): a hostname prefix to search for.

        Returns:
            List of (sid, hostname).
        '''
        data = self._apiCall( 'hostnames/%s' % ( self._oid, ), GET, queryParams = {
            'hostname' : hostnamePrefix,
        } )
        return data.get( 'sid', None )

    def replicantRequest( self, replicantName, data, isSynchronous = False ):
        '''Issue a request to a Replicant.

        Args:
            replicantName (str): the name of the Replicant to task.
            data (dict): JSON data to send to the Replicant as a request.
            isSynchronous (bool): if set to True, wait for data from the Replicant and return it.
        Returns:
            Dict with general success, or data from Replicant if isSynchronous.
        '''
        data = self._apiCall( 'replicant/%s/%s' % ( self._oid, replicantName ), POST, {
            'request_data' : base64.b64encode( json.dumps( data ).encode() ),
            'is_async' : isSynchronous,
        } )
        return data

    def getAvailableReplicants( self ):
        '''Get the list of Replicants currently available.

        Returns:
            List of Replicant names.
        '''
        data = self._apiCall( 'replicant/%s' % ( self._oid, ), GET )
        return data.get( 'replicants', None )

    def getOrgConfig( self, configName ):
        '''Get the value of a per-organization config.

        Args:
            configName (str): name of the config to get.
        Returns:
            String value of the configuration.
        '''
        data = self._apiCall( 'configs/%s/%s' % ( self._oid, configName ), GET )
        return data.get( 'value', None )

    def getOrgURLs( self ):
        '''Get the URLs used by various resources in the organization.

        Returns:
            Dictionary of resource types to URLs.
        '''
        data = self._apiCall( 'orgs/%s/url' % ( self._oid, ), GET )
        return data.get( 'url', None )

    def getIngestionKeys( self ):
        '''Get the Ingestion keys associated to this organization.

        Returns:
            Dictionary of the Ingestion keys.
        '''
        data = self._apiCall( 'insight/%s/ingestion_keys' % ( self._oid, ), GET )
        return data.get( 'keys', None )

    def setIngestionKey( self, name ):
        '''Set (or reset) an Ingestion key.

        Args:
            name (str): name of the Ingestion key to set.
        Returns:
            Dictionary with the key name and value.
        '''
        data = self._apiCall( 'insight/%s/ingestion_keys' % ( self._oid, ), POST, {
            'name' : name,
        } )
        return data

    def delIngestionKey( self, name ):
        '''Delete an Ingestion key.

        Args:
            name (str): name of the Ingestion key to delete.
        '''
        data = self._apiCall( 'insight/%s/ingestion_keys' % ( self._oid, ), DELETE, {
            'name' : name,
        } )
        return data

def _eprint( msg ):
    sys.stderr.write( msg )
    sys.stderr.write( "\n" )

def _report_errors( func ):
    @wraps( func )
    def silenceit( *args, **kwargs ):
        try:
            return func( *args, **kwargs )
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
    import getpass

    parser = argparse.ArgumentParser( prog = 'limacharlie.io cli' )
    parser.add_argument( '-o', '--oid',
                         type = lambda x: str( uuid.UUID( x ) ),
                         required = False,
                         dest = 'oid',
                         help = 'the OID to authenticate as, if not specified global creds are used.' )
    args = parser.parse_args()
    if args.oid is not None:
        secretApiKey = getpass.getpass( prompt = 'Enter secret API key: ' )
    else:
        secretApiKey = None

    app = LCIOShell( args.oid, secretApiKey )
    app.cmdloop()
