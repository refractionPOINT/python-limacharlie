import limacharlie

if __name__ == "__main__":
    def debugPrint( msg ):
        print msg

    man = limacharlie.Manager( oid = raw_input( 'Enter OID: ' ), 
                               secret_api_key = raw_input( 'Enter Secret API Key: '), 
                               print_debug_fn = debugPrint )

    sensors = man.sensors()

    print( "Got %s sensors." % len( sensors ) )

    print( "First sensor %s has the tags: %s" % ( sensors[ 0 ].sid, 
                                                  sensors[ 0 ].getTags() ) )

    single_sensor = sensors[ 1 ]
    single_sensor.task( 'dir_list . *' )