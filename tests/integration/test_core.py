import limacharlie
import time

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
        'fp.ctrl',
    ] ) )

def test_whoami( oid, key ):
    lc = limacharlie.Manager( oid, key )

    who = lc.whoAmI()
    assert( 0 != len( who.get( 'perms', [] ) ) )
    assert( 0 != len( who.get( 'orgs', [] ) ) )

def test_sensors( oid, key ):
    lc = limacharlie.Manager( oid, key )

    sensors = list( lc.sensors() )
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

    resp = lc.add_rule( testRuleName, {
        'op' : 'is tagged',
        'tag' : 'test-tag-python-sdk',
        'event' : 'NEW_PROCESS',
    }, [ {
        'action' : 'report',
        'name' : 'test-sdk-detection',
    } ], isReplace = True )
    assert({'guid': resp['guid'], 'hive': {'name': 'dr-general', 'partition': oid }, 'name': testRuleName} == resp)

    time.sleep(1)

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

    resp = lc.add_rule( testRuleName, { 
        'op' : 'is tagged',
        'tag' : 'test-tag-python-sdk',
        'event' : 'NEW_PROCESS',
    }, [ {
        'action' : 'report',
        'name' : 'test-sdk-detection',
    } ], isReplace = True, namespace = testNamespace )
    assert({'guid': resp['guid'], 'hive': {'name': 'dr-managed', 'partition': oid }, 'name': testRuleName} == resp)

    try:
        rules = lc.rules( namespace = testNamespace )
        assert( testRuleName in rules )

        rules = lc.rules( namespace = None )
        assert( testRuleName not in rules )
    finally:
        assert( {} == lc.del_rule( testRuleName, namespace = testNamespace ) )

    assert( testRuleName not in lc.rules( namespace = testNamespace ) )

def test_fps( oid, key ):
    lc = limacharlie.Manager( oid, key )

    testRuleName = 'test-lc-python-sdk-fp'

    resp = lc.add_fp( testRuleName, {
        'op' : 'is',
        'path' : 'cat',
        'value' : 'test-sdk-detection'
    }, isReplace = True )
    assert({'guid': resp['guid'], 'hive': {'name': 'fp', 'partition': oid }, 'name': testRuleName} == resp)

    try:
        rules = lc.fps()
        assert( testRuleName in rules )
    finally:
        assert( {} == lc.del_fp( testRuleName ) )

    assert( testRuleName not in lc.fps() )

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

    assert( 'key' in lc.setIngestionKey( testIngestionKeyName ) )

    try:
        assert( testIngestionKeyName in lc.getIngestionKeys() )
    finally:
        assert( {} == lc.delIngestionKey( testIngestionKeyName ) )

    assert( testIngestionKeyName not in lc.getIngestionKeys() )

def test_api_keys( oid, key ):
    lc = limacharlie.Manager( oid, key )

    keyName = 'automated-test-key-name'
    perms = [ 'org.get', 'sensor.task', 'sensor.get' ]
    perms.sort()

    keys = lc.getApiKeys()
    assert( 0 != len( keys ) )

    response = lc.addApiKey( keyName, perms )
    assert( response )
    assert( response[ 'success' ] )
    assert( response[ 'api_key' ] )
    assert( response[ 'key_hash' ] )

    keys = lc.getApiKeys()
    assert( response[ 'key_hash' ] in keys )
    tmpKey = keys[ response[ 'key_hash' ] ]
    assert( keyName == tmpKey[ 'name' ] )
    tmpKey[ 'priv' ].sort()
    assert( tmpKey[ 'priv' ] == perms )

    lc.removeApiKey( response[ 'key_hash' ] )
    keys = lc.getApiKeys()
    assert( response[ 'key_hash' ] not in keys )

def test_isolation( oid, key ):
    lc = limacharlie.Manager( oid, key )

    for sensor in lc.sensors():
        if sensor.isChrome():
            continue
        if not ( sensor.isMac() or sensor.isWindows() ):
            continue
        if not sensor.isOnline():
            continue
        assert( not sensor.isIsolatedFromNetwork() )
        sensor.isolateNetwork()
        assert( sensor.isIsolatedFromNetwork() )
        sensor.rejoinNetwork()
        assert( not sensor.isIsolatedFromNetwork() )
        break