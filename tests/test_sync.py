import limacharlie

def test_sensors( oid, key ):
    sync = limacharlie.Sync( manager = limacharlie.Manager( oid, key ) )

    sync.pushRules( {}, isForce = True )

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
                },
                'respond' : [ {
                    'action' : 'report',
                    'name' : 'test-sync-detection',
                } ]
            }
        }
    }

    for change, dataType, elem in sync.pushRules( newConfigs ):
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
        },
        'respond' : [ {
            'action' : 'report',
            'name' : 'test-sync2-detection',
        } ]
    }

    for change, dataType, elem in sync.pushRules( newConfigs ):
        if '=' == change:
            assert( '=' == change )
            assert( 'rule' == dataType )
            assert( 'test-sync-rule' == elem )
        else:
            assert( '+' == change )
            assert( 'rule' == dataType )
            assert( 'second' == elem )

    newConfigs[ 'rules' ].pop( 'second', None )

    for change, dataType, elem in sync.pushRules( newConfigs, isForce = True ):
        if '=' == change:
            assert( '=' == change )
            assert( 'rule' == dataType )
            assert( 'test-sync-rule' == elem )
        else:
            assert( '-' == change )
            assert( 'rule' == dataType )
            assert( 'second' == elem )

    sync.pushRules( {}, isForce = True )