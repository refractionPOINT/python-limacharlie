import limacharlie

def test_sensors( oid, key ):
    sync = limacharlie.Configs( manager = limacharlie.Manager( oid, key ) )

    for change, dataType, elem in sync.push( {}, isForce = True, isRules = True ):
        pass

    allConfigs = {}
    sync.fetch( allConfigs, isRules = True, isResources = True )

    assert( allConfigs )
    assert( 0 != len( allConfigs ) )

    newConfigs = {
        'rules' : {
            'test-sync-rule' : {
                'detect' : {
                    'op' : 'is tagged',
                    'tag' : 'test-tag-python-sync',
                    'event' : 'NEW_PROCESS',
                },
                'respond' : [ {
                    'action' : 'report',
                    'name' : 'test-sync-detection',
                } ]
            }
        }
    }

    for change, dataType, elem in sync.push( newConfigs, isRules = True ):
        assert( '+' == change )
        assert( 'dr-rule' == dataType )
        assert( 'test-sync-rule' == elem )

    allConfigs = {}
    sync.fetch( allConfigs, isRules = True, isResources = True )

    assert( 'test-sync-rule' in allConfigs.get( 'rules', {} ) )

    newConfigs[ 'rules' ][ 'second' ] = {
        'detect' : {
            'op' : 'is tagged',
            'tag' : 'test-tag-python-sync',
            'event' : 'NEW_PROCESS',
        },
        'respond' : [ {
            'action' : 'report',
            'name' : 'test-sync2-detection',
        } ]
    }

    for change, dataType, elem in sync.push( newConfigs, isRules = True ):
        if '=' == change:
            assert( '=' == change )
            assert( 'rule' == dataType )
            assert( 'test-sync-rule' == elem )
        else:
            assert( '+' == change )
            assert( 'rule' == dataType )
            assert( 'second' == elem )

    newConfigs[ 'rules' ].pop( 'second', None )

    for change, dataType, elem in sync.push( newConfigs, isForce = True, isRules = True ):
        if '=' == change:
            assert( '=' == change )
            assert( 'rule' == dataType )
            assert( 'test-sync-rule' == elem )
        else:
            assert( '-' == change )
            assert( 'rule' == dataType )
            assert( 'second' == elem )

    for change, dataType, elem in sync.push( {}, isForce = True, isRules = True ):
        assert( '-' == change )
        assert( 'rule' == dataType )
        assert( 'test-sync-rule' == elem )

    allConfigs = {}
    sync.fetch( allConfigs, isRules = True )

    assert( allConfigs )
    assert( 0 == len( allConfigs.get( 'rules', {} ) ) )