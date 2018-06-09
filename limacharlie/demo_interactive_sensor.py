import limacharlie
import json
import uuid
import getpass

if __name__ == "__main__":
    def debugPrint( msg ):
        print msg

    print( "We are starting in interactive mode, this means setting an output via limacharlie.io which may take up to 30 seconds to start..." )
    man = limacharlie.Manager( oid = raw_input( 'Enter OID: ' ), 
                               secret_api_key = getpass.getpass( prompt = 'Enter secret API key: ' ), 
                               print_debug_fn = None,
                               inv_id = str( uuid.uuid4() ),
                               is_interactive = True )

    print( "Getting a list of sensors." )
    sensors = man.sensors()

    print( "Got %s sensors." % len( sensors ) )

    # This is a very naive way to proceed. We could issue all tasks, accumulate the
    # futures and then wait on all of them, that would be MUCH faster.
    for sensor in sensors:
        print( "Sensor info: %s" % ( sensor.getInfo(), ) )
        print( "Let's ask for autoruns..." )
        try:
            future = sensor.request( 'os_autoruns' )

            responses = future.getNewResponses( timeout = 10 )
            if( len( responses ) == 0 ):
                print( "Never got a response..." )
            else:
                print( "Received response from sensor: %s" % ( json.dumps( responses, indent = 2 ), ) )

        except limacharlie.utils.LcApiException as e:
            if 'host not connected' in str( e ):
                print( "Offline, moving on..." )
            else:
                raise

    print( "All done." )