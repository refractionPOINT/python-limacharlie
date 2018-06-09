import limacharlie
import getpass

if __name__ == "__main__":
    def debugPrint( msg ):
        print msg

    man = limacharlie.Manager( oid = raw_input( 'Enter OID: ' ), 
                               secret_api_key = getpass.getpass( prompt = 'Enter secret API key: ' ), 
                               print_debug_fn = debugPrint )

    all_sensors = man.sensors()

    # The number of sensors returned is limited to a few hundreds, so we will just
    # loop a bit over them.
    while True:
        sensors = man.sensors( is_next = True )
        if sensors is None:
            # There are no more sensors.
            break
        all_sensors += sensors

    print( "Got %s sensors." % len( all_sensors ) )

    print( "First sensor %s has the tags: %s" % ( all_sensors[ 0 ].sid, 
                                                  all_sensors[ 0 ].getTags() ) )

    single_sensor = all_sensors[ 1 ]
    print( "Sensor info: %s" % ( single_sensor.getInfo(), ) )
    single_sensor.task( 'dir_list . *' )