import limacharlie
import json
import gevent
import signal
import sys
import getpass

# Just a general signal handler to stop everying cleanly.
def signal_handler():
    global h
    print( 'You pressed Ctrl+C!' )
    if h is not None:
        print( "Stopping hunter." )
        h.stop()
    sys.exit( 0 )

gevent.signal( signal.SIGINT, signal_handler )

def debugPrint( msg ):
    print msg

class TestHunter( limacharlie.Hunter ):
    def init( self ):
        print( "Initializing" )

    def deinit( self ):
        print( "Deinitializing" )

    def run( self ):
        print( "First we will fetch all sensors." )
        sensors = self.LC.sensors()

        print( "Now that we got %s sensors, we will query them one by one." % len( sensors ) )
        for sensor in sensors:
            # First we will demo using callbacks when tracking the sensor.
            self.track( sensor, callback = self.tallyAutoruns )

            # Issue a listing of autoruns.
            try:
                sensor.task( 'os_autoruns' )
            except limacharlie.LcApiException as e:
                print( "Error tasking, sensor was not online? = %s" % str( e ) )
                continue

        # For the purpose of this demo we will just wait a bit for
        # responses to come back via the callback.
        self.sleep( 10 )

        # Now we will do all the same again but using queues.
        for sensor in sensors:
            # Track to the sensor.responses queue.
            self.track( sensor )

            # Send the autoruns listing.
            try:
                sensor.task( 'os_autoruns' )
            except limacharlie.LcApiException as e:
                print( "Error tasking, sensor was not online? = %s" % str( e ) )
                continue

            # Wait for a reply to come.
            try:
                response = sensor.responses.get( timeout = 10 )
            except Exception as e:
                print( "No response came, odd: %s" % response )
                continue

            print( "Received a response in queue from %s" % sensor.sid )
            print( json.dumps( response, indent = 2 ) )

        print( "All tasking sent, waiting for signal to exit." )
        self.stopEvent.wait()

    def tallyAutoruns( self, sensor, response ):
        print( "Received a response in callback from %s" % sensor.sid )
        print( json.dumps( response, indent = 2 ) )

h = None
if __name__ == "__main__":
    import argparse
    print( "Starting" )
    
    # This example uses interactive credentials, but see the README for alternative
    # ways of getting credentials.

    parser = argparse.ArgumentParser( prog = 'limacharlie.io demo hunter' )
    parser.add_argument( '-f', '--is-firehose',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'is_firehose',
                         help = 'if specified, the hunter should use a Firehose to receive data' )
    args = parser.parse_args()

    if args.is_firehose:
        h = TestHunter( raw_input( 'Enter OID: ' ), 
                        getpass.getpass( prompt = 'Enter secret API key: ' ),
                        listen_on = raw_input( 'Local Interface: ' ),
                        public_dest = raw_input( 'Public Interface: ' ),
                        print_debug_fn = debugPrint )
    else:
        h = TestHunter( raw_input( 'Enter OID: ' ), 
                        getpass.getpass( prompt = 'Enter secret API key: ' ),
                        print_debug_fn = debugPrint )
    h.start()
    gevent.joinall( [ h ] )
    
    print( "Exiting" )
