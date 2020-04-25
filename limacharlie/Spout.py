from gevent.queue import Queue
import gevent.pool
import sys
import json
import requests
import uuid
import time

from .utils import LcApiException

_CLOUD_KEEP_ALIVES = 60
_TIMEOUT_SEC = ( _CLOUD_KEEP_ALIVES * 2 ) + 1

class Spout( object ):
    '''Listener object to receive data (Events, Detects or Audit) from a limacharlie.io Organization in pull mode.'''

    def __init__( self, man, data_type, is_parse = True, max_buffer = 1024, inv_id = None, tag = None, cat = None, sid = None, extra_params = {} ):
        '''Connect to limacharlie.io to start receiving data.

        Args:
            manager (limacharlie.Manager obj): a Manager to use for interaction with limacharlie.io.
            data_typer (str): the type of data received from the cloud as specified in Outputs (event, detect, audit).
            is_parse (bool): if set to True (default) the data will be parsed as JSON to native Python.
            max_buffer (int): the maximum number of messages to buffer in the queue.
            inv_id (str): only receive events marked with this investigation ID.
            tag (str): only receive Events from Sensors with this Tag.
            cat (str): only receive Detections of this Category.
            sid (str): only receive Events or Detections from this Sensor.
        '''

        self._man = man
        self._oid = man._oid
        self._uid = man._uid
        self._data_type = data_type
        self._cat = cat
        self._tag = tag
        self._invId = inv_id
        self._sid = sid
        self._is_parse = is_parse
        self._max_buffer = max_buffer
        self._dropped = 0

        self._isStop = False

        # This is used to register FutureResults objects where data should go
        # based on the full value of an investigation ID (including the custom tracking after "/").
        self._futures = {}

        if self._data_type not in ( 'event', 'detect', 'audit' ):
            raise LcApiException( 'Invalid data type: %s' % self._data_type )

        # Setup internal structures.
        self.queue = Queue( maxsize = self._max_buffer )
        self._threads = gevent.pool.Group()

        # Connect to limacharlie.io.
        spoutParams = { 'type' : self._data_type }
        if man._secret_api_key:
            spoutParams[ 'api_key' ] = man._secret_api_key
        else:
            spoutParams[ 'jwt' ] = man._jwt
        if inv_id is not None:
            spoutParams[ 'inv_id' ] = self._invId
        if tag is not None:
            spoutParams[ 'tag' ] = self._tag
        if cat is not None:
            spoutParams[ 'cat' ] = self._cat
        if sid is not None:
            spoutParams[ 'sid' ] = self._sid
        if self._uid:
            spoutParams[ 'uid' ] = self._uid
        for k, v in extra_params.items():
            spoutParams[ k ] = v
        # Spouts work by doing a POST to the stream.limacharlie.io service with the
        # OID, Secret Key and any Output parameters we want. The HTTP response will
        # be a stream of data.
        self._hConn = self._getStream( spoutParams )
        if self._hConn.status_code != 200:
            raise LcApiException( 'failed to open Spout (%s): %s' % ( self._hConn.status_code, self._hConn.text ) )
        self._threads.add( gevent.spawn( self._handleConnection, spoutParams ) )
        self._futureCleanupInterval = 30
        self._threads.add( gevent.spawn_later( self._futureCleanupInterval, self._cleanupFutures ) )

    def _getStream( self, spoutParams ):
        return requests.post( 'https://stream.limacharlie.io/%s' % ( self._oid, ),
                              data = spoutParams,
                              stream = True,
                              allow_redirects = False,
                              timeout = _TIMEOUT_SEC )

    def _cleanupFutures( self ):
        now = time.time()
        for trackingId, futureInfo in list( self._futures.items() ):
            ttl = futureInfo[ 1 ]
            if ttl < now:
                self._futures.pop( trackingId, None )
        self._threads.add( gevent.spawn_later( self._futureCleanupInterval, self._cleanupFutures ) )

    def shutdown( self ):
        '''Stop receiving data.'''

        if self._isStop:
            return

        self._isStop = True

        if self._hConn is not None:
            try:
                self._hConn.close()
            except:
                # Ignore errors on shutdown. In python 3 there
                # can be a reentrant exception because of the BufferedIO
                # and HTTPResponse object at close time.
                pass

        self._threads.join( timeout = 2 )

    def getDropped( self ):
        '''Get the number of messages dropped because queue was full.'''
        return self._dropped

    def resetDroppedCounter( self ):
        '''Reset the counter of dropped messages.'''
        self._dropped = 0

    def registerFutureResults( self, tracking_id, future, ttl = ( 60 * 60 * 1 ) ):
        '''Register a FutureResults to receive events coming with a specific tracking ID and investigation ID.

        Args:
            tracking_id (str): the full value of the investigation_id field to match on, including the custom tracking after the "/".
            future (limacharlie.FutureResults): future to receive the events.
            ttl (int): number of seconds this future should be tracked.
        '''
        self._futures[ tracking_id ] = ( future, time.time() + ttl )

    def _handleConnection( self, spoutParams ):
        while not self._isStop:
            self._man._printDebug( "Stream started." )
            try:
                for line in self._hConn.iter_lines( chunk_size = 1024 * 1024 * 10 ):
                    try:
                        if self._is_parse:
                            line = json.loads( line.decode() )
                            # The output.limacharlie.io service also injects a
                            # few trace messages like keepalives and number of
                            # events dropped (if any) from the server (indicating
                            # we are too slow). We filter those out here.
                            if '__trace' in line:
                                if 'dropped' == line[ '__trace' ]:
                                    self._dropped += int( line[ 'n' ] )
                            else:
                                future = self._futures.get( line.get( 'routing', {} ).get( 'investigation_id', None ), None )
                                if future is not None:
                                    future[ 0 ]._addNewResult( line )
                                else:
                                    self.queue.put_nowait( line )
                        else:
                            self.queue.put_nowait( line )
                    except:
                        self._dropped += 1
            except Exception as e:
                if not self._isStop:
                    self._man._printDebug( "Stream closed: %s" % str( e ) )
                else:
                    self._man._printDebug( "Stream closed." )
            finally:
                self._man._printDebug( "Stream closed." )

            if not self._isStop:
                self._hConn = self._getStream( spoutParams )

def _signal_handler():
    global sp
    _printToStderr( 'You pressed Ctrl+C!' )
    if sp is not None:
        sp.shutdown()
    sys.exit( 0 )

def _printToStderr( msg ):
    sys.stderr.write( str( msg ) + '\n' )

if __name__ == "__main__":
    import argparse
    import getpass
    import gevent
    import signal
    import limacharlie

    sp = None
    gevent.signal( signal.SIGINT, _signal_handler )

    parser = argparse.ArgumentParser( prog = 'limacharlie.io spout' )
    parser.add_argument( 'data_type',
                         type = str,
                         help = 'the type of data to receive in spout, one of "event", "detect" or "audit".' )
    parser.add_argument( '-o', '--oid',
                         type = lambda x: str( uuid.UUID( x ) ),
                         required = False,
                         dest = 'oid',
                         help = 'the OID to authenticate as, if not specified global creds are used.' )
    parser.add_argument( '-i', '--investigation-id',
                         type = str,
                         dest = 'inv_id',
                         default = None,
                         help = 'spout should only receive events marked with this investigation id.' )
    parser.add_argument( '-t', '--tag',
                         type = str,
                         dest = 'tag',
                         default = None,
                         help = 'spout should only receive events from sensors tagged with this tag.' )
    parser.add_argument( '-c', '--category',
                         type = str,
                         dest = 'cat',
                         default = None,
                         help = 'spout should only receive detections from this category.' )
    parser.add_argument( '-s', '--sid',
                         type = lambda x: str( uuid.UUID( x ) ),
                         dest = 'sid',
                         default = None,
                         help = 'spout should only receive detections or events from this sensor.' )
    args = parser.parse_args()
    secretApiKey = getpass.getpass( prompt = 'Enter secret API key: ' )

    _printToStderr( "Registering..." )
    man = limacharlie.Manager( oid = args.oid, secret_api_key = secretApiKey )
    sp = limacharlie.Spout( man,
                            args.data_type,
                            inv_id = args.inv_id,
                            tag = args.tag,
                            cat = args.cat,
                            sid = args.sid )

    _printToStderr( "Starting to listen..." )
    while True:
        data = sp.queue.get()
        print( json.dumps( data, indent = 2 ) )

    _printToStderr( "Exiting." )