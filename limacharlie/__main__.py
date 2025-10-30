import sys
import traceback
from .constants import CONFIG_FILE_PATH, EPHEMERAL_CREDS_ENV_VAR


def cli(args):
    """
    Command line interface for the LimaCharlie SDK.

    Args:
        args (list): list of CLI arguments to parse.
    """
    import argparse
    import getpass
    import uuid
    import sys
    import stat
    import os
    import yaml
    import time
    import json

    def prompt_for_oauth_provider():
        """
        Interactively prompt the user to select an OAuth provider.

        Returns:
            str: The selected provider ('google' or 'microsoft')
        """
        print("\nSelect OAuth provider:")
        print("  1. Google (default)")
        print("  2. Microsoft")

        while True:
            try:
                choice = input("\nEnter your choice [1]: ").strip()

                # Default to Google if empty
                if choice == '' or choice == '1':
                    print("Selected: Google")
                    return 'google'
                elif choice == '2':
                    print("Selected: Microsoft")
                    return 'microsoft'
                else:
                    print("Invalid choice. Please enter 1 or 2.")
            except KeyboardInterrupt:
                print("\n\nLogin cancelled by user.")
                sys.exit(1)
            except EOFError:
                print("\n\nLogin cancelled (EOF).")
                sys.exit(1)

    parser = argparse.ArgumentParser( prog = 'limacharlie' )
    parser.add_argument( 'action',
                         type = str,
                         help = 'management action, currently supported "login" (store credentials), "use" (use specific credentials), "set-oid" (change organization ID), "get-arl" (outputs data returned from ARLs), "dr" (manage Detection & Response rules), "search" (search for Indicators of Compromise), "replay" (replay D&R rules on data), "sync" (synchronize configurations from/to an org), "who" get current SDK authentication in effect, "detections" (download detections), "events" (download events), "artifacts" (get or upload artifacts), "users" (manage and invite users)' )
    parser.add_argument( 'opt_arg',
                         type = str,
                         nargs = "?",
                         default = None,
                         help = 'optional argument depending on action' )

    # Hack around a bit so that we can pass the help
    # to the proper sub-command line.
    rootArgs = args[ 1: 2 ]

    # Everything after the command name and the action name that is passed
    # to the action argument parser.
    # For example: limacharlie users invite --email -> ["invite", "--email"]
    actionArgs = args[ 2: ]
    args = parser.parse_args( rootArgs )

    if args.action.lower() == 'version':
        from . import __version__
        print( "LimaCharlie Python SDK Version %s" % ( __version__, ) )
    elif args.action.lower() == 'login':
        # Parse login arguments
        parser = argparse.ArgumentParser( prog = 'limacharlie login' )
        parser.add_argument( '--oauth',
                             action = 'store_true',
                             help = 'use OAuth authentication instead of API key' )
        parser.add_argument( '--no-browser',
                             action = 'store_true',
                             help = 'print URL instead of opening browser (OAuth only)' )
        parser.add_argument( '--oid',
                             type = str,
                             help = 'organization ID (non-interactive mode)' )
        parser.add_argument( '--environment', '--env',
                             type = str,
                             help = 'environment name (default: "default")' )
        parser.add_argument( '--api-key',
                             type = str,
                             help = 'API key (non-interactive mode)' )
        parser.add_argument( '--uid',
                             type = str,
                             default = '',
                             help = 'user ID for user-scoped API keys' )
        
        login_args = parser.parse_args( actionArgs )
        
        if login_args.oauth:
            # OAuth login flow - use simplified Firebase auth
            # This approach lets Firebase handle all OAuth provider complexity,
            # eliminating the need to manage OAuth client credentials in our code
            from .oauth_firebase_simple import perform_simple_firebase_auth

            # Get OID if not provided
            oid = login_args.oid
            if not oid:
                oid = input( 'Enter your Organization ID (UUID), or leave empty: ' )
                if oid:
                    try:
                        uuid.UUID( oid )
                    except:
                        print( "Invalid OID" )
                        sys.exit( 1 )

            # Get environment name
            environment = login_args.environment
            if not environment:
                environment = input( 'Enter a name for this access (environment), or leave empty to set default: ' )
                if '' == environment:
                    environment = 'default'

            # Prompt for OAuth provider selection
            provider = prompt_for_oauth_provider()

            # Perform simplified Firebase auth
            success = perform_simple_firebase_auth(
                oid=oid if oid else None,
                environment=environment if environment != 'default' else None,
                no_browser=login_args.no_browser,
                provider=provider
            )

            if not success:
                sys.exit( 1 )
        else:
            # Traditional API key login
            from .utils import writeCredentialsToConfig
            
            # Support non-interactive mode
            if login_args.oid and login_args.api_key:
                # Non-interactive mode
                oid = login_args.oid
                try:
                    uuid.UUID( oid )
                except:
                    print( "Invalid OID" )
                    sys.exit( 1 )
                
                environment = login_args.environment if login_args.environment else 'default'
                secretApiKey = login_args.api_key
                uid = login_args.uid
                
                if uid != '' and len(uid) > 20:
                    print("UID must be maximum 20 characters long.")
                    sys.exit(1)
            else:
                # Interactive mode (original behavior)
                oid = input( 'Enter your Organization ID (UUID): ' )
                try:
                    uuid.UUID( oid )
                except:
                    print( "Invalid OID" )
                    sys.exit( 1 )
                environment = input( 'Enter a name for this access (environment), or leave empty to set default: ' )
                if '' == environment:
                    environment = 'default'
                secretApiKey = getpass.getpass( prompt = 'Enter secret API key: ' )
                uid = input( 'If this key is a *user* API key, specify your UID, or leave empty for a normal API key (UUID): ' )
                try:
                    if uid != '':
                        if 20 > len( uid ):
                            print("UID must be maximum 20 characters long.")
                            sys.exit(1)
                except:
                    print( "Invalid UID" )
                    sys.exit( 1 )

            writeCredentialsToConfig( environment, oid, secretApiKey, uid )
    elif args.action.lower() == 'use':
        parser = argparse.ArgumentParser( prog = 'limacharlie use' )
        parser.add_argument( 'environment_name',
                             type = str,
                             nargs = "?",
                             default = None,
                             help = 'name of the environment to use.' )
        args = parser.parse_args( actionArgs )
        if args.environment_name is None:
            # General listing of existing environments.
            with open( CONFIG_FILE_PATH, 'rb' ) as f:
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
            with open( CONFIG_FILE_PATH, 'rb' ) as f:
                conf = yaml.safe_load( f.read() )
            if args.environment_name == '':
                args.environment_name = 'default'
            if ( args.environment_name not in conf[ 'env' ] ) and args.environment_name != 'default':
                print( "Environment not found" )
                sys.exit( 1 )
            print( 'export LC_CURRENT_ENV="%s"' % args.environment_name )
    elif args.action.lower() == 'set-oid':
        parser = argparse.ArgumentParser( prog = 'limacharlie set-oid' )
        parser.add_argument( 'oid',
                             type = str,
                             help = 'Organization ID (UUID) to set as default' )
        parser.add_argument( '--environment', '--env',
                             type = str,
                             default = 'default',
                             help = 'environment to update (default: "default")' )
        args = parser.parse_args( actionArgs )
        
        # Validate OID format
        try:
            uuid.UUID( args.oid )
        except:
            print( "Invalid OID format. Must be a valid UUID." )
            sys.exit( 1 )
        
        # Check for ephemeral mode
        if os.environ.get( EPHEMERAL_CREDS_ENV_VAR ):
            print( "Cannot use 'set-oid' command in ephemeral credentials mode (LC_EPHEMERAL_CREDS is set)." )
            print( "In ephemeral mode, credentials are not persisted to disk." )
            print( "Use the LC_OID environment variable instead to set the organization ID." )
            sys.exit( 1 )

        # Load existing config
        from .utils import loadCredentials
        config = loadCredentials()
        if config is None:
            print( "No existing configuration found. Please run 'limacharlie login' first." )
            sys.exit( 1 )

        # Update OID based on environment
        if args.environment == 'default':
            if 'oid' not in config and 'api_key' not in config and 'oauth' not in config:
                print( "No default credentials found. Please run 'limacharlie login' first." )
                sys.exit( 1 )
            old_oid = config.get( 'oid', 'not set' )
            config['oid'] = args.oid
            print( f"Updated default OID from {old_oid} to {args.oid}" )
        else:
            # Update specific environment
            if 'env' not in config or args.environment not in config['env']:
                print( f"Environment '{args.environment}' not found." )
                sys.exit( 1 )
            old_oid = config['env'][args.environment].get( 'oid', 'not set' )
            config['env'][args.environment]['oid'] = args.oid
            print( f"Updated OID for environment '{args.environment}' from {old_oid} to {args.oid}" )

        # Save updated config
        with open( CONFIG_FILE_PATH, 'w' ) as f:
            yaml.safe_dump( config, f )

        # Set file permissions to 600 (read/write for owner only)
        os.chmod( CONFIG_FILE_PATH, stat.S_IRUSR | stat.S_IWUSR )

        print( "Configuration updated successfully." )
    elif args.action.lower() == 'dr':
        from .DRCli import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'search':
        from .Search import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'replay':
        from .Replay import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'query':
        from .Query import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'ai-chat':
        from .AIChat import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'sync':
        from .Sync import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'configs':
        from .Configs import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'spotcheck':
        from .SpotCheck import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'spout':
        from .Spout import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'get-arl':
        from .ARL import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() in ['who', 'whoami']:
        from . import Manager
        tmpManager = Manager()
        print( "OID: %s" % ( tmpManager._oid, ) )
        print( "UID: %s" % ( tmpManager._uid, ) )
        if tmpManager._oauth_creds:
            print( "AUTH: OAuth (Provider: %s)" % ( tmpManager._oauth_creds.get('provider', 'unknown'), ) )
            from .oauth import OAuthManager
            expires_at = tmpManager._oauth_creds.get('expires_at', 0)
            if OAuthManager.is_token_expired(expires_at):
                print( "TOKEN: Expired" )
            else:
                import time
                remaining = expires_at - int(time.time())
                print( "TOKEN: Valid for %d minutes" % ( remaining // 60, ) )
        else:
            print( "AUTH: API Key" )
            print( "KEY: %s..." % ( tmpManager._secret_api_key[ : 4 ], ) )
        print( "PERMISSIONS:\n%s" % ( yaml.safe_dump( tmpManager.whoAmI() ), ) )
    elif args.action.lower() == 'logs' or args.action.lower() == 'artifacts':
        from .Logs import main as cmdMain
        cmdMain( actionArgs )
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
        args = parser.parse_args( actionArgs )
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
        args = parser.parse_args( actionArgs )
        _man = Manager()
        _sensor = _man.sensor( str( args.sid ) )
        for event in _sensor.getHistoricEvents( args.start, args.end, limit = args.limit, eventType = args.eventType, outputName = args.outputName ):
            print( json.dumps( event ) )
    elif args.action.lower() == 'audit':
        from . import Manager
        import json
        parser = argparse.ArgumentParser( prog = 'limacharlie audit' )
        parser.add_argument( 'start',
                             type = int,
                             help = 'second-based epoch time to start at.' )
        parser.add_argument( 'end',
                             type = int,
                             help = 'second-based epoch time to end at.' )
        parser.add_argument( '--sid',
                             type = uuid.UUID,
                             dest = 'sid',
                             help = 'sensor id to get the audit events about.' )
        parser.add_argument( '--limit',
                             type = int,
                             default = None,
                             dest = 'limit',
                             help = 'maximum number of audit events to return.' )
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
        args = parser.parse_args( actionArgs )
        _man = Manager()
        for event in _man.getAuditLogs( args.start, args.end, limit = args.limit, event_type = args.eventType, sid = args.sid ):
            print( json.dumps( event ) )
    elif args.action.lower() == 'hive':
        from .Hive import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'extension':
        from .Extensions import main as cmdMain
        cmdMain( actionArgs )
    elif args.action.lower() == 'model':
        from .Model import main as cmdMain
        cmdMain( actionArgs )
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
        args = parser.parse_args( actionArgs )
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
        args = parser.parse_args( actionArgs )
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
        args = parser.parse_args( actionArgs )
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
    elif args.action.lower() == 'mass-upgrade':
        from .versions import massUpgrade
        massUpgrade()
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
        args = parser.parse_args( actionArgs )
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
        args = parser.parse_args( actionArgs )
        _man = Manager()
        if args.start is not None and args.end is not None:
            start = args.start
            end = args.end
        else:
            start = int(time.time() - (4*60*60))
            end = int(time.time())
        print( json.dumps( _man.getSensorsWithIp( args.ip, start, end ), indent = 2 ) )
    elif args.action.lower() == 'mitre-report':
        from . import Manager
        print(json.dumps(Manager().getMITREReport(), indent = 2))
    elif args.action.lower() == 'users':
        from .User import main as cmdMain
        cmdMain( actionArgs )
    else:
        raise Exception( 'invalid action: %s' % (args.action.lower()) )

def main():
    args = sys.argv

    # Hack since we don't have access to parsed args here and parsing itself may fail
    debug_mode = False
    if "--debug" in args:
        debug_mode = True
        args.remove("--debug")

    # TODO: Should --debug also just imply debug-request so we don't need two flags?
    if "--debug-request" in args:
        args.remove("--debug-request")
        from .Manager import set_default_print_debug_fn
        set_default_print_debug_fn(lambda x: print(x, file=sys.stderr))


    try:
        cli(args)
    except Exception as e:
        print("Error:", e,file=sys.stderr)

        if debug_mode:
            print(traceback.format_exc(), file=sys.stderr)

        return 1

if __name__ == "__main__":
    sys.exit(main())