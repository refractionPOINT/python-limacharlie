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
            assert( 'dr-rule' == dataType )
            assert( 'test-sync-rule' == elem )
        else:
            assert( '+' == change )
            assert( 'dr-rule' == dataType )
            assert( 'second' == elem )

    newConfigs[ 'rules' ].pop( 'second', None )

    for change, dataType, elem in sync.push( newConfigs, isForce = True, isRules = True ):
        if '=' == change:
            assert( '=' == change )
            assert( 'dr-rule' == dataType )
            assert( 'test-sync-rule' == elem )
        else:
            assert( '-' == change )
            assert( 'dr-rule' == dataType )
            assert( 'second' == elem )

    for change, dataType, elem in sync.push( {}, isForce = True, isRules = True ):
        assert( '-' == change )
        assert( 'dr-rule' == dataType )
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
                    }
                }
            }
        }
    }

    #dry run of adding cloud_sensor
    for change, dataType, elem in sync.push(newConfigs,isDryRun=True, isHives={"cloud_sensor":True}):
        assert(change == "+")
        assert(dataType == "hives")
        assert(elem == "cloud_sensor/"+unique_key)

    #actual run of adding cloud_sensor
    for change, dataType, elem in sync.push(newConfigs,isDryRun=False, isHives={"cloud_sensor":True}):
        assert(change == "+")
        assert(dataType == "hives")
        assert(elem == "cloud_sensor/"+unique_key)


    # run sync fetch to ensure cloud_sensor data can be retrieved and is created
    sensor_configs = {}
    sync.fetch( sensor_configs, isHives={"cloud_sensor":True })
    assert(unique_key in sensor_configs.get( 'hives', {} )['cloud_sensor'])


    #remove newly created config data from sensor_configs as sync.push will auto delete any removed config data when sync push is ran
    sensor_configs["hives"]["cloud_sensor"].pop(unique_key, None)


    #dry run test to ensure unique key is removed, isForce will remove any hive data not part of sensor_config so be weary of removing values from original sensor config 
    # isHives={} can set any key to true and push will run config updates based upon passed sensor_config data and not hive keys
    for change, dataType, elem in sync.push(sensor_configs,isDryRun=True, isForce=True, isHives={"cloud_sensor":True}):
        assert(change == "-")
        assert(dataType == "hives")
        assert(elem == "cloud_sensor/"+unique_key)


    # actual run of sync push and removal of newly created cloud_sensor data
    for change, dataType, elem in sync.push(sensor_configs,isDryRun=False, isForce=True, isHives={"cloud_sensor":True}):
        assert(change == "-")
        assert(dataType == "hives")
        assert(elem == "cloud_sensor/"+unique_key)


        
    # grab actual data after delete to ensure it has been deleted
    sync.fetch( sensor_configs, isHives={"cloud_sensor":True})

    # assert that cloud_sensor no longer contains created cloud_sensor data
    assert(unique_key not in sensor_configs.get( 'hives', {} )['cloud_sensor'])

