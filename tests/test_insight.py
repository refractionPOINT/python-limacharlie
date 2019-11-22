import limacharlie

import time

def test_credentials( oid, key ):
    lc = limacharlie.Manager( oid, key )

    assert( lc.testAuth( [
        'org.get',
        'sensor.get',
        'sensor.list',
        'insight.evt.get',
        'insight.det.get',
        'insight.list',
        'insight.stat',
    ] ) )

def test_insight_status( oid, key ):
    lc = limacharlie.Manager( oid, key )

    assert( lc.isInsightEnabled() )

def test_detections( oid, key ):
    lc = limacharlie.Manager( oid, key )

    detections = lc.getHistoricDetections(
        int( time.time() ) - ( 60 * 60 * 24 ),
        int( time.time() ),
        limit = 10
    )

    # The return is a generator so we
    # will unravel it.
    detections = list( detections )

    assert( isinstance( detections, list ) )

def test_object_informaton( oid, key ):
    lc = limacharlie.Manager( oid, key )

    objects = lc.getObjectInformation( 'domain', 'www.google.com', 'summary' )

    assert( isinstance( objects, dict ) )

def test_batch_object_information( oid, key ):
    lc = limacharlie.Manager( oid, key )

    objects = lc.getBatchObjectInformation( {
        'domain' : [ 'www.google.com', 'www.apple.com' ]
    } )

    assert( isinstance( objects, dict ) )

def test_host_count_platform( oid, key ):
    lc = limacharlie.Manager( oid, key )

    counts = lc.getInsightHostCountPerPlatform()

    assert( isinstance( counts, dict ) )