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

    parser = argparse.ArgumentParser( prog = 'limacharlie' )
    parser.add_argument( 'action',
                         type = str,
                         help = 'management action, currently supported "login" (store credentials), "use" (use specific credentials), "dr" (manage Detection & Response rules), "search" (search for Indicators of Compromise), "replay" (replay D&R rules on data), "sync" (synchronize configurations from/to an org), "who" get current SDK authentication in effect, "detections" (download detections), "events" (downlod events), "artifacts" (get or upload artifacts)' )
    parser.add_argument( 'opt_arg',
                         type = str,
                         nargs = "?",
                         default = None,
                         help = 'optional argument depending on action' )

    # Hack around a bit so that we can pass the help
    # to the proper sub-command line.
    rootArgs = sys.argv[ 1 : 2 ]
    args = parser.parse_args( rootArgs )

    if args.action.lower() == 'login':
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
            uid = raw_input( 'If this key is a *user* API key, specify your UID, or leave empter for a normal API key (UUID): ' ) # noqa
        else:
            uid = input( 'If this key is a *user* API key, specify your UID, or leave empter for a normal API key (UUID): ' )
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
    elif args.action.lower() == 'sync':
        from .Sync import main as cmdMain
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
        args = parser.parse_args( sys.argv[ 2: ] )
        _man = Manager()
        _sensor = _man.sensor( str( args.sid ) )
        for event in _sensor.getHistoricEvents( args.start, args.end, limit = args.limit, eventType = args.eventType ):
            print( json.dumps( event ) )
    else:
        raise Exception( 'invalid action' )

if __name__ == "__main__":
    main()