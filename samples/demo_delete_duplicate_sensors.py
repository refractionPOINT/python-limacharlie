# Sometimes a sensor can be installed on the same host a few times by mistake.
# This script looks for sensors with the same host name. When found, detelete
# the oldest sensor.

import limacharlie
from limacharlie.utils import parallelExec
import argparse
from datetime import datetime

if __name__ == "__main__":
    parser = argparse.ArgumentParser( description = 'Delete duplicate sensors.' )
    parser.add_argument( '--dry-run', action = 'store_true', default = False, dest = 'isDryRun' )

    args = parser.parse_args()

    if args.isDryRun:
        print( "---=== DRY RUN ===---" )

    # Instantiate the SDK
    lc = limacharlie.Manager()

    # We will accumulate sensors by hostname.
    sensorsByHostname = {}
    allSensors = []

    # Get all the sensor info. Do this in parallel since it
    # could take a while on a large organization.
    def _getSensorInfo( s ):
        sensorInfo = s.getInfo()
        sensorsByHostname.setdefault( sensorInfo[ 'hostname' ], [] ).append( sensorInfo )
        allSensors.append( sensorInfo )

    print( "Getting all sensor info..." )

    parallelExec( _getSensorInfo, lc.sensors(), maxConcurrent = 5 )

    print( "Found %s sensors with %s unique hostnames." % ( len( allSensors ), len( sensorsByHostname ) ) )

    # For each hostname, if it has more than one sensor, compare the
    # last time we saw the sensor alive.
    for hostname, sensors in sensorsByHostname.items():
        if len( sensors ) == 1:
            continue

        print( "Hostname %s has %s sensors." % ( hostname, len( sensors ) ) )
        latestSensor = sensors[ 0 ]
        for sensor in sensors:
            if datetime.fromisoformat( sensor[ 'alive' ] ) > datetime.fromisoformat( latestSensor[ 'alive' ] ):
                latestSensor = sensor

        print( "Latest sensor is: %s" % ( latestSensor[ 'sid' ] ) )

        # Create a list of all the other sensors so we can delete them.
        toDelete = []
        for sensor in sensors:
            if sensor == latestSensor:
                continue
            toDelete.append( sensor )

        print( "Deleting %s sensors." % ( len( toDelete ), ) )
        for sensor in toDelete:
            print( "Deleting %s." % ( sensor[ 'sid' ], ) )
            if not args.isDryRun:
                lc.sensor( sensor[ 'sid' ] ).delete()

    print( "Done." )