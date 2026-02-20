from .Sensor import Sensor

from .utils import GET
from .utils import DELETE

class Job( object ):
    '''Representation of a Job created by Services.'''

    def __init__( self, manager, data ):
        self._man = manager
        self.jobId = None
        self.lastNarration = None
        self.cause = None
        self.finished = None
        self.changed = None
        self.created = None
        self.sensors = None
        self.service = None
        self.activity = None
        self._data = data
        self._parseData( data )

    def _parseData( self, data ):
        self.jobId = data.get( 'job_id', None )
        self.lastNarration = data.get( 'last_narration', None )
        self.cause = data.get( 'cause', None )
        self.finished = data.get( 'stopped', None )
        self.changed = data.get( 'last_change', None )
        if self.changed is not None:
            # The Changed timestamp is not ms-based
            # but the others are so we normalize.
            self.changed = self.changed * 1000
        self.created = data.get( 'created', None )
        self.sensors = [ Sensor( self._man, s ) for s in data.get( 'sids', [] ) ]
        self.service = data.get( 'replicant', None )
        if 'record' in data:
            self.activity = data[ 'record' ].get( 'hist', None )

    def update( self ):
        '''Fetch any updates to the job found in the cloud.'''

        data = self._man._apiCall( 'job/%s/%s' % ( self._man._oid, self.jobId ), GET, queryParams = {
            'is_compressed' : 'true',
            'with_data' : 'false',
        } )
        data = self._man._unwrap( data[ 'job' ] )
        self._data = data
        self._parseData( data )

    def fetchDetails( self ):
        '''Fetch detailed activity for this job in the cloud.'''

        data = self._man._apiCall( 'job/%s/%s' % ( self._man._oid, self.jobId ), GET, queryParams = {
            'is_compressed' : 'true',
            'with_data' : 'true',
        } )
        data = self._man._unwrap( data[ 'job' ] )
        self._data = data
        self._parseData( data )

    def delete( self ):
        '''Delete this job.'''

        self._man._apiCall( 'job/%s/%s' % ( self._oid, self.jobId ), DELETE )

    def isFinished( self ):
        '''Check if this job has terminated.

        Returns:
            True if the job is finished.
        '''
        return self.finished is not None

    def __str__( self ):
        return "Job-%s@[%s]" % ( self.jobId, ", ".join( [ str( s ) for s in self.sensors ] ) )

    def __repr__( self ):
        return "Job-%s@[%s]" % ( self.jobId, ", ".join( [ str( s ) for s in self.sensors ] ) )