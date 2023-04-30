# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

def main():
    import argparse
    import getpass
    import uuid
    import sys
    import stat
    import os
    import yaml
    import time

    parser = argparse.ArgumentParser( prog = 'limacharlie' )
    parser.add_argument( 'action',
                         type = str,
                         help = 'management action, currently supported "login" (store credentials), "use" (use specific credentials), "dr" (manage Detection & Response rules), "search" (search for Indicators of Compromise), "replay" (replay D&R rules on data), "sync" (synchronize configurations from/to an org), "who" get current SDK authentication in effect, "detections" (download detections), "events" (download events), "artifacts" (get or upload artifacts)' )
    parser.add_argument( 'opt_arg',
                         type = str,
                         nargs = "?",
                         default = None,
                         help = 'optional argument depending on action' )

    # Hack around a bit so that we can pass the help
    # to the proper sub-command line.
    rootArgs = sys.argv[ 1 : 2 ]
    args = parser.parse_args( rootArgs )

    if args.action.lower() == 'version':
        from . import __version__
        print( "LimaCharlie Python SDK Version %s" % ( __version__, ) )
    elif args.action.lower() == 'login':
        if _IS_PYTHON_2:
            oid = raw_input( 'Enter your Organization ID (UUID): ' ) # noqa
        else:
            oid = input( 'Enter your Organization ID (UUID): ' )
        try:
            uuid.UUID( oid )
        except:
            print( "Invalid OID" )
            sys.exit( 1 )
        if _IS_PYTHON_2:
            alias = raw_input( 'Enter a name for this access (alias), or leave empty to set default: ' ) # noqa
        else:
            alias = input( 'Enter a name for this access (alias), or leave empty to set default: ' )
        if '' == alias:
            alias = 'default'
        secretApiKey = getpass.getpass( prompt = 'Enter secret API key: ' )
        if _IS_PYTHON_2:
            uid = raw_input( 'If this key is a *user* API key, specify your UID, or leave empty for a normal API key (UUID): ' ) # noqa
        else:
            uid = input( 'If this key is a *user* API key, specify your UID, or leave empty for a normal API key (UUID): ' )
        try:
            if uid != '':
                if 20 > len( uid ):
                    raise Exception()
        except:
            print( "Invalid UID" )
            sys.exit( 1 )
        conf = {}
        try:
            with open( os.path.expanduser( '~/.limacharlie' ), 'rb' ) as f:
                conf = yaml.safe_load( f.read() )
        except:
            pass
        if 'default' == alias:
            conf[ 'oid' ] = oid
            conf[ 'api_key' ] = secretApiKey
            if uid != '':
                conf[ 'uid' ] = uid
            else:
                conf.pop( 'uid', None )
        else:
            conf.setdefault( 'env', {} )
            conf[ 'env' ].setdefault( alias, {} )[ 'oid' ] = oid
            conf[ 'env' ].setdefault( alias, {} )[ 'api_key' ] = secretApiKey
            if uid != '':
                conf[ 'env' ].setdefault( alias, {} )[ 'uid' ] = uid
        with open( os.path.expanduser( '~/.limacharlie' ), 'wb' ) as f:
            f.write( yaml.safe_dump( conf, default_flow_style = False ).encode() )
        os.chown( os.path.expanduser( '~/.limacharlie' ), os.getuid(), os.getgid() )
        os.chmod( os.path.expanduser( '~/.limacharlie' ), stat.S_IWUSR | stat.S_IRUSR )
        print( "Credentials have been stored to: %s" % os.path.expanduser( '~/.limacharlie' ) )
    elif args.action.lower() == 'use':
        parser = argparse.ArgumentParser( prog = 'limacharlie use' )
        parser.add_argument( 'environment_name',
                             type = str,
                             nargs = "?",
                             default = None,
                             help = 'name of the environment to use.' )
        args = parser.parse_args( sys.argv[ 2: ] )
        if args.environment_name is None:
            # General listing of existing environments.
            with open( os.path.expanduser( '~/.limacharlie' ), 'rb' ) as f:
                conf = yaml.safe_load( f.read() )
            print( "Current environment: %s\n" % ( os.environ.get( 'LC_CURRENT_ENV', 'default' ) ) )
            print( "Available environments:" )
            for env in conf.get( 'env', {} ).keys():
                print( env )
            if 'oid' in conf and 'api_key' in conf:
                print( 'default' )

            print( "\nlimacharlie use <environment_name> to change environment" )
        else:
            # Selecting a specific environment.
            with open( os.path.expanduser( '~/.limacharlie' ), 'rb' ) as f:
                conf = yaml.safe_load( f.read() )
            if args.environment_name == '':
                args.environment_name = 'default'
            if ( args.environment_name not in conf[ 'env' ] ) and args.environment_name != 'default':
                print( "Environment not found" )
                sys.exit( 1 )
            print( 'export LC_CURRENT_ENV="%s"' % args.environment_name )
    elif args.action.lower() == 'dr':
        from .DRCli import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'search':
        from .Search import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'replay':
        from .Replay import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'query':
        from .Query import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'sync':
        from .Sync import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'configs':
        from .Configs import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'spotcheck':
        from .SpotCheck import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'spout':
        from .Spout import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'who':
        from . import Manager
        tmpManager = Manager()
        print( "OID: %s" % ( tmpManager._oid, ) )
        print( "UID: %s" % ( tmpManager._uid, ) )
        print( "KEY: %s..." % ( tmpManager._secret_api_key[ : 4 ], ) )
        print( "PERMISSIONS:\n%s" % ( yaml.safe_dump( tmpManager.whoAmI() ), ) )
    elif args.action.lower() == 'logs' or args.action.lower() == 'artifacts':
        from .Logs import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'detections':
        from . import Manager
        import json
        parser = argparse.ArgumentParser( prog = 'limacharlie detections' )
        parser.add_argument( 'start',
                             type = int,
                             help = 'second-based epoch time to start at.' )
        parser.add_argument( 'end',
                             type = int,
                             help = 'second-based epoch time to end at.' )
        parser.add_argument( '--limit',
                             type = int,
                             default = None,
                             dest = 'limit',
                             help = 'maximum number of detections to return.' )
        parser.add_argument( '--cat',
                             type = str,
                             default = None,
                             dest = 'cat',
                             help = 'only get detections of this type.' )
        args = parser.parse_args( sys.argv[ 2: ] )
        _man = Manager()
        for detection in _man.getHistoricDetections( args.start, args.end, limit = args.limit, cat = args.cat ):
            print( json.dumps( detection ) )
    elif args.action.lower() == 'events':
        from . import Manager
        import json
        parser = argparse.ArgumentParser( prog = 'limacharlie events' )
        parser.add_argument( 'sid',
                             type = uuid.UUID,
                             help = 'sensor id to get the events from.' )
        parser.add_argument( 'start',
                             type = int,
                             help = 'second-based epoch time to start at.' )
        parser.add_argument( 'end',
                             type = int,
                             help = 'second-based epoch time to end at.' )
        parser.add_argument( '--limit',
                             type = int,
                             default = None,
                             dest = 'limit',
                             help = 'maximum number of events to return.' )
        parser.add_argument( '--event-type',
                             type = str,
                             default = None,
                             dest = 'eventType',
                             help = 'only get events of this type.' )
        parser.add_argument( '--output-name',
                             type = str,
                             default = None,
                             dest = 'outputName',
                             help = 'send data to a named output instead.' )
        args = parser.parse_args( sys.argv[ 2: ] )
        _man = Manager()
        _sensor = _man.sensor( str( args.sid ) )
        for event in _sensor.getHistoricEvents( args.start, args.end, limit = args.limit, eventType = args.eventType, outputName = args.outputName ):
            print( json.dumps( event ) )
    elif args.action.lower() == 'hive':
        from .Hive import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'extension':
        from .Extensions import main as cmdMain
        cmdMain( sys.argv[ 2 : ] )
    elif args.action.lower() == 'create_org':
        from . import Manager
        import json
        parser = argparse.ArgumentParser( prog = 'limacharlie create_org' )
        parser.add_argument( 'name',
                             type = str,
                             help = 'name of the organization to create.' )
        parser.add_argument( '--location',
                             type = str,
                             default = None,
                             dest = 'loc',
                             help = 'location where to create the organization, omit to get location list.' )
        args = parser.parse_args( sys.argv[ 2: ] )
        _man = Manager()
        res = _man.createNewOrg( args.name, args.loc )
        print( json.dumps( res, indent = 2 ) )
    elif args.action.lower() == 'schema':
        from . import Manager
        import json
        parser = argparse.ArgumentParser( prog = 'limacharlie schema' )
        parser.add_argument( '--schema-name',
                             type = str,
                             dest = 'name',
                             default = None,
                             required = False,
                             help = 'schema name to retrieve, schema list is returned if not specified.' )
        args = parser.parse_args( sys.argv[ 2: ] )
        _man = Manager()
        if args.name is None:
            res = _man.getSchemas()
        else:
            res = _man.getSchema( name = args.name )
        print( json.dumps( res, indent = 2 ) )
    elif args.action.lower() == 'org_stats':
        from . import Manager
        import yaml
        print( yaml.dump( Manager().getUsageStats() ) )
    elif args.action.lower() == 'mass-tag':
        from . import Manager
        import json
        parser = argparse.ArgumentParser( prog = 'limacharlie mass-tag' )
        parser.add_argument( 'sensor_selector',
                             type = str,
                             help = 'sensor selector expression to apply the tags to.' )
        parser.add_argument( '--remove-tags',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'isRemoveTags',
                         help = 'remove the tags instead of adding them.' )
        parser.add_argument( '-t', '--tag',
                         action = 'append',
                         required = False,
                         default = [],
                         dest = 'tag',
                         help = 'tag to add or remove.' )
        parser.add_argument( '--ttl',
                             type = int,
                             default = None,
                             dest = 'ttl',
                             help = 'ttl for tagging.' )
        args = parser.parse_args( sys.argv[ 2: ] )
        _man = Manager()
        for sensor in _man.sensors( selector = args.sensor_selector ):
            for tag in args.tag:
                if not args.isRemoveTags:
                    print( "tagging sensor %s with %s (ttl = %s)..." % ( sensor.sid, tag, args.ttl ) )
                    sensor.tag( tag, ttl = args.ttl )
                    print( "done" )
                else:
                    print( "removing tag %s from sensor %s..." % ( tag, sensor.sid ) )
                    sensor.untag( tag )
                    print( "done" )
        print( "all done" )
    elif args.action.lower() == 'sensors':
        from . import Manager
        import json
        parser = argparse.ArgumentParser( prog = 'limacharlie sensors' )
        parser.add_argument( '--selector',
                             default = None,
                             type = str,
                             dest = 'sensor_selector',
                             help = 'sensor selector expression.' )
        parser.add_argument( '--limit',
                             type = int,
                             default = None,
                             dest = 'limit',
                             help = 'limit number of result per underlying query.' )
        parser.add_argument( '--with-ip',
                             type = str,
                             default = None,
                             dest = 'with_ip',
                             help = 'list sensors with the given internal or external ip.' )
        parser.add_argument( '--with-hostname-prefix',
                             type = str,
                             default = None,
                             dest = 'with_hostname_prefix',
                             help = 'list sensors with the given hostname prefix.' )
        args = parser.parse_args( sys.argv[ 2: ] )
        _man = Manager()
        for sensor in _man.sensors( selector = args.sensor_selector, limit = args.limit, with_ip = args.with_ip, with_hostname_prefix = args.with_hostname_prefix ):
            print( json.dumps( sensor.getInfo(), indent = 2 ) )
    elif args.action.lower() == 'sensors_with_ip':
        from . import Manager
        import json
        parser = argparse.ArgumentParser( prog = 'limacharlie sensors_with_ip' )
        parser.add_argument( 'ip',
                             type = str,
                             help = 'IP address to look for.' )
        parser.add_argument( '--start',
                             type = int,
                             default = None,
                             dest = 'start',
                             help = 'optional start second epoch.' )
        parser.add_argument( '--end',
                             type = int,
                             default = None,
                             dest = 'end',
                             help = 'optional end second epoch.' )
        args = parser.parse_args( sys.argv[ 2: ] )
        _man = Manager()
        if args.start is not None and args.end is not None:
            start = args.start
            end = args.end
        else:
            start = int(time.time() - (4*60*60))
            end = int(time.time())
        print( json.dumps( _man.getSensorsWithIp( args.ip, start, end ), indent = 2 ) )
    else:
        raise Exception( 'invalid action' )

if __name__ == "__main__":
    main()
