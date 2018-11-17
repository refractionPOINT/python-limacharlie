if __name__ == "__main__":
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
                         help = 'management action, currently supported "login" which stores your OID/API-KEY locally unencrypted' )
    parser.add_argument( 'opt_arg',
                         type = str,
                         nargs = "?",
                         default = None,
                         help = 'optional argument depending on action' )

    args = parser.parse_args()

    if args.action.lower() == 'login':
        oid = raw_input( 'Enter your Organization ID (UUID): ' )
        try:
            uuid.UUID( oid )
        except:
            print( "Invalid OID" )
            sys.exit( 1 )
        alias = raw_input( 'Enter a name for this access (alias): ' )
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
            f.write( yaml.safe_dump( conf, default_flow_style = False ) )
        os.chown( os.path.expanduser( '~/.limacharlie' ), os.getuid(), os.getgid() )
        os.chmod( os.path.expanduser( '~/.limacharlie' ), stat.S_IWUSR | stat.S_IRUSR )
        print( "Credentials have been stored to: %s" % os.path.expanduser( '~/.limacharlie' ) )
    elif args.action.lower() == 'use':
        if args.opt_arg is None:
            # General listing of existing environments.
            with open( os.path.expanduser( '~/.limacharlie' ), 'rb' ) as f:
                conf = yaml.load( f.read() )
            print( "Available environments:" )
            for env in conf.get( 'env', {} ).iterkeys():
                print( env )
            if 'oid' in conf and 'api_key' in conf:
                print( 'default' )
        else:
            # Selecting a specific environment.
            with open( os.path.expanduser( '~/.limacharlie' ), 'rb' ) as f:
                conf = yaml.load( f.read() )
            if args.opt_arg == '':
                args.opt_arg = 'default'
            if ( args.opt_arg not in conf[ 'env' ] ) and args.opt_arg != 'default':
                print( "Environment not found" )
                sys.exit( 1 )
            print( 'export LC_CURRENT_ENV="%s"' % args.opt_arg )
    else:
        raise Exception( 'invalid action' )