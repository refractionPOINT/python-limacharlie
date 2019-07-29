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

    parser = argparse.ArgumentParser( prog = 'limacharlie.io' )
    parser.add_argument( 'action',
                         type = str,
                         help = 'management action, currently supported "login", "use" and "init" which stores your OID/API-KEY locally unencrypted' )
    parser.add_argument( 'opt_arg',
                         type = str,
                         nargs = "?",
                         default = None,
                         help = 'optional argument depending on action' )

    args = parser.parse_args()

    if args.action.lower() == 'login':
        if _IS_PYTHON_2:
            oid = raw_input( 'Enter your Organization ID (UUID): ' )
        else:
            oid = input( 'Enter your Organization ID (UUID): ' )
        try:
            uuid.UUID( oid )
        except:
            print( "Invalid OID" )
            sys.exit( 1 )
        if _IS_PYTHON_2:
            alias = raw_input( 'Enter a name for this access (alias), or leave empty to set default: ' )
        else:
            alias = input( 'Enter a name for this access (alias), or leave empty to set default: ' )
        if '' == alias:
            alias = 'default'
        secretApiKey = getpass.getpass( prompt = 'Enter secret API key: ' )
        conf = {}
        try:
            with open( os.path.expanduser( '~/.limacharlie' ), 'rb' ) as f:
                conf = yaml.load( f.read() )
        except:
            pass
        if 'default' == alias:
            conf[ 'oid' ] = oid
            conf[ 'api_key' ] = secretApiKey
        else:
            conf.setdefault( 'env', {} )
            conf[ 'env' ].setdefault( alias, {} )[ 'oid' ] = oid
            conf[ 'env' ].setdefault( alias, {} )[ 'api_key' ] = secretApiKey
        with open( os.path.expanduser( '~/.limacharlie' ), 'wb' ) as f:
            f.write( yaml.safe_dump( conf, default_flow_style = False ).encode() )
        os.chown( os.path.expanduser( '~/.limacharlie' ), os.getuid(), os.getgid() )
        os.chmod( os.path.expanduser( '~/.limacharlie' ), stat.S_IWUSR | stat.S_IRUSR )
        print( "Credentials have been stored to: %s" % os.path.expanduser( '~/.limacharlie' ) )
    elif args.action.lower() == 'use':
        if args.opt_arg is None:
            # General listing of existing environments.
            with open( os.path.expanduser( '~/.limacharlie' ), 'rb' ) as f:
                conf = yaml.load( f.read() )
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
            if args.opt_arg == '':
                args.opt_arg = 'default'
            if ( args.opt_arg not in conf[ 'env' ] ) and args.opt_arg != 'default':
                print( "Environment not found" )
                sys.exit( 1 )
            print( 'export LC_CURRENT_ENV="%s"' % args.opt_arg )
    elif args.action.lower() == 'init':
        if args.opt_arg is None:
            print( "existing directory name as argument is required" )
            sys.exit( 1 )
        rootPath = os.path.abspath( args.opt_arg )
        if not os.path.isdir( rootPath ):
            print( "directory does not exist: %s" % ( rootPath, ) )
            sys.exit( 1 )
        with open( os.path.join( rootPath, 'LCConf' ), 'wb' ) as f:
            f.write( yaml.safe_dump( {
                "version" : 2,
                "include" : [
                    "outputs.yaml",
                    "management.yaml",
                    "fim.yaml",
                ]
            }, default_flow_style = False ).encode() )
        with open( os.path.join( rootPath, 'outputs.yaml' ), 'wb' ) as f:
            f.write( yaml.safe_dump( {
                "version" : 2,
                "ouputs" : {}
            }, default_flow_style = False ).encode() )
        with open( os.path.join( rootPath, 'management.yaml' ), 'wb' ) as f:
            f.write( yaml.safe_dump( {
                "version" : 2,
                "rules" : {
                    "isolate-network" : {
                        "detect" : {
                            "op": "and",
                            "rules" : [
                                {
                                    "op" : "is tagged",
                                    "tag" : "isolated",
                                    "event" : "CONNECTED",
                                },
                                {
                                    "op" : "is",
                                    "path" : "event/IS_SEGREGATED",
                                    "value" : 0,
                                }
                            ]
                        },
                        "respond" : [
                            {
                                "action" : "task",
                                "command" : "segregate_network",
                            }
                        ]
                    },
                    "rejoin-network" : {
                        "detect" : {
                            "op": "and",
                            "rules" : [
                                {
                                    "op" : "is tagged",
                                    "tag" : "isolated",
                                    "not" : True,
                                    "event" : "CONNECTED",
                                },
                                {
                                    "op" : "is",
                                    "path" : "event/IS_SEGREGATED",
                                    "value" : 1,
                                }
                            ]
                        },
                        "respond" : [
                            {
                                "action" : "task",
                                "command" : "rejoin_network",
                            }
                        ]
                    },
                    "high-performance" : {
                        "detect" : {
                            "op" : "is tagged",
                            "tag" : "high-perf",
                            "event" : "CONNECTED",
                        },
                        "respond" : [
                            {
                                "action" : "task",
                                "command" : "set_performance_mode --is-enabled",
                            }
                        ]
                    }
                }
            }, default_flow_style = False ).encode() )
        with open( os.path.join( rootPath, 'fim.yaml' ), 'wb' ) as f:
            f.write( yaml.safe_dump( {
                "version" : 2,
            }, default_flow_style = False ).encode() )
    else:
        raise Exception( 'invalid action' )

if __name__ == "__main__":
    main()