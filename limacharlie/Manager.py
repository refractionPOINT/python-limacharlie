
# Detect if this is Python 2 or 3
import sys
import os
import shlex
import ssl
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

if _IS_PYTHON_2:
    from urllib2 import HTTPError
    from urllib2 import Request as URLRequest
    from urllib2 import urlopen
    from urllib import urlencode
    from urllib import quote as urlescape
else:
    from urllib.error import HTTPError
    from urllib.request import Request as URLRequest
    from urllib.request import urlopen
    from urllib.parse import urlencode
    from urllib.parse import quote as urlescape

from typing import Any

import uuid
import traceback
import cmd
import zlib
import base64
import time
import json
from datetime import datetime, timezone
from functools import wraps

from .Sensor import Sensor
from .Spout import Spout
from .utils import LcApiException
from .utils import GET
from .utils import POST
from .utils import DELETE
from .request_utils import getCurlCommandString

from .Jobs import Job
from . import __version__

from limacharlie import GLOBAL_OID
from limacharlie import GLOBAL_UID
from limacharlie import GLOBAL_API_KEY
from limacharlie import GLOBAL_OAUTH
from limacharlie import _getEnvironmentCreds

from typing import Any, Optional, Callable

ROOT_URL = 'https://api.limacharlie.io'
API_VERSION = 'v1'

API_TO_JWT_URL = 'https://jwt.limacharlie.io'

HTTP_UNAUTHORIZED = 401
HTTP_TOO_MANY_REQUESTS = 429
HTTP_GATEWAY_TIMEOUT = 504
HTTP_OK = 200

# Default function to call with debug messages.
DEFAULT_PRINT_DEBUG_FN: Optional[Callable[[str], None]] = None

def set_default_print_debug_fn( fn: Optional[Callable[[str], None]] = None ):
    """
    Set a default function to call with debug messages.

    Args:
        fn (function): the function to call with debug messages.
    """
    global DEFAULT_PRINT_DEBUG_FN
    DEFAULT_PRINT_DEBUG_FN = fn


def _create_ssl_context():
    """
    Create an SSL context with SSL_OP_IGNORE_UNEXPECTED_EOF flag set.

    This flag is needed for compatibility with servers that don't send proper
    close_notify alerts during SSL shutdown. OpenSSL 3.0+ treats this as a
    protocol violation by default, but setting this flag restores the more
    lenient behavior from OpenSSL 1.1.1.

    Returns:
        ssl.SSLContext: An SSL context configured for urllib, or None for Python 2
    """
    if _IS_PYTHON_2:
        # Python 2 doesn't support custom SSL contexts with urlopen
        return None

    try:
        # Create default SSL context
        ctx = ssl.create_default_context()

        # Set SSL_OP_IGNORE_UNEXPECTED_EOF if available (Python 3.10+, OpenSSL 3.0+)
        # This flag tells OpenSSL to treat unexpected EOFs as graceful shutdowns
        # instead of protocol violations
        if hasattr(ssl, 'OP_IGNORE_UNEXPECTED_EOF'):
            ctx.options |= ssl.OP_IGNORE_UNEXPECTED_EOF

        return ctx
    except Exception:
        # If SSL context creation fails, fall back to secure defaults
        # Never return None as older Python versions may use insecure defaults
        try:
            return ssl.create_default_context()
        except Exception:
            return None


class Manager( object ):
    '''General interface to a limacharlie.io Organization.'''

    def __init__( self, oid: Optional[str] = None, secret_api_key: Optional[str] = None, environment: Optional[str] = None, inv_id: Optional[str] = None, print_debug_fn: Optional[Callable[[str], None]] = None, is_interactive: bool = False, extra_params: dict[str, Any] = {}, jwt: Optional[str] = None, uid: Optional[str] = None, onRefreshAuth: Optional[Callable[[], None]] = None, isRetryQuotaErrors: bool = False, oauth_creds: Optional[dict] = None ):
        '''Create a session manager for interaction with limacharlie.io, much of the Python API relies on this object.

        Args:
            oid (str): a limacharlie.io organization ID, default environment if unset.
            secret_api_key (str): an API key for the organization, as provided by limacharlie.io, default environment if unset.
            environment (str): an environment name as defined in "limacharlie login" to use.
            inv_id (str): an investigation ID that will be used/propagated to other APIs using this Manager instance.
            print_debug_fn (function(message)): a callback function that will receive detailed debug messages.
            is_interactive (bool): if True, the manager will provide a root investigation and Spout so that tasks sent to Sensors can be tracked in realtime automatically; requires an inv_id to be set.
            extra_params (dict): optional key / values passed to interactive spout.
            jwt (str): optionally specify a single JWT to use for authentication.
            uid (str): a limacharlie.io user ID, if present authentication will be based on it instead of organization ID, set to False to override the current environment.
            onRefreshAuth (func): if provided, function is called whenever a JWT would be refreshed using the API key.
            isRetryQuotaErrors (bool): if True, the Manager will attempt to retry queries when it gets an out-of-quota error (HTTP 429).
            oauth_creds (dict): OAuth credentials dictionary with 'id_token', 'refresh_token', and 'provider' keys.
        '''
        print_debug_fn = print_debug_fn or DEFAULT_PRINT_DEBUG_FN

        # If an environment is specified, try to get its creds.
        if environment is not None:
            oid, uid, secret_api_key, oauth_creds = _getEnvironmentCreds( environment )
            if (secret_api_key is None and oauth_creds is None) or ( oid is None and uid is None ):
                raise LcApiException( 'LimaCharlie environment not configured, use "limacharlie login".')
        else:
            # Otherwise, try to take the values in parameter. But if
            # they are not present, use the GLOBAL values.
            if uid is None:
                if GLOBAL_UID is not None:
                    uid = GLOBAL_UID
            if oid is None:
                if GLOBAL_OID is None and uid is None:
                    raise LcApiException( 'LimaCharlie "default" environment not set, please use "limacharlie login".' )
                oid = GLOBAL_OID
            if secret_api_key is None and jwt is None and oauth_creds is None:
                if GLOBAL_API_KEY is None and GLOBAL_OAUTH is None:
                    raise LcApiException( 'LimaCharlie "default" environment not set, please use "limacharlie login".' )
                secret_api_key = GLOBAL_API_KEY
                if oauth_creds is None:
                    oauth_creds = GLOBAL_OAUTH

        try:
            if oid is not None and oid != '-':
                uuid.UUID( oid )
        except:
            raise LcApiException( 'Invalid oid, should be in UUID format.' )
        try:
            if secret_api_key is not None:
                uuid.UUID( secret_api_key )
        except:
            if jwt is None and oauth_creds is None:
                raise LcApiException( 'Invalid secret API key, should be in UUID format.' )
        self._oid: Optional[str] = oid
        self._uid: Optional[str] = uid if uid else None
        self._onRefreshAuth: Optional[Callable[[], None]] = onRefreshAuth
        self._secret_api_key: Optional[str] = secret_api_key
        self._oauth_creds: Optional[dict] = oauth_creds
        self._jwt: Optional[str] = jwt
        self._debug: Callable[[str], None] = print_debug_fn
        self._lastSensorListContinuationToken: Optional[str] = None
        self._inv_id: Optional[str] = inv_id
        self._spout: Optional[Spout] = None
        self._is_interactive: bool = is_interactive
        self._extra_params: dict[str, Any] = extra_params
        self._isRetryQuotaErrors: bool = isRetryQuotaErrors
        if self._is_interactive:
            if not self._inv_id:
                raise LcApiException( 'Investigation ID must be set for interactive mode to be enabled.' )
            self._refreshSpout()

    def _unwrap( self, data, isRaw = False ):
        if isRaw:
            return zlib.decompress( base64.b64decode( data ), 16 + zlib.MAX_WBITS )
        else:
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
            time_string = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
            self._debug( f"{time_string}: {msg}" )

    def _refreshJWT( self, expiry = None ):
        try:
            # Check if we're using OAuth
            if self._oauth_creds is not None:
                # Use simplified OAuth manager
                from .oauth_simple import SimpleOAuthManager
                oauth_manager = SimpleOAuthManager()
                
                # Ensure we have a valid token (handles refresh if needed)
                updated_creds = oauth_manager.ensure_valid_token(self._oauth_creds)
                
                if updated_creds is None:
                    raise LcApiException('Failed to refresh OAuth token')
                
                # Update our credentials if they were refreshed
                if updated_creds != self._oauth_creds:
                    self._oauth_creds = updated_creds
                    
                    # Update the credentials file with new tokens
                    from . import utils
                    # Determine environment from current config
                    environment = os.environ.get('LC_CURRENT_ENV', 'default')
                    utils.writeCredentialsToConfig(
                        environment,
                        self._oid,
                        None,  # No API key
                        uid=self._uid,
                        oauth_creds=self._oauth_creds
                    )
                
                # Exchange Firebase JWT for LimaCharlie JWT
                authData = { "fb_auth" : self._oauth_creds['id_token'] }
                if self._oid is not None:
                    authData[ 'oid' ] = self._oid
                if expiry is not None:
                    authData[ 'expiry' ] = int( expiry )
                
                request = URLRequest( API_TO_JWT_URL,
                                      urlencode( authData ).encode(),
                                      headers = { "Content-Type": "application/x-www-form-urlencoded" } )
                request.get_method = lambda: "POST"

                # Use custom SSL context to handle OpenSSL 3.0+ stricter EOF handling
                ssl_context = _create_ssl_context()
                if not _IS_PYTHON_2 and ssl_context is not None:
                    u = urlopen( request, context = ssl_context )
                else:
                    u = urlopen( request )
                self._jwt = json.loads( u.read().decode() )[ 'jwt' ]
                u.close()
                
                if self._onRefreshAuth is not None:
                    self._onRefreshAuth()
                return
            
            # Traditional API key flow
            if self._secret_api_key is None:
                raise Exception( 'No API key or OAuth credentials set' )
            authData = { "secret" : self._secret_api_key }
            if self._uid is not None:
                authData[ 'uid' ] = self._uid
            if self._oid is not None:
                authData[ 'oid' ] = self._oid
            if expiry is not None:
                authData[ 'expiry' ] = int( expiry )
            request = URLRequest( API_TO_JWT_URL,
                                  urlencode( authData ).encode(),
                                  headers = { "Content-Type": "application/x-www-form-urlencoded" } )
            request.get_method = lambda: "POST"

            # Use custom SSL context to handle OpenSSL 3.0+ stricter EOF handling
            ssl_context = _create_ssl_context()
            if not _IS_PYTHON_2 and ssl_context is not None:
                u = urlopen( request, context = ssl_context )
            else:
                u = urlopen( request )
            self._jwt = json.loads( u.read().decode() )[ 'jwt' ]
            u.close()
        except HTTPError as e:
            # Handle HTTP errors from JWT generation service
            code = e.code
            error_body = e.read().decode() if hasattr(e, 'read') else str(e)
            self._jwt = None

            # Check for MFA-related errors
            if 'multi-factor authentication' in error_body.lower() or 'mfa' in error_body.lower():
                error_msg = (
                    'Multi-factor authentication is required but was not performed.\n'
                    'Your account has 2FA enabled. Please re-authenticate using:\n'
                    '  limacharlie login --oauth\n'
                    'This will prompt you for your second factor during login.'
                )
                raise LcApiException(error_msg, code=code)

            raise LcApiException( 'Failed to get JWT: %s' % ( error_body, ), code=code)
        except Exception as e:
            # Handle other exceptions
            code = e.__dict__.get("code", None)
            self._jwt = None
            raise LcApiException( 'Failed to get JWT: %s' % ( e, ), code=code)

    def _restCall( self, url: str, verb: str, params: dict[str, Any] = {}, altRoot: Optional[str] = None, queryParams: Optional[dict[str, Any]] = None, rawBody: Optional[str] = None, contentType: Optional[str] = None, isNoAuth: bool = False, timeout: Optional[int] = None ) -> tuple[int, dict[str, Any]]:
        try:
            resp = None
            if not isNoAuth:
                headers = { "Authorization" : "bearer %s" % self._jwt }
            else:
                headers = {}

            if altRoot is None:
                url = '%s/%s/%s' % ( ROOT_URL, API_VERSION, url )
            else:
                if url:
                    url = '%s/%s' % ( altRoot, url )
                else:
                    url = altRoot

            if queryParams is not None:
                url = '%s?%s' % ( url, urlencode( queryParams ) )

            request = URLRequest( url,
                                  rawBody if rawBody is not None else urlencode( params, doseq = True ).encode(),
                                  headers = headers )
            request.get_method = lambda: verb
            request.add_header( 'User-Agent', 'lc-py-api/%s' % (__version__) )
            if contentType is not None:
                request.add_header( 'Content-Type', contentType )

            # Use custom SSL context to handle OpenSSL 3.0+ stricter EOF handling
            ssl_context = _create_ssl_context()
            if not _IS_PYTHON_2 and ssl_context is not None and url.startswith('https'):
                u = urlopen( request, timeout = timeout, context = ssl_context )
            else:
                u = urlopen( request, timeout = timeout )
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

            # Prior to enforcement of rate limits, we return the headers
            # in the response. Display the warning in stderr.
            headers = u.getheaders()
            quotaLimit = None
            quotaPeriod = None
            for header in headers:
                if header[0] == 'X-RateLimit-Quota':
                    quotaLimit = int(header[1])
                if header[0] == 'X-RateLimit-Period':
                    quotaPeriod = int(header[1])
            if quotaLimit is not None or quotaPeriod is not None:
                print(f"Warning: Rate limit hit, quota limit: {quotaLimit}, quota period: {quotaPeriod} seconds, see https://docs.limacharlie.io/v2/docs/en/api-keys?highlight=bulk", file=sys.stderr)

        except HTTPError as e:
            errorBody = e.read()
            try:
                ret = ( e.getcode(), json.loads( errorBody.decode() ) )
            except:
                ret = ( e.getcode(), errorBody )
        except ssl.SSLError as e:
            # Handle SSL errors (including SSLEOFError from OpenSSL 3.0+)
            # Treat as a transient error similar to gateway timeout so retry logic kicks in
            error_msg = f"SSL error occurred: {str(e)}"
            self._printDebug(error_msg)
            ret = ( HTTP_GATEWAY_TIMEOUT, { "error": error_msg } )

        if rawBody:
            body = rawBody.decode("utf-8")
        else:
            body = rawBody

        self._printDebug("Request information:")
        self._printDebug( "%s: %s ( params=%s,body=%s ) ==> %s ( %s )" % ( verb, url, body, str( params ), ret[ 0 ], str( ret[ 1 ] ) ) )
        self._printDebug("cURL command:")
        self._printDebug(getCurlCommandString(request=request))

        return ret

    # TODO: Fix mutable default (dict) in params
    def _apiCall( self, url: str, verb: str, params: dict[str, Any] = {}, altRoot: Optional[str] = None, queryParams: Optional[dict[str, Any]] = None, rawBody: Optional[str] = None, contentType: Optional[str] = None, isNoAuth: bool = False, nMaxTotalRetries: int = 3, timeout: int = 60 * 10 ) -> dict[str, Any]:
        hasAuthRefreshed = False
        nRetries = 0

        # If no JWT is ready, prime it.
        if not isNoAuth and self._jwt is None:
            if self._onRefreshAuth is not None:
                self._onRefreshAuth( self )
            else:
                self._refreshJWT()

        while nRetries < nMaxTotalRetries:
            nRetries += 1

            code, data = self._restCall( url, verb, params, altRoot = altRoot, queryParams = queryParams, rawBody = rawBody, contentType = contentType, isNoAuth = isNoAuth, timeout = timeout )

            if code == HTTP_UNAUTHORIZED:
                if hasAuthRefreshed:
                    # We already renewed the JWT once.
                    break
                elif not isNoAuth:
                    # Do our one JWT renew attempt.
                    hasAuthRefreshed = True
                    if self._onRefreshAuth is not None:
                        self._onRefreshAuth( self )
                    else:
                        if self._jwt is not None and self._secret_api_key is None:
                            # This is a case where we likely initialized the manager with a JWT,
                            # but no API key. In this case, we can't refresh the JWT, so we'll
                            # just fail.
                            raise LcApiException( 'Auth error and no API key available: oid=%s uid=%s: %s' % ( self._oid, self._uid, data, ), code=code)
                        self._refreshJWT()
                    continue
                else:
                    # Auth failed, can't renew.
                    break

            if code == HTTP_TOO_MANY_REQUESTS and self._isRetryQuotaErrors:
                # Out of quota, wait a bit and retry.
                time.sleep( 10 )
                continue

            if code == HTTP_GATEWAY_TIMEOUT:
                # The API gateway timed out talking to the
                # backend, we'll give it another shot.
                continue

            # Some other status code, including 200, so we're done.
            break

        if code != HTTP_OK:
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
        resp = self._apiCall( 'who', GET, {}, altRoot =  "%s/%s" % ( ROOT_URL, API_VERSION ) )
        return resp

    def userAccessibleOrgs( self, offset = None, limit = None, filter = None, sort_by = None, sort_order = None, with_names = True ):
        '''Query the API to see which organizations the user has access to.

        Args:
            offset (int): number of organizations to skip from the start.
            limit (int): maximum number of organizations to return (default 10).
            filter (str): case-insensitive substring filter on name, description, or oid.
            sort_by (str): field to sort by: 'name' or 'description' (default: 'name').
            sort_order (str): sort order: 'asc' or 'desc' (default: 'asc').
            with_names (bool): if True (default), include organization names in the response.

        Returns:
            A dict with 'orgs' key containing a list of OIDs and optional 'names' key with OID->name mapping.
        '''
        queryParams = {}
        if offset is not None:
            queryParams['offset'] = str(offset)
        if limit is not None:
            queryParams['limit'] = str(limit)
        if filter is not None:
            queryParams['filter'] = filter
        if sort_by is not None:
            queryParams['sort_by'] = sort_by
        if sort_order is not None:
            queryParams['sort_order'] = sort_order

        resp = self._apiCall( 'user/orgs', GET, queryParams = queryParams )

        # Transform response to match old format
        orgs_list = resp.get('orgs', [])

        # Extract OIDs as a list
        oids = [org.get('oid') for org in orgs_list if org.get('oid')]

        ret_data = {
            'orgs': oids
        }

        # Include names if requested
        if with_names:
            names = {org.get('oid'): org.get('name') for org in orgs_list if org.get('oid')}
            ret_data['names'] = names

        return ret_data

    def getOrgInfo( self ) -> dict[str, Any]:
        return self._apiCall( 'orgs/%s' % ( self._oid, ), GET, {} )

    def sensor( self, sid, inv_id = None, detailedInfo = None ):
        '''Get a Sensor object for the specific Sensor ID.

        The sensor may or may not be online.

        Args:
            sid (uuid str): the Sensor ID to represent.
            inv_id (str): investigation ID to add to all actions done using this object.

        Returns:
            a Sensor object.
        '''

        s = Sensor( self, sid, detailedInfo = detailedInfo )
        if inv_id is not None:
            s.setInvId( inv_id )
        elif self._inv_id is not None:
            s.setInvId( self._inv_id )
        return s

    def sensors( self, inv_id = None, selector = None, limit = None, with_ip = None, with_hostname_prefix = None ):
        '''Gets all Sensors in the Organization.

        The sensors may or may not be online.

        Args:
            inv_id (str): investigation ID to add to all actions done using these objects.
            selector (str): sensor selector expression to use as filter.
            limit (int): max number of sensors per page of result.
            with_ip (str): list sensors with the specific internal or external ip.
            with_hostname_prefix (str): list sensors with the specific hostname prefix.

        Returns:
            a generator of Sensor objects.
        '''

        continuationToken = None

        while True:
            params = {}

            if continuationToken is not None:
                params[ 'continuation_token' ] = continuationToken
            if selector is not None:
                params[ 'selector' ] = selector
            if limit is not None:
                params[ 'limit' ] = limit
            if with_ip is not None:
                params[ 'with_ip' ] = with_ip
            if with_hostname_prefix is not None:
                params[ 'with_hostname_prefix' ] = with_hostname_prefix

            resp = self._apiCall( 'sensors/%s' % self._oid, GET, queryParams = params )
            if inv_id is None:
                inv_id = self._inv_id

            for s in resp[ 'sensors' ]:
                yield self.sensor( s[ 'sid' ], inv_id, detailedInfo = s )

            continuationToken = resp.get( 'continuation_token', None )
            if continuationToken is None:
                break

    def sensorsWithTag( self, tag ):
        '''Get a list of sensors that have the matching tag.

        Args:
            tag (str): a tag to look for.

        Returns:
            a list of Sensor objects.
        '''

        resp = self._apiCall( 'tags/%s/%s' % ( self._oid, urlescape( tag, safe = '' ) ), GET, queryParams = {} )
        return [ Sensor( self, sid ) for sid in resp.keys() ]

    def getAllTags( self ):
        '''Get a list of tags in use by sensors.

        Returns:
            a list of tags.
        '''

        return self._apiCall( 'tags/%s' % ( self._oid, ), GET, queryParams = {} )[ 'tags' ]

    def getAllOnlineSensors( self, onlySIDs = [] ):
        '''Get a list of all online sensors.

        Args:
            onlySIDs (list of str): optional list of SIDs to check.

        Returns:
            a list of SIDs.
        '''

        req = {}
        if onlySIDs:
            req[ 'sids' ] = onlySIDs

        return list( k for k, v in self._apiCall( 'online/%s' % ( self._oid, ), POST, req, queryParams = {} ).items() if v )

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

    def hosts( self, hostname_expr, as_dict = False ):
        '''Get the Sensor objects for hosts matching a hostname expression.

        Args:
            hostname_expr (str): hostname prefix to look for.


        Returns:
            a list of Sensor IDs matching the hostname expression.
        '''

        return self.getSensorsWithHostname( hostname_expr, as_dict = as_dict )

    def rules( self, namespace = None ):
        '''DEPRECATED, use Hive accessors instead. Get the list of all Detection & Response rules for the Organization.

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
        '''DEPRECATED, use Hive accessors instead. Remove a Rule from the Organization.

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

    def add_rule( self, name, detection, response, isReplace = False, namespace = None, isEnabled = True, ttl = None ):
        '''DEPRECATED, use Hive accessors instead. Add a Rule to the Organization.

        For detailed explanation and possible Rules parameters
        see the official documentation, naming is the same as for the
        REST interface.

        Args:
            name (str): name to give to the Rule.
            namespace (str): optional namespace to operator on, defaults to "general".
            isReplace (boolean): if True, replace existing Rule with the same name.
            detection (dict): dictionary representing the detection component of the Rule.
            response (list): list representing the response component of the Rule.
            isEnabled (boolean): if True (default), the rule is enabled.
            ttl (int): number of seconds before the rule should be auto-deleted.

        Returns:
            the REST API response (JSON).
        '''

        expireOn = None
        if ttl is not None:
            expireOn = str( int( time.time() ) + int( ttl ) )

        req = {
            'name' : name,
            'is_replace' : 'true' if isReplace else 'false',
            'detection' : json.dumps( detection ),
            'response' : json.dumps( response ),
            'is_enabled' : 'true' if isEnabled else 'false',
        }

        if expireOn is not None:
            req[ 'expire_on' ] = expireOn

        if namespace is not None:
            req[ 'namespace' ] = namespace

        return self._apiCall( 'rules/%s' % self._oid, POST, req )

    def fps( self ):
        '''DEPRECATED, use Hive accessors instead. Get the list of all False Positive rules for the Organization.

        Returns:
            a list of False Positive rules (JSON).
        '''

        req = {}

        resp = self._apiCall( 'fp/%s' % self._oid, GET, queryParams = req )
        return resp

    def del_fp( self, name ):
        '''DEPRECATED, use Hive accessors instead. Remove a False Positive rule from the Organization.

        Args:
            name (str): the name of the rule to remove.

        Returns:
            the REST API response (JSON).
        '''

        req = {
            'name' : name,
        }

        return self._apiCall( 'fp/%s' % self._oid, DELETE, req )

    def add_fp( self, name, rule, isReplace = False, ttl = None ):
        '''DEPRECATED, use Hive accessors instead. Add a False Positive rule to the Organization.

        For detailed explanation and possible rules parameters
        see the official documentation, naming is the same as for the
        REST interface.

        Args:
            name (str): name to give to the rule.
            isReplace (boolean): if True, replace existing rule with the same name.
            detection (dict): dictionary representing the False Positive rule content.
            ttl (int): number of seconds before the rule should be auto-deleted.

        Returns:
            the REST API response (JSON).
        '''

        expireOn = None
        if ttl is not None:
            expireOn = str( int( time.time() ) + int( ttl ) )

        req = {
            'name' : name,
            'is_replace' : 'true' if isReplace else 'false',
            'rule' : json.dumps( rule ),
        }

        if expireOn is not None:
            req[ 'expire_on' ] = expireOn

        return self._apiCall( 'fp/%s' % self._oid, POST, req )

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
            a generator of detects.
        '''
        cursor = '-'
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

        nReturned = 0
        while cursor:
            req[ 'cursor' ] = cursor
            data = self._apiCall( 'insight/%s/detections' % ( self._oid, ), GET, queryParams = req )
            cursor = data.get( 'next_cursor', None )
            for detect in self._unwrap( data[ 'detects' ] ):
                yield detect
                nReturned += 1
                if limit is not None and limit <= nReturned:
                    break
            if limit is not None and limit <= nReturned:
                break

    def getAuditLogs( self, start, end, limit = None, event_type = None, sid = None ):
        '''Get the audit logs for the organization.

        Args:
            start (int): start unix (seconds) timestamp to fetch detects from.
            end (int): end unix (seconds) timestamp to feth detects to.
            limit (int): maximum number of detects to return.
            event_type (str): only return this audit event.
            sid (str): only return audit logs relating to this sensor id.

        Returns:
            a generator of detects.
        '''
        cursor = '-'
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

        if event_type is not None:
            req[ 'event_type' ] = event_type

        if sid is not None:
            req[ 'sid' ] = sid

        nReturned = 0
        while cursor:
            req[ 'cursor' ] = cursor
            data = self._apiCall( 'insight/%s/audit' % ( self._oid, ), GET, queryParams = req )
            cursor = data.get( 'next_cursor', None )
            for detect in self._unwrap( data[ 'events' ] ):
                yield detect
                nReturned += 1
                if limit is not None and limit <= nReturned:
                    break
            if limit is not None and limit <= nReturned:
                break

    def getHistoricDetectionByID( self, detect_id ):
        '''Get the detection with a specific detect_id.

        Args:
            detect_id (str): the ID (detect_id) of the detection to fetch.

        Returns:
            a detection.
        '''
        return self._apiCall( 'insight/%s/detections/%s' % ( self._oid, detect_id, ), GET )

    def getObjectInformation( self, objType, objName, info, isCaseSensitive = True, isWithWildcards = False, limit = None, isPerObject = None ):
        '''Get information about an object (indicator) using Insight (retention) data.

        Args:
            objType (str): the object type to query for, one of: user, domain, ip, hash, file_path, file_name.
            objName (str): the name of the object to query for, like "cmd.exe".
            info (str): the type of information to query for, one of: summary, locations.
            isCaseSensitive (bool): False to ignore case in the object name.
            isWithWildcards (bool): True to enable use of "%" wildcards in the object name.
            limit (int): optional maximum number of sensors/logs to report, or None for LimaCharlie default.
            isPerObject (bool): if set, specifies if the results should be groupped per object when a wildcard is present.

        Returns:
            a dict with the requested information.
        '''
        infoTypes = ( 'summary', 'locations' )
        objTypes = ( 'user', 'domain', 'ip', 'file_hash', 'file_path', 'file_name', 'service_name', 'package_name' )

        if info not in infoTypes:
            raise Exception( 'invalid information type: %s, choose one of %s' % ( info, infoTypes ) )

        if objType not in objTypes:
            raise Exception( 'invalid object type: %s, choose one of %s' % ( objType, objTypes ) )

        perObject = isPerObject
        if perObject is None:
            perObject = 'true' if ( isWithWildcards and 'summary' == info ) else 'false'
        else:
            perObject = 'true' if perObject else 'false'

        req = {
            'name' : objName,
            'info' : info,
            'case_sensitive' : 'true' if isCaseSensitive else 'false',
            'with_wildcards' : 'true' if isWithWildcards else 'false',
            'per_object' : perObject,
        }

        if limit is not None:
            req[ 'limit' ] = str( limit )

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

    def getSensorsWithHostname( self, hostnamePrefix, as_dict = False ):
        '''Get the list of sensor IDs and hostnames that match the given prefix.

        Args:
            hostnamePrefix (str): a hostname prefix to search for.

        Returns:
            List of (sid, hostname).
        '''
        data = self._apiCall( 'hostnames/%s' % ( self._oid, ), GET, queryParams = {
            'hostname' : hostnamePrefix,
            'as_dict' : 'true' if as_dict else 'false',
        } )
        return data.get( 'sid', None )

    def getSensorsWithIp( self, ip, start, end ):
        '''Get the list of sensor IDs that used the given IP during the time range.

        Args:
            ip (str): the IP address used.
            start (int): beginning of the time range to look for.
            end (int): end of the time range to look for.

        Returns:
            List of sid.
        '''
        data = self._apiCall( 'ips/%s' % ( self._oid, ), GET, queryParams = {
            'ip' : str( ip ),
            'start' : int( start ),
            'end' : int( end ),
        } )
        return data.get( 'sid', None )

    def serviceRequest( self, serviceName, data, isAsynchronous = False, isImpersonate = False ):
        '''Issue a request to a Service.

        Args:
            serviceName (str): the name of the Service to task.
            data (dict): JSON data to send to the Service as a request.
            isAsynchronous (bool): if set to False, wait for data from the Service and return it.
            isImpersonate (bool): if set to True, request the Service impersonate the caller.
        Returns:
            Dict with general success, or data from Service if isSynchronous.
        '''
        req = {
            'request_data' : base64.b64encode( json.dumps( data ).encode() ),
            'is_async' : isAsynchronous,
        }
        if isImpersonate:
            # To make sure we have as fresh a JWT as possible,
            # always do a refresh.
            self._refreshJWT()
            req[ 'jwt' ] = self._jwt
        data = self._apiCall( 'service/%s/%s' % ( self._oid, serviceName ), POST, req )
        return data

    def replicantRequest( self, *args, **kwargs ):
        # Maintained for backwards compatibility post rename replicant => service.
        return self.serviceRequest( *args, **kwargs )

    def extensionRequest( self, extensionName: str, action: str, data: dict[str, Any], isImpersonate: bool = False ) -> dict[str, Any]:
        '''Issue a request to an Extension.

        Args:
            extensionName (str): the name of the Extension to task.
            data (dict): JSON data to send to the Extension as a request.
            isImpersonate (bool): if set to True, request the Service impersonate the caller.
        Returns:
            Dict with general success.
        '''
        from limacharlie.Extensions import Extension
        return Extension( self ).request( extensionName, action, data, isImpersonated = isImpersonate )

    def getAvailableServices( self ):
        '''Get the list of Services currently available.

        Returns:
            List of Service names.
        '''
        data = self._apiCall( 'service/%s' % ( self._oid, ), GET )
        return data.get( 'replicants', None )

    def getAvailableReplicants( self ):
        # Maintained for backwards compatibility post rename replicant => service.
        return self.getAvailableServices()

    def getOrgConfig( self, configName ):
        '''Get the value of a per-organization config.

        Args:
            configName (str): name of the config to get.
        Returns:
            String value of the configuration.
        '''
        data = self._apiCall( 'configs/%s/%s' % ( self._oid, configName ), GET )
        return data.get( 'value', None )

    def setOrgConfig( self, configName, value ):
        '''Set the value of a per-organization config.

        Args:
            configName (str): name of the config to get.
            value (str): value of the config to set.
        '''
        data = self._apiCall( 'configs/%s/%s' % ( self._oid, configName ), POST, {
            'value' : value,
        } )
        return data

    def getOrgURLs( self ):
        '''Get the URLs used by various resources in the organization.

        Returns:
            Dictionary of resource types to URLs.
        '''
        data = self._apiCall( 'orgs/%s/url' % ( self._oid, ), GET, isNoAuth = True )
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
        data = self._apiCall( 'insight/%s/ingestion_keys?name=%s' % ( self._oid, name ), DELETE, {} )
        return data

    def configureUSPKey( self, name, parse_hint = '', format_re = '' ):
        '''Set the USP configuration of an Ingestion key.

        Args:
            name (str): name of the Ingestion key to configure.

        Returns:
            Dictionary with the key name and value.
        '''
        data = self._apiCall( 'insight/%s/ingestion_keys/usp' % ( self._oid, ), POST, {
            'name' : name,
            'parse_hint' : parse_hint,
            'format_re' : format_re,
        } )
        return data

    def validateUSP( self, platform, hostname = None, mapping = None, mappings = None, indexing = None, text_input = None, json_input = None ):
        '''Validate a USP (Universal Sensor Parser) configuration.

        Args:
            platform (str): parser platform type (e.g., 'text', 'json', 'cef', 'gcp', 'aws').
            hostname (str): optional default hostname for sensors (defaults to 'validation-test').
            mapping (dict): optional single mapping descriptor (mutually exclusive with mappings).
            mappings (list): optional list of mapping descriptors (mutually exclusive with mapping).
            indexing (list): optional list of indexing rules.
            text_input (str): optional newline-separated text input (mutually exclusive with json_input).
            json_input (list): optional pre-parsed JSON input array (mutually exclusive with text_input).

        Returns:
            Dictionary with 'results' (list of parsed events) and 'errors' (list of error strings).
        '''
        req = {
            'platform' : platform,
        }
        if hostname is not None:
            req[ 'hostname' ] = hostname
        if mapping is not None:
            req[ 'mapping' ] = mapping
        if mappings is not None:
            req[ 'mappings' ] = mappings
        if indexing is not None:
            req[ 'indexing' ] = indexing
        if text_input is not None:
            req[ 'text_input' ] = text_input
        if json_input is not None:
            req[ 'json_input' ] = json_input
        data = self._apiCall( 'usp/validate/%s' % ( self._oid, ), POST, {}, rawBody = json.dumps( req ).encode(), contentType = 'application/json' )
        return data

    def setOrgQuota( self, quota ):
        '''Set a new sensor quota for the organization.

        Args:
            quota (int): the new quota value.
        '''
        data = self._apiCall( 'orgs/%s/quota' % ( self._oid, ), POST, {
            'quota' : int( quota ),
        } )
        return data

    def getSubscriptions( self ):
        '''Get the list of resources the organization is subscribed to.

        '''
        data = self._apiCall( 'orgs/%s/resources' % ( self._oid, ), GET, {} )
        return data.get( 'resources', None )

    def subscribeToResource( self, name ):
        '''Subscribe the organization to the specific resource.

        Args:
            name (str): name of the resource like lookup/test-res.
        '''
        resCat, resName = name.split( '/' )
        data = self._apiCall( 'orgs/%s/resources' % ( self._oid, ), POST, {
            'res_cat': resCat,
            'res_name' : resName,
        } )
        return data

    def unsubscribeFromResource( self, name ):
        '''Unsubscribe the organization from the specific resource.

        Args:
            name (str): name of the resource like lookup/test-res.
        '''
        resCat, resName = name.split( '/' )
        data = self._apiCall( 'orgs/%s/resources' % ( self._oid, ), DELETE, {
            'res_cat': resCat,
            'res_name' : resName,
        } )
        return data

    def getUsers( self ):
        '''Get the list of users in the organization.

        '''
        data = self._apiCall( 'orgs/%s/users' % ( self._oid, ), GET, {} )
        return data.get( 'users', None )

    def addUser( self, email ):
        '''Add a user to an organization.

        Args:
            email (str): email of the user to add.
        '''
        data = self._apiCall( 'orgs/%s/users' % ( self._oid, ), POST, {
            'email' : email,
        } )
        return data

    def removeUser( self, email ):
        '''Remove user from an organization.

        Args:
            email (str): email of the user to remove.
        '''
        data = self._apiCall( 'orgs/%s/users' % ( self._oid, ), DELETE, {
            'email' : email,
        } )
        return data

    def getUserPermissions( self ):
        '''Get the list of users and their permissions.

        '''
        data = self._apiCall( 'orgs/%s/users/permissions' % ( self._oid, ), GET, {} )
        return data.get( 'user_permissions', None )

    def addUserPermission( self, email, permission ):
        '''Add a user to an organization.

        Args:
            email (str): email of the user to add.
            permission (str): permission to add to the user.
        '''
        data = self._apiCall( 'orgs/%s/users/permissions' % ( self._oid, ), POST, {
            'email' : email,
            'perm' : permission,
        } )
        return data

    def removeUserPermission( self, email, permission ):
        '''Remove user from an organization.

        Args:
            email (str): email of the user to remove.
            permission (str): permission to remove from the user.
        '''
        data = self._apiCall( 'orgs/%s/users/permissions' % ( self._oid, ), DELETE, {
            'email' : email,
            'perm' : permission,
        } )
        return data

    def getJobs( self, startTime, endTime, limit = None, sid = None ):
        '''Get all the jobs in an organization in a time window.

        Args:
            startTime (int): second epoch of the start of the time window.
            endTime (int): second epoch of the end of the time window.
            limit (int): optional maximum number of jobs to return.
            sid (str): optionally only return jobs that relate to this sensor ID.
        Returns:
            a Job object.
        '''
        params = {
            'start' : startTime,
            'end' : endTime,
            'is_compressed' : 'true',
            'with_data' : 'false',
        }
        if limit is not None:
            params[ 'limit' ] = limit
        if sid is not None:
            params[ 'sid' ] = sid
        data = self._apiCall( 'job/%s' % ( self._oid, ), GET, queryParams = params )
        data = self._unwrap( data[ 'jobs' ] )
        data = [ Job( self, job ) for jobId, job in data.items() ]
        return data

    def getJob( self, jobId ):
        '''Get a specific job.

        Args:
            jobId (str): job ID of the job to get.
        Returns:
            a Job object.
        '''
        job = Job( self, { 'job_id' : jobId } )
        job.update()
        return job

    def getApiKeys( self ):
        '''Get the list of API keys in the organization.

        '''
        data = self._apiCall( 'orgs/%s/keys' % ( self._oid, ), GET, {} )
        return data.get( 'api_keys', None )

    def addApiKey( self, keyName: str, permissions: list[str] = [], allowed_ip_range: Optional[str] = None ) -> dict[str, Any]:
        '''Add an API key to an organization.

        Args:
            keyName (str): name of the key to add.
            permissions (str[]): list of permissions for the key.
        Returns:
            the secret value of the new API key.
        '''
        req = {
            'key_name' : keyName,
            'perms' : ",".join( permissions ),
        }
        if allowed_ip_range:
            req['allowed_ip_range'] = allowed_ip_range
        data = self._apiCall( 'orgs/%s/keys' % ( self._oid, ), POST, req )
        return data

    def removeApiKey( self, keyHash: str ):
        '''Remove an API key from an organization.

        Args:
            keyHash (str): key hash of the key to remove.
        '''
        data = self._apiCall( 'orgs/%s/keys' % ( self._oid, ), DELETE, {
            'key_hash' : keyHash,
        } )
        return data

    def exportSensorList( self ):
        '''Perform a bulk export of the entire sensor list.

        Returns:
            a dictionary of sensors with their information and tags.
        '''
        data = self._apiCall( 'export/%s/sensors' % ( self._oid, ), POST, {} )
        return data

    def createNewOrg( self, name, location, template = None ):
        '''Request the creation of a new organization.

        Args:
            name (str): organization name.
            location (str): location where the organization is created.
            template (str): optional yaml template to initialize the new organization with.
        Returns:
            dict of info on new organization.
        '''
        req = {
            'name' : name,
            'loc' : location,
        }
        if template is not None:
            req[ 'template' ] = template
        data = self._apiCall( 'orgs/new', POST, req )
        return data

    def deleteOrg( self, oid, withConfirmation = None ):
        '''Request the deletion of an organization.

        Deleting an organization means the total and unrecoverable deletion of ALL data associated.

        This API is used in 2 steps:
        - Call this API without any "withConfirmation" value specified to get a confirmation token.
        - Using the confirmation token returned, call the same API with the token. Tokens are valid for 1 minute.

        Args:
            oid (str): the organization id to delete.
            withConfirmation (str): optional confirmation value returned by the call to the API without it.
        Returns:
            dict of info on new organization.
        '''
        if withConfirmation is None:
            return self._apiCall( 'orgs/%s/delete' % ( oid, ), GET, {} )
        return self._apiCall( 'orgs/%s/delete' % ( oid, ), DELETE, {
            'confirmation' : withConfirmation,
        } )

    def getGroups( self ):
        '''Get all groups this User has access to as an owner.

        '''
        data = self._apiCall( 'groups', GET, {} )
        return data.get( 'groups', None )

    def createGroup( self, name ):
        '''Create a new group.

        Args:
            name (str): group name.
        '''
        return self._apiCall( 'groups', POST, {
            'name': name,
        } )

    def getGroup( self, groupId ):
        '''Get the details about a specific group.

        Args:
            groupId (str): group id.
        Returns:
            dict of group details
        '''
        data = self._apiCall( 'groups/%s' % ( groupId, ), GET, {} )
        return data.get( 'group', None )

    def deleteGroup( self, groupId ):
        '''Delete a specific group.

        Args:
            groupId (str): group id.
        '''
        return self._apiCall( 'groups/%s' % ( groupId, ), DELETE, {} )

    def addGroupOwner( self, groupId, ownerEmail ):
        '''Add a new owner to a group.

        Args:
            groupId (str): group id.
            ownerEmail (str): email to add.
        '''
        return self._apiCall( 'groups/%s/owners' % ( groupId, ), POST, {
            'member_email' : ownerEmail,
        } )

    def removeGroupOwner( self, groupId, ownerEmail ):
        '''Remove an owner from the group.

        Args:
            groupId (str): group id.
            ownerEmail (str): email to remove.
        '''
        return self._apiCall( 'groups/%s/owners' % ( groupId, ), DELETE, {
            'member_email' : ownerEmail,
        } )

    def addGroupMember( self, groupId, memberEmail ):
        '''Add a User as a member of a group.

        Args:
            groupId (str): group id.
            memberEmail (str): email to add.
        '''
        return self._apiCall( 'groups/%s/users' % ( groupId, ), POST, {
            'member_email' : memberEmail,
        } )

    def removeGroupMember( self, groupId, memberEmail ):
        '''Remove a User from a group.

        Args:
            groupId (str): group id.
            memberEmail (str): email to remove.
        '''
        return self._apiCall( 'groups/%s/users' % ( groupId, ), DELETE, {
            'member_email' : memberEmail,
        } )

    def setGroupPermissions( self, groupId, permissions = [] ):
        '''Set the permissions for Users in the group.

        Args:
            groupId (str): group id.
            permissions (list of str): list of permissions.
        '''
        return self._apiCall( 'groups/%s/permissions' % ( groupId, ), POST, {
            'perm' : permissions,
        } )

    def getGroupLogs( self, groupId ):
        '''Get the audit logs for a group.

        Args:
            groupId (str): group id.
        Returns:
            list of audit entries
        '''
        data = self._apiCall( 'groups/%s/logs' % ( groupId, ), GET, {} )
        return data.get( 'logs', None )

    def addGroupOrg( self, groupId, oid ):
        '''Add an Org to a group.

        Args:
            groupId (str): group id.
            oid (str): organization id to add.
        '''
        return self._apiCall( 'groups/%s/orgs' % ( groupId, ), POST, {
            'oid' : oid,
        } )

    def removeGroupOrg( self, groupId, oid ):
        '''Remove an Org from a group.

        Args:
            groupId (str): group id.
            oid (str): organization id to remove.
        '''
        return self._apiCall( 'groups/%s/orgs' % ( groupId, ), DELETE, {
            'oid' : oid,
        } )

    def getSchemas( self, platform = None ):
        '''Get the list of all Schemas available for the Organization.

        Args:
            platform (str): optional platform name to filter the event types by.

        Returns:
            a dict containing the list of available schemas.
        '''
        params = None
        if platform is not None:
            params = {
                'platform' : platform,
            }
        return self._apiCall( 'orgs/%s/schema' % self._oid, GET, queryParams = params )

    def getSchema( self, name ):
        '''Get a specific Schema Definition.

        Args:
            name (str): name of the schema to get (e.g. 'evt:DNS_REQUEST').

        Returns:
            a dict containing the schema definition.
        '''
        return self._apiCall( 'orgs/%s/schema/%s' % ( self._oid, urlescape( name, safe = '' ) ), GET )

    def resetSchemas( self ):
        '''Reset the Schema Definition for all Schemas in an Organization.
        '''

        req = {}

        resp = self._apiCall( 'orgs/%s/schema' % self._oid, DELETE, queryParams = req )
        return resp

    def setSensorVersion( self, isFallbackVersion = False, isSleepVersion = False, specificVersion = None ):
        '''Set the sensor version for an Organization.

        Args:
            isFallbackVersion (bool): use the "stable" version.
            isSleepVersion (bool): set sensors in dormant mode.
            specificVersion (str): set a specific sensor version.
        '''

        req = {
            'is_fallback' : 'true' if isFallbackVersion else 'false',
            'is_sleep' : 'true' if isSleepVersion else 'false',
        }
        if specificVersion is not None:
            req[ 'specific_version' ] = specificVersion

        resp = self._apiCall( 'modules/%s' % self._oid, POST, queryParams = req )
        return resp

    def get_installation_keys( self, ):
        '''Get all installation keys for the Organization.

        Returns:
            the REST API response (JSON).
        '''

        return self._apiCall( 'installationkeys/%s' % self._oid, GET )

    def get_installation_key( self, iid ):
        '''Get a single installation key by ID.

        Args:
            name (str): installation key id to get.

        Returns:
            the REST API response (JSON).
        '''

        return self._apiCall( 'installationkeys/%s/%s' % ( self._oid, iid ), GET )

    def create_installation_key( self, tags, desc, iid = None, quota = None, use_public_root_ca = False ):
        '''Create an installation key.

        Args:
            tags (list): list of tags.
            desc (str): description for the installation key.
            iid (str): optional IID to overwrite (update).
            quota (int): optional number of enrollments a key can perform.
            use_public_root_ca (bool): optionally make sensors enrolling with this key use non-pinned SSL certificate going to public Root CAs.

        Returns:
            the REST API response (JSON).
        '''

        req = {
            'tags' : tags,
            'desc' : desc,
            'use_public_root_ca' : 'true' if use_public_root_ca else 'false',
        }
        if iid is not None:
            req[ 'iid' ] = str( iid )
        if quota is not None:
            req[ 'quota' ] = str( quota )

        return self._apiCall( 'installationkeys/%s' % self._oid, POST, req )

    def delete_installation_key( self, iid ):
        '''Delete an installation key.

        Args:
            iid (str): installation key id.

        Returns:
            the REST API response (JSON).
        '''

        return self._apiCall( 'installationkeys/%s' % self._oid, DELETE, {
            'iid' : iid,
        } )

    def getUsageStats( self ):
        '''Get general usage stats for the org.

        Args:
            tags (list): list of tags.
            desc (str): description for the installation key.

        Returns:
            the REST API response (JSON).
        '''

        return self._apiCall( 'usage/%s' % self._oid, GET )

    def getOntology( self ):
        '''Get the LimaCharlie ontology.

        Returns:
            dict with various ontology components.
        '''

        return self._apiCall( 'ontology', GET )

    def getEDREventList( self ):
        '''Get a list of all possible LimaCharlie EDR events.

        Returns:
            dict with the various events and IDs.
        '''

        return self._apiCall( 'events', GET )

    def testTransform( self, transform, data ):
        '''Test a transform against a piece of data.

        Returns:
            The transformed data.
        '''

        resp = self._apiCall( 'test_transform', POST, {}, queryParams = {
            'transform' : json.dumps( transform ),
            'test_data' : json.dumps( data ),
        } )
        return resp

    def getRuntimeMetadata( self, entity_type = None, entity_name = None ):
        '''Get the runtime metadata for entities in an org.

        Returns:
            runtime metdata.
        '''
        data = {}
        if entity_type is not None:
            data[ 'entity_type' ] = entity_type
        if entity_name is not None:
            data[ 'entity_name' ] = entity_name

        return self._apiCall( 'runtime_mtd/%s' % ( self._oid, ), GET, queryParams = data )

    def renameOrg( self, newName ):
        '''Rename the existing org.

        Args:
            tags (str): the new org name.

        Returns:
            the REST API response (JSON).
        '''

        return self._apiCall( 'orgs/%s/name' % self._oid, POST, queryParams = {
            'name' : newName,
        } )

    def checkOrgNameAvailability( self, newName ):
        '''Check if an org name can be used for a new org.

        Args:
            tags (str): the org name.

        Returns:
            the REST API response (JSON).
        '''

        return self._apiCall( 'orgs/new', GET, queryParams = {
            'name' : newName,
        } )

    def getMITREReport( self ):
        '''Get the MITRE report

        '''
        data = self._apiCall( 'mitre/%s' % ( self._oid, ), GET, {} )
        return data

    def getOrgErrors( self ):
        '''Get the error log for the organization.

        Returns:
            a list of error objects with component, error, oid, and ts fields.
        '''
        data = self._apiCall( 'errors/%s' % ( self._oid, ), GET, {} )
        return data.get( 'errors', None )

    def dismissOrgError( self, component ):
        '''Dismiss a specific error for the organization.

        Args:
            component (str): component name of the error to dismiss.

        Returns:
            the REST API response (JSON).
        '''
        return self._apiCall( 'errors/%s/%s' % ( self._oid, urlescape( component, safe = '' ) ), DELETE, {} )

    def inviteUser( self, email ):
        '''
        Invite a user to LimaCharlie.

        Args:
            email (str): Email of the user to invite.
        '''
        data = self._apiCall( 'invite/user', POST, { "user_email": email } )
        return data


    def inviteUser( self, email ):
        '''Invite a user to limacharlie.io.

        Args:
            email (str): the email of the user to invite.
        '''
        return self._apiCall( 'invite/user', POST, {
            'user_email' : email,
        } )
    
    def get_cve_list( self, product, version, include_details = False ):
        '''Get the list of CVEs.

        Returns:
            the list of CVEs.
        '''
        return self._apiCall( 'cves/%s/%s' % ( urlescape( product, safe = '' ), urlescape( version, safe = '' ) ), GET, queryParams = {
            'include_details' : 'true' if include_details else 'false',
        }, altRoot = 'https://vulnerability-db-service-usa-1-532932106819.us-central1.run.app/' )

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
