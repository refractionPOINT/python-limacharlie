# Detect if this is Python 2 or 3
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import os
import yaml
import tempfile
import sys
import stat
import shutil
from time import time

_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

try:
    FileNotFoundError
except NameError:
    # Python 2 compatibility
    FileNotFoundError = IOError

import threading
import time

from .constants import CONFIG_FILE_PATH, EPHEMERAL_CREDS_ENV_VAR


class LcApiException ( Exception ):
    '''Exception type used for various errors in the LimaCharlie SDK.'''

    def __init__(self, message, code=None):
        """
        Initialize the exception with a message and an optional status code.

        Args:
            message (str): The error message.
            code (int, optional): An optional status code returnd by the API. Defaults to None.
        """
        super().__init__(message)
        self.code = code


GET = 'GET'
POST = 'POST'
DELETE = 'DELETE'
PUT = 'PUT'
HEAD = 'HEAD'
PATCH = 'PATCH'

class FutureResults( object ):
    '''Represents a Future promise of results from a task sent to a Sensor.'''

    def __init__( self ):
        self._nReceivedResults = 0
        self._newResultEvent = threading.Event()
        self._results = []
        self._lock = threading.Lock()
        self.wasReceived = False

    def _addNewResult( self, res ):
        with self._lock:
            if 'CLOUD_NOTIFICATION' == res[ 'routing' ][ 'event_type' ]:
                self.wasReceived = True
            else:
                res = _enhancedDict( res )
                res[ 'routing' ] = _enhancedDict( res[ 'routing' ] )
                res[ 'event' ] = _enhancedDict( res[ 'event' ] )
                self._results.append( res )
                self._nReceivedResults += 1
                self._newResultEvent.set()

    def getNewResponses( self, timeout = None ):
        '''Get new responses available, blocking for up to timeout seconds.

        Args:
            timeout (float): number of seconds to block for new results.

        Returns:
            a list of new results, or an empty list if timeout is reached.
        '''

        if self._newResultEvent.wait( timeout = timeout ):
            with self._lock:
                self._newResultEvent.clear()
                ret = self._results
                self._results = []
            return ret
        return []

def enhanceEvent( evt ):
    '''Wrap an event with an _enhancedDict providing utility functions getOne() and getAll().

    Args:
        evt (dict): event to wrap.

    Returns:
        wrapped event.
    '''

    if 'event' in evt:
        evt[ 'event' ] = _enhancedDict( evt[ 'event' ] )
    if 'routing' in evt:
        evt[ 'routing' ] = _enhancedDict( evt[ 'routing' ] )
    return _enhancedDict( evt )

# Helper functions
class _enhancedDict( dict ):
    '''Dictionary with helper functions getOne() and getAll() to get element at given path.'''

    def getAll( self, *args, **kwargs ):
        '''Get all elements in matching path.

        Args:
            path (str): path to get within the data.

        Returns:
            list of matching elements.
        '''

        return _xm_( self, *args, **kwargs )

    def getOne( self, *args, **kwargs ):
        '''Get one element in matching path.

        Args:
            path (str): path to get within the data.

        Returns:
            matching element or None if not found.
        '''

        return _x_( self, *args, **kwargs )

def _isDynamicType( e ):
    return isinstance( e, ( dict, list, tuple ) )

def _isListType( e ):
    return isinstance( e, ( list, tuple ) )

def _isSeqType( e ):
    return isinstance( e, dict )

def _xm_( o, path, isWildcardDepth = False ):
    result = []

    if _isStringCompat( path ):
        if '/' == path:
            # Special case where we want a NOOP path
            return [ o ]
        tokens = [ x for x in path.split( '/' ) if x != '' ]
    else:
        tokens = path

    if isinstance( o, dict ):
        isEndPoint = False
        if 0 != len( tokens ):
            if 1 == len( tokens ):
                isEndPoint = True

            curToken = tokens[ 0 ]

            if '*' == curToken:
                if 1 < len( tokens ):
                    result = _xm_( o, tokens[ 1 : ], True )
            elif '?' == curToken:
                if 1 < len( tokens ):
                    result = []
                    for elem in o.values():
                        if _isDynamicType( elem ):
                            result += _xm_( elem, tokens[ 1 : ], False )

            elif curToken in o:
                if isEndPoint:
                    result = [ o[ curToken ] ] if not _isListType( o[ curToken ] ) else o[ curToken ]
                elif _isDynamicType( o[ curToken ] ):
                    result = _xm_( o[ curToken ], tokens[ 1 : ] )

            if isWildcardDepth:
                tmpTokens = tokens[ : ]
                for elem in o.values():
                    if _isDynamicType( elem ):
                        result += _xm_( elem, tmpTokens, True )
    elif isinstance( o, ( list, tuple ) ):
        result = []
        for elem in o:
            if _isDynamicType( elem ):
                result += _xm_( elem, tokens, isWildcardDepth )

    return result

def _x_( o, path, isWildcardDepth = False ):
    r = _xm_( o, path, isWildcardDepth )
    if 0 != len( r ):
        r = r[ 0 ]
    else:
        r = None
    return r

def _isStringCompat( s ):
    if _IS_PYTHON_2:
        return isinstance( s, ( str, unicode ) ) # noqa: F821
    return isinstance( s, str )

def parallelExec( f, objects, timeout = None, maxConcurrent = None ):
    '''Execute a function on a list of objects in parallel.

    Args:
        f (callable): function to apply to each object.
        objects (iterable): list of objects to apply the function on.
        timeout (int): maximum number of seconds to wait for collection of calls.
        maxConcurrent (int): maximum number of function application to do concurrently.

    Returns:
        list of return values (or Exception if an exception occured).
    '''

    results = []
    with ThreadPoolExecutor( max_workers=maxConcurrent ) as executor:
        results = executor.map( lambda o: _retExecOrExc( f, o, timeout ), objects, timeout=timeout )
    return list( results )

def _retExecOrExc( f, o, timeout ):
    try:
        if timeout is None:
            return f( o )
        else:
            return f( o )
    except ( Exception, TimeoutError ) as e:
        return e

class Spinner:
    busy = False
    delay = 0.1

    @staticmethod
    def spinning_cursor():
        while 1:
            for cursor in '|/-\\': yield cursor

    def __init__(self, delay=None):
        self.spinner_generator = self.spinning_cursor()
        if delay and float(delay): self.delay = delay

    def spinner_task(self):
        while self.busy:
            sys.stdout.write(next(self.spinner_generator))
            sys.stdout.flush()
            time.sleep(self.delay)
            sys.stdout.write('\b')
            sys.stdout.flush()

    def __enter__(self):
        self.busy = True
        threading.Thread(target=self.spinner_task).start()

    def __exit__(self, exception, value, tb):
        self.busy = False
        time.sleep(self.delay)
        if exception is not None:
            return False
        
def loadCredentials():
    """
    Load credentials from config file.

    Returns:
        dict: Loaded credentials or None if file doesn't exist
    """
    # If ephemeral credentials mode is enabled, skip disk operations entirely
    if os.environ.get( EPHEMERAL_CREDS_ENV_VAR ):
        return None

    try:
        with open(CONFIG_FILE_PATH, 'rb') as f:
            return yaml.safe_load(f.read())
    except FileNotFoundError:
        return None

def writeCredentialsToConfig(alias, oid, secretApiKey, uid="", environment=None, oauth_creds=None):
    """
    Securely write credentials to a file on disk.

    Args:
        alias (str): Alias to store the credentials under (deprecated, use environment).
        oid (str): The organization ID.
        secretApiKey (str): The secret API key.
        uid (str): The user ID (optional, only for user scoped API keys).
        environment (str): Environment name (replaces alias).
        oauth_creds (dict): OAuth credentials (id_token, refresh_token, etc).
    """
    # If ephemeral credentials mode is enabled, skip disk operations entirely
    if os.environ.get( EPHEMERAL_CREDS_ENV_VAR ):
        print( "Ephemeral credentials mode enabled - credentials will not be persisted to disk" )
        return

    conf = {}

    print(CONFIG_FILE_PATH)

    try:
        with open( CONFIG_FILE_PATH, 'rb' ) as f:
            conf = yaml.safe_load( f.read() )
    except FileNotFoundError:
        pass

    # Handle scenario where a file is empty
    conf = conf or {}

    # Use environment if provided, otherwise fall back to alias
    env_name = environment if environment is not None else alias

    if env_name == "default" or env_name is None:
        # Update default credentials
        if oid is not None:
            conf[ 'oid' ] = oid
        if secretApiKey is not None:
            conf[ 'api_key' ] = secretApiKey
        if uid != '':
            conf[ 'uid' ] = uid
        elif uid == '' and 'uid' in conf:
            conf.pop( 'uid', None )
        if oauth_creds is not None:
            conf[ 'oauth' ] = oauth_creds
    else:
        # Update named environment
        conf.setdefault( 'env', {} )
        conf[ 'env' ].setdefault( env_name, {} )
        if oid is not None:
            conf[ 'env' ][ env_name ][ 'oid' ] = oid
        if secretApiKey is not None:
            conf[ 'env' ][ env_name ][ 'api_key' ] = secretApiKey
        if uid != '':
            conf[ 'env' ][ env_name ][ 'uid' ] = uid
        elif uid == '' and 'uid' in conf[ 'env' ][ env_name ]:
            conf[ 'env' ][ env_name ].pop( 'uid', None )
        if oauth_creds is not None:
            conf[ 'env' ][ env_name ][ 'oauth' ] = oauth_creds

    content = yaml.safe_dump( conf, default_flow_style = False ).encode()

    # For security reasons we first write it to a temporary file, chown + chmod it and
    # then move it to a final location. Without doing that, there is a potential race condition
    # with the file being written to and read from by another user (before we chmod it).
    fd, tmp_path = tempfile.mkstemp()

    # Set secure ownership and permissions on the temporary file.
    os.chown( tmp_path, os.getuid(), os.getgid() )
    os.chmod( tmp_path, stat.S_IWUSR | stat.S_IRUSR )  # 0o600

    try:
        try:
            os.write(fd, content)
        finally:
            os.close(fd)

        # Move is an atomic operation on unix.
        # TODO: Also check if destination is symlink and abort / prompt for confirmation before moving?
        shutil.move(tmp_path, CONFIG_FILE_PATH)
    finally:
        if os.path.isfile(tmp_path):
            os.unlink(tmp_path)

    print( "Credentials have been stored to: %s" % (CONFIG_FILE_PATH) )