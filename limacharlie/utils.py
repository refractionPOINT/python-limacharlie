# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

import gevent.event
import gevent.lock

class LcApiException ( Exception ):
    '''Exception type used for various errors in the LimaCharlie SDK.'''

    pass

GET = 'GET'
POST = 'POST'
DELETE = 'DELETE'
PUT = 'PUT'

class FutureResults( object ):
    '''Represents a Future promise of results from a task sent to a Sensor.'''

    def __init__( self ):
        self._nReceivedResults = 0
        self._newResultEvent = gevent.event.Event()
        self._results = []
        self._lock = gevent.lock.Semaphore()
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
        return isinstance( s, ( str, unicode ) )
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

    g = gevent.pool.Pool( size = maxConcurrent )
    results = g.imap_unordered( lambda o: _retExecOrExc( f, o, timeout ), objects )
    return list( results )

def _retExecOrExc( f, o, timeout ):
    try:
        if timeout is None:
            return f( o )
        else:
            with gevent.Timeout( timeout ):
                return f( o )
    except ( Exception, gevent.Timeout ) as e:
        return e
