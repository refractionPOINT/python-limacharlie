import uuid
import time
import json

from .utils import LcApiException
from .utils import GET
from .utils import DELETE
from .utils import POST
from .utils import FutureResults
from .utils import enhanceEvent

class Sensor( object ):
    '''Representation of a limacharlie.io Sensor.'''

    _PLATFORM_WINDOWS = 0x10000000
    _PLATFORM_LINUX = 0x20000000
    _PLATFORM_MACOS = 0x30000000
    _PLATFORM_IOS = 0x40000000
    _PLATFORM_ANDROID = 0x50000000
    _PLATFORM_CHROMEOS = 0x60000000

    _ARCHITECTURE_X86 = 0x00000001
    _ARCHITECTURE_X64 = 0x00000002
    _ARCHITECTURE_ARM = 0x00000003
    _ARCHITECTURE_ARM64 = 0x00000004
    _ARCHITECTURE_ALPINE64 = 0x00000005
    _ARCHITECTURE_CHROME = 0x00000006

    def __init__( self, manager, sid, detailedInfo = None ):
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
        self._detailedInfo = detailedInfo

    def setInvId( self, inv_id ):
        '''Set an investigation ID to be applied to all actions done using the object.

        Args:
            inv_id (str): investigation ID to propagate.
        '''

        self._invId = inv_id

    def waitToComeOnline( self, timeout ):
        '''Wait for the sensor to be online.

        Args:
            timeout (int): number of seconds to wait up to

        Returns:
            True if sensor is back or False if timeout
        '''
        deadline = time.time() + timeout

        while not self.isOnline():
            if time.time() >= deadline:
                return False
            time.sleep( min( 60, deadline - time.time() ) )

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
            time.sleep( 1 )
            if future.wasReceived:
                break
            if time.time() > deadline:
                print("DEADLINE")
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

    def tag( self, tag, ttl=None ):
        '''Apply a Tag to the Sensor.

        Args:
            tag (str or list of str): Tag(s) to apply.
            ttl (int): number of seconds the Tag should remain applied.

        Returns:
            the REST API response (JSON).
        '''
        if ttl is not None:
            req = { 'tags' : tag, 'ttl' : int( ttl ) }
        else:
            req = { 'tags' : tag }
        return self._manager._apiCall( '%s/tags' % self.sid, POST, req )

    def untag( self, tag ):
        '''Remove a Tag from the Sensor.

        Args:
            tag (str): Tag to remove.

        Returns:
            the REST API response (JSON).
        '''

        if isinstance( tag, str ):
            req = { 'tag' : tag }
        else:
            req = { 'tags' : ','.join( tag ) }
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
        data = self._detailedInfo
        if not data:
            data = self._manager._apiCall( '%s' % self.sid, GET )[ 'info' ]

        # We massage the info a bit to make it easier to understand.
        platToString = {
            self._PLATFORM_WINDOWS : 'windows',
            self._PLATFORM_LINUX : 'linux',
            self._PLATFORM_MACOS : 'macos',
            self._PLATFORM_IOS : 'ios',
            self._PLATFORM_ANDROID : 'android',
            self._PLATFORM_CHROMEOS : 'chromeos',
        }
        archToString = {
            self._ARCHITECTURE_X86 : 'x86',
            self._ARCHITECTURE_X64 : 'x64',
            self._ARCHITECTURE_ARM : 'arm',
            self._ARCHITECTURE_ARM64 : 'arm64',
            self._ARCHITECTURE_ALPINE64 : 'alpine64',
            self._ARCHITECTURE_CHROME : 'chrome',
        }

        self._platform = data[ 'plat' ]
        self._architecture = data[ 'arch' ]
        self._hostname = data.get( 'hostname', None )
        self._is_isolated = data.get( 'is_isolated', None )
        self._should_isolate = data.get( 'should_isolate', None )
        self._is_sealed = data.get( 'is_sealed', None )
        self._should_seal = data.get( 'should_seal', None )

        data[ 'plat' ] = platToString.get( data[ 'plat' ], data[ 'plat' ] )
        data[ 'arch' ] = archToString.get( data[ 'arch' ], data[ 'arch' ] )

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

    def isChrome( self ):
        '''Checks if the sensor is on Chrome.

        Returns:
            True if the sensor is Chrome.
        '''
        if self._architecture is None:
            # If the platform has not been cached yet, retrieve the info.
            self.getInfo()
        return self._architecture == self._ARCHITECTURE_CHROME

    def isChromeOS( self ):
        '''Checks if the sensor is on ChromeOS.

        Returns:
            True if the sensor is on ChromeOS.
        '''
        if self._architecture is None:
            # If the platform has not been cached yet, retrieve the info.
            self.getInfo()
        return self._platform == self._PLATFORM_CHROMEOS

    def hostname( self ):
        '''Get the hostname of this sensor.

        Returns:
            a string of the hostname.
        '''
        if self._hostname is None:
            # If the hostname has not been cached yet, retrieve the info.
            self.getInfo()
        return self._hostname

    def getHistoricEvents( self, start, end, limit = None, eventType = None, isForward = True, outputName = None ):
        '''Get the events for this sensor between the two times, requires Insight (retention) enabled.

        Args:
            start (int): start unix (seconds) timestamp to fetch events from.
            end (int): end unix (seconds) timestamp to feth events to.
            limit (int): maximum number of events to return.
            eventType (str): return events only of this type.
            isForward (bool): return events in ascending order.
            outputName (str): send data to a named output instead.

        Returns:
            a generator of events.
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
            'is_forward' : 'true' if isForward else 'false',
        }

        if limit is not None:
            req[ 'limit' ] = limit

        if eventType is not None:
            req[ 'event_type' ] = eventType
        if outputName is not None:
            req[ 'output_name' ] = outputName
            yield self._manager._apiCall( 'insight/%s/%s' % ( self._manager._oid, self.sid ), GET, queryParams = req )
            return

        nReturned = 0
        while cursor:
            req[ 'cursor' ] = cursor
            data = self._manager._apiCall( 'insight/%s/%s' % ( self._manager._oid, self.sid ), GET, queryParams = req )
            cursor = data.get( 'next_cursor', None )
            for event in self._manager._unwrap( data[ 'events' ] ):
                yield enhanceEvent( event )
                nReturned += 1
                if limit is not None and limit <= nReturned:
                    break
            if limit is not None and limit <= nReturned:
                break

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

    def getObjectTimeline( self, start, end, bucketing = 'day', onlyTypes = None ):
        '''Get summarized information about timeline of Objects (IOCs) for this host.

        Args:
            start (int): start time (unix seconds epoch) of the period to search.
            end (int): end time (unix seconds epoch) of the period to search.
            bucketing (str): granularity of the timeline, one of "hour", "day", "week", "month".
            onlyTypes (list): list of object types to look for, all if undefined.

        Returns:
            Dict of timelines per type and object.
        '''
        req = {
            'oid' : self._manager._oid,
            'start' : start,
            'end' : end,
            'bucketing' : bucketing,
            'sid' : self.sid,
            'is_compressed' : True,
            'objects' : json.dumps( { t : [] for t in onlyTypes } ) if onlyTypes is not None else "{}",
        }

        data = self._manager._apiCall( 'insight/%s/objects_timeline' % ( self._manager._oid, ), POST, req )
        data = self._manager._unwrap( data[ 'timeline' ] )

        # We don't care about the prevalence counters in this case
        # so we'll just strip it down.
        for oType, objects in data.items():
            for o, timeInfo in objects.items():
                objects[ o ] = sorted( tuple( timeInfo.keys() ) )

        return data

    def getChildrenEvents( self, atom ):
        '''Get all children events from a given atom.

        Args:
            atom (string): atom to get the children of.

        Returns:
            List of events.
        '''
        req = {
            'oid' : self._manager._oid,
            'is_compressed' : True,
        }

        data = self._manager._apiCall( 'insight/%s/%s/%s/children' % ( self._manager._oid, self.sid, atom ), GET, queryParams = req )
        data = self._manager._unwrap( data[ 'events' ] )

        return data

    def getEventByAtom( self, atom ):
        '''Get an event by atom.

        Args:
            atom (string): atom to get the event of.

        Returns:
            Event.
        '''
        return self._manager._apiCall( 'insight/%s/%s/%s' % ( self._manager._oid, self.sid, atom ), GET )

    def delete( self ):
        '''Delete the sensor. It will not be able to connect to the cloud anymore, but will not be uninstalled.abs
        '''

        return self._manager._apiCall( '%s' % self.sid, DELETE, {} )

    def isIsolatedFromNetwork( self ):
        '''Determine if the given sensor is marked to be isolated from the network.

        Returns:
            True if isolated.
        '''
        # Network isolation is ephemeral, so always refresh.
        self.getInfo()
        return self._should_isolate

    def isolateNetwork( self ):
        '''Mark the sensor for network isolation (persistent).'''
        return self._manager._apiCall( '%s/isolation' % ( self.sid, ), POST )

    def rejoinNetwork( self ):
        '''Remove the sensor from network isolation (persistent).'''
        return self._manager._apiCall( '%s/isolation' % ( self.sid, ), DELETE )

    def isSealed( self ):
        '''Determine if the given sensor is marked to be sealed.

        Returns:
            True if sealed.
        '''
        # Seal is ephemeral, so always refresh.
        self.getInfo()
        return self._should_seal

    def seal( self ):
        '''Mark the sensor for sealing (persistent).'''
        return self._manager._apiCall( '%s/seal' % ( self.sid, ), POST )

    def unseal( self ):
        '''Remove the sensor from sealing (persistent).'''
        return self._manager._apiCall( '%s/seal' % ( self.sid, ), DELETE )

    def getRetainedEventCount( self, startTime, endTime, isDetailed = False ):
        '''Get the number of events retained for a given sensor between two second epochs.

        Args:
            startTime (int): time (unix seconds epoch) of the period start.
            endTime (int): time (unix seconds epoch) of the period end.

        Returns:
            Event counts.
        '''
        return self._manager._apiCall( 'insight/event_count/%s/%s' % ( self._manager._oid, self.sid ), GET, queryParams = {
            'start' : startTime,
            'end' : endTime,
            'is_detailed' : 'true' if isDetailed else 'false',
        } )

    def __str__( self ):
        return self.sid

    def __repr__( self ):
        return self.sid
