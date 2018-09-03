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
     
    args = parser.parse_args() 
     
    if args.action.lower() != 'login': 
        raise Exception( 'invalid action' ) 
     
    oid = raw_input( 'Enter your Organization ID (UUID): ' ) 
    try: 
        uuid.UUID( oid ) 
    except: 
        print( "Invalid OID" ) 
        sys.exit( 1 ) 
    secretApiKey = getpass.getpass( prompt = 'Enter secret API key: ' ) 
    with open( os.path.expanduser( '~/.limacharlie' ), 'wb' ) as f: 
        f.write( yaml.safe_dump( { 'oid' : oid, 'api_key' : secretApiKey }, default_flow_style = False ) ) 
    os.chown( os.path.expanduser( '~/.limacharlie' ), os.getuid(), os.getgid() ) 
    os.chmod( os.path.expanduser( '~/.limacharlie' ), stat.S_IWUSR | stat.S_IRUSR ) 
    print( "Credentials have been stored to: %s" % os.path.expanduser( '~/.limacharlie' ) ) 
        