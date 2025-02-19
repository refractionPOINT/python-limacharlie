import limacharlie

def test_credentials( oid, key ):
    lc = limacharlie.Manager( oid, key )

    assert( lc.testAuth( [
        'org.get',
        'sensor.get',
        'sensor.list',
        'replicant.get',
        'replicant.task',
    ] ) )

def test_replicants_available( oid, key ):
    lc = limacharlie.Manager( oid, key )

    replicants = list( lc.getAvailableReplicants() )

    assert( 0 != len( replicants ) )