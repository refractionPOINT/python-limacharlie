import limacharlie

def test_credentials( oid, key ):
    lc = limacharlie.Manager( oid, key )

    assert( lc.testAuth( [
        'org.get',
        'sensor.get',
        'sensor.list',
        'dr.list',
        'dr.set',
        'dr.del',
        'dr.list.managed',
        'dr.set.managed',
        'dr.del.managed',
        'ikey.list',
        'ikey.set',
        'ikey.del',
        'output.list',
        'output.set',
        'output.del',
        'org.conf.get',
        'ingestkey.ctrl',
        'audit.get',
    ] ) )

def test_whoami( oid, key ):
    lc = limacharlie.Manager( oid, key )

    who = lc.whoAmI()
    assert( 0 != len( who.get( 'perms', [] ) ) )
    assert( 0 != len( who.get( 'orgs', [] ) ) )

def test_sensors( oid, key ):
    lc = limacharlie.Manager( oid, key )

    sensors = lc.sensors()
    assert( isinstance( sensors, list ) )

def test_outputs( oid, key ):
    lc = limacharlie.Manager( oid, key )

    testOutputName = 'test-lc-python-sdk-out'
    testDest = '1.1.1.1:22'

    assert( lc.add_output(
        testOutputName,
        'syslog',
        'event',
        dest_host = testDest,
        is_tls = True,
        is_strict_tls = True,
        is_no_header = True,
    ) )

    try:
        outputs = lc.outputs()
        assert( outputs.get( testOutputName, {} ).get( 'dest_host', None ) == testDest )
    finally:
        assert( {} == lc.del_output( testOutputName ) )

    assert( testOutputName not in lc.outputs() )

def test_hosts( oid, key ):
    lc = limacharlie.Manager( oid, key )

    hosts = lc.hosts( 'a' )
    assert( isinstance( hosts, list ) )

def test_rules( oid, key ):
    lc = limacharlie.Manager( oid, key )

    testRuleName = 'test-lc-python-sdk-rule'

    assert( {} == lc.add_rule( testRuleName, {
        'op' : 'is tagged',
        'tag' : 'test-tag-python-sdk',
    }, [ {
        'action' : 'report',
        'name' : 'test-sdk-detection',
    } ], isReplace = True ) )

    try:
        rules = lc.rules()
        assert( testRuleName in rules )
    finally:
        assert( {} == lc.del_rule( testRuleName ) )

    assert( testRuleName not in lc.rules() )

def test_rules_namespace( oid, key ):
    lc = limacharlie.Manager( oid, key )

    testRuleName = 'test-lc-python-sdk-rule'
    testNamespace = 'managed'

    if testRuleName in lc.rules():
        assert( {} == lc.del_rule( testRuleName ) )

    if testRuleName in lc.rules( namespace = testNamespace ):
        assert( {} == lc.del_rule( testRuleName, namespace = testNamespace ) )

    assert( {} == lc.add_rule( testRuleName, {
        'op' : 'is tagged',
        'tag' : 'test-tag-python-sdk',
    }, [ {
        'action' : 'report',
        'name' : 'test-sdk-detection',
    } ], isReplace = True, namespace = testNamespace ) )

    try:
        rules = lc.rules( namespace = testNamespace )
        assert( testRuleName in rules )

        rules = lc.rules( namespace = None )
        assert( testRuleName not in rules )
    finally:
        assert( {} == lc.del_rule( testRuleName, namespace = testNamespace ) )

    assert( testRuleName not in lc.rules( namespace = testNamespace ) )

def test_org_config( oid, key ):
    lc = limacharlie.Manager( oid, key )

    val = lc.getOrgConfig( 'vt' )

    assert( val )

def test_org_urls( oid, key ):
    lc = limacharlie.Manager( oid, key )

    urls = lc.getOrgURLs()

    assert( isinstance( urls, dict ) )

def test_ingestion_keys( oid, key ):
    lc = limacharlie.Manager( oid, key )

    testIngestionKeyName = 'test-python-sdk-key'

    assert( {} == lc.setIngestionKey( testIngestionKeyName ) )

    try:
        assert( testIngestionKeyName in lc.getIngestionKeys() )
    finally:
        assert( {} == lc.delIngestionKey( testIngestionKeyName ) )

    assert( testIngestionKeyName not in lc.getIngestionKeys() )