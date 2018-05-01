import limacharlie

def debugPrint( msg ):
    print msg

man = limacharlie.Manager( oid = raw_input( 'Enter OID: ' ), 
                           secret_api_key = raw_input( 'Enter Secret API Key: '), 
                           print_debug_fn = None )

sensors = man.sensors()

print( "Got %s sensors." % len( sensors ) )

print( "First sensor %s has the tags: %s" % ( sensors[ 0 ].sid, 
                                              sensors[ 0 ].getTags() ) )
