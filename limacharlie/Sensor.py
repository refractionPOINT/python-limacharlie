import uuid

from .utils import *

import gevent

class Sensor( object ):
    '''Representation of a limacharlie.io Sensor.'''

    _PLATFORM_WINDOWS = 0x10000000
    _PLATFORM_LINUX = 0x20000000
    _PLATFORM_MACOS = 0x30000000
    _PLATFORM_IOS = 0x40000000
    _PLATFORM_ANDROID = 0x50000000

    _ARCHITECTURE_X86 = 0x00000001
    _ARCHITECTURE_X64 = 0x00000002

    def __init__( self, manager, sid ):
        try:
            uuid.UUID( sid )
        except:
            raise LcApiException( 'Invalid sid, should be in UUID format.' )
        self._manager = manager
        self.sid = str( sid )
        self._invId = None
        self.responses = None

    def setInvId( self, inv_id ):
        '''Set an investigation ID to be applied to all actions done using the object.
            
        Args:
            inv_id (str): investigation ID to propagate.
        '''

        self._invId = inv_id

    def task( self, tasks, inv_id = None ):
        '''Send a task (or list of tasks) to the Sensor.

        Args:
            tasks (str or list of str): tasks to send in the command line format described in official documentation.
            inv_id (str): investigation ID to propagate.

        Returns:
            the REST API response (JSON).
        '''

        if not isinstance( tasks, ( tuple, list ) ):
            tasks = [ tasks ]
        req = { 'tasks' : tasks }
        invId = None
        if inv_id is not None:
            invId = inv_id
        elif self._invId is not None:
            invId = self._invId
        if invId is not None:
            req[ 'investigation_id' ] = invId
        return self._manager._apiCall( '%s' % self.sid, POST, req )

    def request( self, tasks ):
        '''Send a task (or list of tasks) to the Sensor and returns a FutureResults where the results will be sent; requires Manager is_interactive.

        Args:
            tasks (str or list of str): tasks to send in the command line format described in official documentation.

        Returns:
            a FutureResults object.
        '''
        if not self._manager._is_interactive:
            raise LcApiException( 'Manager provided was not created with is_interactive set to True, cannot track responses.' )
        thisTrackingId = '%s/%s' % ( self._manager._inv_id, str( uuid.uuid4() ) )
        future = FutureResults()

        self._manager._spout.registerFutureResults( thisTrackingId, future )

        self.task( tasks, inv_id = thisTrackingId )

        return future
    
    def simpleRequest( self, tasks, timeout = 30,  ):
        '''Make a request to the sensor assuming a single response.
        
        Args:
            tasks (str or list of str): tasks to send in the command line format described in official documentation.
        
        Returns:
            a single event, or None if not received.
        '''
        future = self.request( tasks )
        
        # Although getting the command result may take a while, the receipt from the sensor
        # should come back quickly so we will implement a static wait for that.
        nWait = 0
        while True:
            nWait += 1
            gevent.sleep( 1 )
            if future.wasReceived:
                break
            if nWait > 30:
                return None
        
        # We know the sensor got the tasking, now we will wait according to variable timeout.
        responses = future.getNewResponses( timeout = timeout )
        if responses:
            return responses[ 0 ]
        return None

    def tag( self, tag, ttl ):
        '''Apply a Tag to the Sensor.

        Args:
            tag (str): Tag to apply.
            ttl (int): number of seconds the Tag should remain applied.

        Returns:
            the REST API response (JSON).
        '''

        req = { 'tags' : str( tag ), 'ttl' : int( ttl ) }
        return self._manager._apiCall( '%s/tags' % self.sid, POST, req )

    def untag( self, tag ):
        '''Remove a Tag from the Sensor.

        Args:
            tag (str): Tag to remove.

        Returns:
            the REST API response (JSON).
        '''

        req = { 'tag' : str( tag ) }
        return self._manager._apiCall( '%s/tags' % self.sid, DELETE, req )

    def getTags( self ):
        '''Get Tags applied to the Sensor.

        Returns:
            the list of Tags currently applied.
        '''

        data = self._manager._apiCall( '%s/tags' % self.sid, GET )
        return data[ 'tags' ][ self.sid ].keys()

    def getInfo( self ):
        '''Get basic information on the Sensor.

        Returns:
            high level information on the Sensor.
        '''
        data = self._manager._apiCall( '%s' % self.sid, GET )

        # We massage the info a bit to make it easier to understand.
        platToString = {
            self._PLATFORM_WINDOWS : 'windows',
            self._PLATFORM_LINUX : 'linux',
            self._PLATFORM_MACOS : 'macos',
            self._PLATFORM_IOS : 'ios',
            self._PLATFORM_ANDROID : 'android',
        }
        archToString = {
            self._ARCHITECTURE_X86 : 'x86',
            self._ARCHITECTURE_X64 : 'x64',
        }
        data = data[ 'info' ]
        data[ 'plat' ] = platToString[ data[ 'plat' ] ]
        data[ 'arch' ] = archToString[ data[ 'arch' ] ]

        return data

    def isOnline( self ):
        '''Checks if the sensor is currently online.

        Returns:
            True if the sensor is connected to the cloud right now.
        '''
        data = self._manager._apiCall( '%s' % self.sid, GET )

        data = data[ 'online' ]
        return ( len( data ) > 0 ) and ( 'error' not in data )
    
    def __str__( self ):
        return self.sid
    
    def __repr__( self ):
        return self.sid