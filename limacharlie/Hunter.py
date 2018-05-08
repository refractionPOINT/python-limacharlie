from .Manager import Manager
from .Firehose import Firehose
import gevent
from gevent.lock import Semaphore
from gevent.queue import Queue
import gevent.pool
import random
import uuid

class Hunter( gevent.Greenlet ):
    def __init__( self, oid, secret_api_key, listen_on = None, public_dest = None, print_debug_fn = None ):
        gevent.Greenlet.__init__( self )
        self._uniqueName = '%s_%s' % ( type( self ).__name__, uuid.uuid4() )
        self._tracked = {}
        self._lock = Semaphore()
        self._threads = gevent.pool.Group()
        self.stopEvent = gevent.event.Event()

        self.LC = Manager( oid, secret_api_key, inv_id = self._uniqueName, print_debug_fn = print_debug_fn )

        if listen_on is None or listen_on == '':
            listen_on = '0.0.0.0:%s' % random.randint( 1024, 65535 )
            self._print( 'No local interface:port specified, listinging on random port: %s' % listen_on )
        
        self._threads.add( gevent.spawn_later( 0, self._fhLoop ) )
        self._fh = Firehose( self.LC, listen_on, 'event', name = self._uniqueName, public_dest = public_dest, inv_id = self._uniqueName )
        self._print( "Inbound channel open, waiting 30 seconds to ensure it is active..." )
        self.sleep( 31 )
        self._print( "Started as %s" % self._uniqueName )

    def _run( self ):
        if hasattr( self, 'init' ):
            self.init()

        self.run()

        if hasattr( self, 'deinit' ):
            self.deinit()

    def stop( self ):
        self._print( "Stopping..." )
        self.stopEvent.set()
        self._print( "Waiting for main thread." )
        self.join()
        self._print( "Waiting for firehose thread." )
        self._threads.join()
        self._print( "Stopped, shutting down firehose." )
        self._fh.shutdown()
        self._print( "Goodbye." )

    def _print( self, msg ):
        print( msg )

    def sleep( self, seconds ):
        gevent.sleep( seconds )

    def _fhLoop( self ):
        while not self.stopEvent.wait( timeout = 0 ):
            try:
                response = self._fh.queue.get( block = True, timeout = 1 )
            except:
                continue
            sid = response[ 'routing' ][ 'sid' ]
            with self._lock:
                if sid in self._tracked:
                    sensorOrCallback = self._tracked[ sid ]
                    if callable( sensorOrCallback ):
                        gevent.spawn_later( 0, sensorOrCallback, response )
                    else:
                        sensorOrCallback.responses.put_nowait( response )


    def track( self, sensor, callback = None ):
        with self._lock:
            # If a callback is requested, we keep that 
            # callback and wrap it with the actual sensor.
            if callback is not None:
                cb = lambda r: callback( sensor, r )
                self._tracked[ sensor.sid ] = cb
            else:
                # Otherwise we just keep the sensor and initialize
                # its own queue where we will put the responses.
                if sensor.responses is None:
                    sensor.responses = Queue( maxsize = 1024 )
                self._tracked[ sensor.sid ] = sensor

    def untrack( self, sensor ):
        with self._lock:
            self._tracked.pop( sensor.sid, None )