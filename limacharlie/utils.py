# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

import gevent.event
import gevent.lock

class LcApiException ( Exception ):
    pass

GET = 'GET'
POST = 'POST'
DELETE = 'DELETE'

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
    if 'event' in evt:
        evt[ 'event' ] = _enhancedDict( evt[ 'event' ] )
    if 'routing' in evt:
        evt[ 'routing' ] = _enhancedDict( evt[ 'routing' ] )
    return _enhancedDict( evt )

# Helper functions
class _enhancedDict( dict ):
    def getAll( self, *args, **kwargs ):
        return _xm_( self, *args, **kwargs )

    def getOne( self, *args, **kwargs ):
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
