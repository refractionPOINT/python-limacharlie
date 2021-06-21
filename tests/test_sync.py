import limacharlie

def test_sensors( oid, key ):
    sync = limacharlie.Configs( manager = limacharlie.Manager( oid, key ) )

    sync.push( {}, isForce = True, isRules = True )

    allConfigs = {}
    sync.fetch( allConfigs )
    print( allConfigs )

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
        assert( 'rule' == dataType )
        assert( 'test-sync-rule' == elem )

    allConfigs = {}
    sync.fetch( allConfigs )

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

    sync.push( {}, isForce = True, isRules = True )