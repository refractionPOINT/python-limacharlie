import limacharlie
import json
import gevent
import signal
import sys
import getpass

if __name__ == "__main__":
    def signal_handler():
        global sp
        print( 'You pressed Ctrl+C!' )
        sp.shutdown()
        sys.exit( 0 )

    gevent.signal( signal.SIGINT, signal_handler )

    def debugPrint( msg ):
        print( msg )

    # This example uses interactive credentials, but see the README for alternative
    # ways of getting credentials.

    man = limacharlie.Manager( oid = raw_input( 'Enter OID: ' ),
                                secret_api_key = getpass.getpass( prompt = 'Enter secret API key: ' ),
                                print_debug_fn = debugPrint )

    sp = limacharlie.Spout( man, 'event' )

    while True:
        data = sp.queue.get()
        print( json.dumps( data, indent = 2 ) + "\n\n" )
