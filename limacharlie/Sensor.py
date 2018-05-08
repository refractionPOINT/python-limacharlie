import uuid

from .utils import *

class Sensor( object ):
    '''Representation of a limacharlie.io Sensor.'''

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

        tasks = tasks
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
        '''Get Tags applied to the Sensor

        Returns:
            the list of Tags currently applied.
        '''

        data = self._manager._apiCall( '%s/tags' % self.sid, GET )
        return data[ 'tags' ][ self.sid ].keys()