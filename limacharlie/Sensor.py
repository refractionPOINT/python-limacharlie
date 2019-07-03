import uuid
import json
import time

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
        self._platform = None
        self._architecture = None
        self._hostname = None

    def setInvId( self, inv_id ):
        '''Set an investigation ID to be applied to all actions done using the object.

        Args:
            inv_id (str): investigation ID to propagate.
        '''

        self._invId = inv_id

    def waitToComeOnline( self, timeout ):
        '''Wait for the sensor to be online.

        :param timeout: number of seconds to wait up to

        :return True if sensor is back or False if timeout
        '''
        deadline = time.time() + timeout

        while not self.isOnline():
            if time.time() >= deadline:
                return False
            gevent.sleep( min( 60, deadline - time.time() ) )

        return True

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
        if ( not self._manager._is_interactive ) or ( self._manager._spout is None ):
            raise LcApiException( 'Manager provided was not created with is_interactive set to True, cannot track responses.' )
        thisTrackingId = '%s/%s' % ( self._manager._inv_id, str( uuid.uuid4() ) )
        future = FutureResults()

        self._manager._spout.registerFutureResults( thisTrackingId, future )

        self.task( tasks, inv_id = thisTrackingId )

        return future

    def simpleRequest( self, tasks, timeout = 30, until_completion = False ):
        '''Make a request to the sensor assuming a single response.

        Args:
            tasks (str or list of str): tasks to send in the command line format described in official documentation.
            timeout (int): number of seconds to wait for responses.
            until_completion (bool or callback): if True, wait for completion receipts from the sensor, or callback for each response.

        Returns:
            a single event (if tasks was a single task), a list of events (if tasks was a list), or None if not received.
        '''
        future = self.request( tasks )

        nExpectedResponses = 1
        if isinstance( tasks, ( list, tuple ) ):
            nExpectedResponses = len( tasks )

        deadline = time.time() + timeout

        # Although getting the command result may take a while, the receipt from the sensor
        # should come back quickly so we will implement a static wait for that.
        while True:
            gevent.sleep( 1 )
            if future.wasReceived:
                break
            if time.time() > deadline:
                return None

        # We know the sensor got the tasking, now we will wait according to variable timeout.
        allResponses = []
        nDone = 0
        while True:
            responses = future.getNewResponses( timeout = deadline - time.time() )
            if not responses:
                break
            if not until_completion:
                if 1 == nExpectedResponses:
                    return responses[ 0 ]
                else:
                    allResponses += responses
                    if len( allResponses ) >= nExpectedResponses:
                        return allResponses
            else:
                for response in responses:
                    err = response[ 'event' ].get( 'ERROR_MESSAGE', None )
                    if err == 'done':
                        nDone += 1
                    else:
                        if callable( until_completion ):
                            response = until_completion( response )
                        allResponses.append( response )
                if nDone >= nExpectedResponses:
                    return allResponses
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

        self._platform = data[ 'plat' ]
        self._architecture = data[ 'arch' ]
        self._hostname = data.get( 'hostname', None )

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

    def isWindows( self ):
        '''Checks if the sensor is a Windows OS.

        Returns:
            True if the sensor is Windows.
        '''
        if self._platform is None:
            # If the platform has not been cached yet, retrieve the info.
            self.getInfo()
        return self._platform == self._PLATFORM_WINDOWS

    def isMac( self ):
        '''Checks if the sensor is a Mac OS.

        Returns:
            True if the sensor is Mac.
        '''
        if self._platform is None:
            # If the platform has not been cached yet, retrieve the info.
            self.getInfo()
        return self._platform == self._PLATFORM_MACOS

    def isLinux( self ):
        '''Checks if the sensor is a Linux OS.

        Returns:
            True if the sensor is Linux.
        '''
        if self._platform is None:
            # If the platform has not been cached yet, retrieve the info.
            self.getInfo()
        return self._platform == self._PLATFORM_LINUX

    def hostname( self ):
        '''Get the hostname of this sensor.

        Returns:
            a string of the hostname.
        '''
        if self._hostname is None:
            # If the hostname has not been cached yet, retrieve the info.
            self.getInfo()
        return self._hostname

    def getHistoricEvents( self, start, end, limit = None, eventType = None ):
        '''Get the events for this sensor between the two times, requires Insight (retention) enabled.

        Args:
            start (int): start unix (seconds) timestamp to fetch events from.
            end (int): end unix (seconds) timestamp to feth events to.
            limit (int): maximum number of events to return.
            eventType (str): return events only of this type.

        Returns:
            a list of events.
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

        if eventType is not None:
            req[ 'event_type' ] = eventType

        data = self._manager._apiCall( 'insight/%s/%s' % ( self._manager._oid, self.sid ), GET, queryParams = req )
        return [ enhanceEvent( e ) for e in self._manager._unwrap( data[ 'events' ] ) ]

    def getHistoricOverview( self, start, end ):
        '''Get a list of timestamps representing where sensor data is available in Insight (retention).

        Args:
            start (int): start unix (seconds) timestamp to look for events from.
            end (int): end unix (seconds) timestamp to look for events to.

        Returns:
            a list of timestamps.
        '''
        start = int( start )
        end = int( end )

        req = {
            'start' : start,
            'end' : end,
        }

        data = self._manager._apiCall( 'insight/%s/%s/overview' % ( self._manager._oid, self.sid ), GET, queryParams = req )
        return data[ 'overview' ]

    def isDataAvailableFor( self, timestamp ):
        '''Check if data is available in Insight for this sensor at this specific time.

        Args:
            timestamp (int): time (unix seconds epoch) to check for events.

        Returns:
            True if data is available.
        '''
        # The overview technically searches for batches of data coming in
        # during that time frame, so we look for something shortly after.
        batches = self.getHistoricOverview( timestamp, timestamp + ( 60 * 60 * 2 ) )
        return 0 != len( batches )

    def __str__( self ):
        return self.sid

    def __repr__( self ):
        return self.sid
