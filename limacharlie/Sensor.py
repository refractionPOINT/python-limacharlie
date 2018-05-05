import uuid

from .utils import *

class Sensor( object ):
    def __init__( self, manager, sid ):
        try:
            uuid.UUID( sid )
        except:
            raise LcApiException( 'Invalid sid, should be in UUID format.' )
        self._manager = manager
        self.sid = str( sid )

    def task( self, tasks, inv_id = None ):
        tasks = tasks
        if not isinstance( tasks, ( tuple, list ) ):
            tasks = [ tasks ]
        req = { 'tasks' : tasks }
        if inv_id is not None:
            req[ 'investigation_id' ] = inv_id
        return self._manager._apiCall( '%s' % self.sid, POST, req )

    def tag( self, tag, ttl ):
        req = { 'tags' : str( tag ), 'ttl' : int( ttl ) }
        return self._manager._apiCall( '%s/tags' % self.sid, POST, req )

    def untag( self, tag ):
        req = { 'tag' : str( tag ) }
        return self._manager._apiCall( '%s/tags' % self.sid, DELETE, req )

    def getTags( self ):
        data = self._manager._apiCall( '%s/tags' % self.sid, GET )
        return data[ 'tags' ][ self.sid ].keys()