import limacharlie
import json
import signal
import sys
import getpass

if __name__ == "__main__":
    def signal_handler(signal, frame):
        global fh
        print( 'You pressed Ctrl+C!' )
        fh.shutdown()
        sys.exit( 0 )

    signal.signal( signal.SIGINT, signal_handler )

    def debugPrint( msg ):
        print( msg )

    # This example uses interactive credentials, but see the README for alternative
    # ways of getting credentials.

    man = limacharlie.Manager( oid = input( 'Enter OID: ' ),
                               secret_api_key = getpass.getpass( prompt = 'Enter secret API key: ' ),
                               print_debug_fn = debugPrint )

    fh = limacharlie.Firehose( man,
                               input( 'Local Interface: ' ),
                               'event',
                               public_dest = input( 'Public Interface: ' ),
                               name = 'firehose_test' )

    while True:
        data = fh.queue.get()
        print( json.dumps( data, indent = 2 ) + "\n\n" )
