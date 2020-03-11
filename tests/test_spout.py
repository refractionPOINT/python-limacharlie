import limacharlie

def test_credentials( oid, key ):
    lc = limacharlie.Manager( oid, key )

    assert( lc.testAuth( [
        'org.get',
        'sensor.list',
        'sensor.get',
        'output.list',
        'output.set',
        'output.del',
    ] ) )

def test_spout( oid, key ):
    lc = limacharlie.Manager( oid, key, inv_id = 'test-lc-python-sdk-inv', is_interactive = True )

    try:
        # First we need to make sure we have a sensor to test against.
        sensors = list( lc.sensors() )
        assert( 0 != len( sensors ) )

        # We will pick the first sensor in the list that is online.
        targetSensor = None
        for sensor in sensors:
            if ( not sensor.isChrome() ) and sensor.isOnline():
                targetSensor = sensor
                print( "Found sensor %s online, using it for test." % ( sensor, ) )
                break

        assert( targetSensor is not None )

        resp = targetSensor.simpleRequest( 'os_version' )

        assert( resp is not None )
        assert( resp.get( 'event', None ) is not None )
    finally:
        try:
            lc.shutdown()
        except:
            # In Python3 the underlying http client has issues
            # with this call being reentrant. It should not be
            # an issue for us here.
            pass