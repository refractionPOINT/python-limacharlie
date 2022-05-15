from limacharlie import Manager
import yaml
import sys

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
    resp = man._apiCall( 'hive/%s/%s' % ( args.hive_name, man._oid ), GET )
    printData( resp )

def do_get( args, man ):
    if args.ruleName is None:
        reportError( 'No rule name specified.' )
    rule = Manager( None, None ).rules( args.namespace ).get( args.ruleName, None )
    if rule is None:
        reportError( 'Rule not found.' )
    printData( rule )

def do_add( args, man ):
    ruleFile = args.ruleFile
    if ruleFile is None:
        reportError( 'No rule file not specified.' )
    try:
        with open( ruleFile, 'rb' ) as f:
            ruleFile = yaml.safe_load( f.read() )
    except Exception as e:
        reportError( 'Error reading rule file yaml: %s' % e )
    detect = ruleFile.get( 'detect', None )
    if detect is None:
        reportError( 'No detect component in rule file.' )
    response = ruleFile.get( 'respond', None )
    if response is None:
        reportError( 'No respond component in rule file.' )
    Manager( None, None ).add_rule( args.ruleName, detect, response, args.isReplace, namespace = args.namespace )
    printData( 'Added' )

def do_remove( args, man ):
    Manager( None, None ).del_rule( args.ruleName, namespace = args.namespace )
    printData( 'Removed' )

def main( sourceArgs = None ):
    import argparse

    actions = {
        'list' : do_list,
        'get' : do_get,
        'add' : do_add,
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
    actions[ args.action.lower() ]( args, man )

if '__main__' == __name__:
    main()