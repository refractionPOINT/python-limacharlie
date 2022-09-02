import limacharlie
import json
import string
import random

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
        },
        
    }

    for change, dataType, elem in sync.push( newConfigs, isRules = True ):
        assert( '+' == change )
        assert( 'rule' == dataType )
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



def test_hive(oid, key):
    sync = limacharlie.Configs( manager = limacharlie.Manager( oid, key ) )

    letters = string.ascii_lowercase
    unique_key = 'test-s3-python-sdk-' + ''.join(random.choice(letters) for i in range(6))

    newConfigs = {
        "hives":{
            "cloud_sensor": {
                unique_key: {
                    "data": {
                        "s3": {
                        "access_key": "test-access-key",
                        "bucket_name": "aws-cloudtrail-logs-005407990505-225b8680",
                        "client_options": {
                            "hostname": "cloudtrail",
                            "identity": {
                            "installation_key": "test-install-key",
                            "oid": "342c7b8f-243a-4acb-8801-d82f3f8dca99"
                            },
                            "platform": "aws",
                            "sensor_seed_key": "cloudtrail"
                        },
                        "secret_key": "secret-key"
                        },
                        "sensor_type": "s3"
                    },
                    "usr_mtd": {
                        "enabled": False,
                        "expiry": 0,
                        "tags": None
                    }
                }
            }
        }
    }

    for change, dataType, elem in sync.push(newConfigs, isForce=True, isDryRun=True, isHives={"cloud_sensor":True}):
        assert(change == "+")
        assert(dataType == "hives")
        assert(elem == "cloud_sensor/"+unique_key)
        print(change," ", dataType," ", elem)

    allConfigs = {}
    sync.fetch( allConfigs, isHives={"cloud_sensor":True})
    print(allConfigs)

