from limacharlie import Manager
import yaml
import sys
import json

from .utils import GET
from .utils import POST
from .utils import DELETE

def printData( data ):
    if isinstance( data, str ):
        print( data )
    else:
        print( yaml.safe_dump( data, default_flow_style = False ) )

def reportError( msg ):
    sys.stderr.write( msg + '\n' )
    sys.exit( 1 )

def do_list( args, man ):
    resp = man._apiCall( 'hive/%s/%s' % ( args.hive_name, args.partitionKey ), GET )
    printData( resp )

def do_get( args, man ):
    if args.key is None:
        reportError( 'Key required' )

    resp = man._apiCall( 'hive/%s/%s/%s' % ( args.hive_name, args.partitionKey, args.key ), GET )
    printData( resp )

def do_add( args, man ):
    if args.key is None:
        reportError( 'Key required' )

    target = 'mtd'

    data = None
    if args.data is not None:
        data = open( data, 'rb' ).read().decode()
        data = json.loads( data )
        target = 'data'

    usrMtd = {}
    if args.expiry is not None:
        usrMtd[ 'expiry' ] = args.expiry
    if args.enabled is not None:
        usrMtd[ 'enabled' ] = args.enabled.lower() not in ( '0', 'false', 'no' )
    if args.tags is not None:
        usrMtd[ 'tags' ] = [ t.strip() for t in args.tags.split( ',' ) ]

    req = {
        'data' : json.dumps( data ),
    }

    if args.etag is not None:
        req[ 'etag' ] = args.etag
    if len( usrMtd ) != 0:
        req[ 'usr_mtd' ] = json.dumps( usrMtd )

    resp = man._apiCall( 'hive/%s/%s/%s/%s' % ( args.hive_name, args.partitionKey, args.key, target ), POST, req )
    printData( resp )

def do_remove( args, man ):
    Manager( None, None ).del_rule( args.ruleName, namespace = args.namespace )
    printData( 'Removed' )

def main( sourceArgs = None ):
    import argparse

    actions = {
        'list' : do_list,
        'get' : do_get,
        'set' : do_add,
        'remove' : do_remove,
    }

    parser = argparse.ArgumentParser( prog = 'limacharlie hive' )
    parser.add_argument( 'action',
                         type = str,
                         help = 'the action to take, one of: %s' % ( ', '.join( actions.keys(), ) ) )
    
    parser.add_argument( 'hive_name',
                         type = str,
                         help = 'the hive name' )

    parser.add_argument( '-k', '--key',
                         type = str,
                         required = False,
                         dest = 'key',
                         default = None,
                         help = 'the name of the key.' )

    parser.add_argument( '-d', '--data',
                         default = None,
                         required = False,
                         dest = 'data',
                         help = 'the JSON data for the record.' )

    parser.add_argument( '-pk', '--partition-key',
                         default = None,
                         required = False,
                         dest = 'partitionKey',
                         help = 'the partition key to use instead of the default OID.' )

    parser.add_argument( '--etag',
                         default = None,
                         required = False,
                         dest = 'etag',
                         help = 'the optional previous etag expected for transactions.' )

    parser.add_argument( '--expiry',
                         default = None,
                         required = False,
                         dest = 'expiry',
                         help = 'a millisecond epoch timestamp when the record should expire.' )

    parser.add_argument( '--enabled',
                         default = None,
                         required = False,
                         dest = 'enabled',
                         help = 'whether the record is enabled or disabled.' )

    parser.add_argument( '--tags',
                         default = None,
                         required = False,
                         dest = 'tags',
                         help = 'comma separated list of tags.' )

    args = parser.parse_args( sourceArgs )

    man = Manager( None, None )
    if args.partitionKey is None:
        args.partitionKey = man._oid
    actions[ args.action.lower() ]( args, man )

if '__main__' == __name__:
    main()