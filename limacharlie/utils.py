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