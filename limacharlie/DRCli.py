from limacharlie import Manager
import yaml
import sys

def printData( data ):
    if isinstance( data, str ):
        print( data )
    else:
        print( yaml.safe_dump( data, default_flow_style = False ) )

def reportError( msg ):
    sys.stderr.write( msg + '\n' )
    sys.exit( 1 )

def do_list( args ):
    rules = Manager( None, None ).rules( args.namespace )
    for rule in rules.values():
        rule.pop( 'detect', None )
        rule.pop( 'respond', None )
        rule.pop( 'name', None )
        rule.pop( 'oid', None )
    printData( { ruleName: rule for ruleName, rule in rules.items() if not ruleName.startswith( '_' ) } )

def do_get( args ):
    if args.ruleName is None:
        reportError( 'No rule name specified.' )
    rule = Manager( None, None ).rules( args.namespace ).get( args.ruleName, None )
    if rule is None:
        reportError( 'Rule not found.' )
    printData( rule )

def do_add( args ):
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

def do_remove( args ):
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

    parser = argparse.ArgumentParser( prog = 'limacharlie dr' )
    parser.add_argument( 'action',
                         type = str,
                         help = 'the action to take, one of: %s' % ( ', '.join( actions.keys(), ) ) )

    parser.add_argument( '-r', '--rule-name',
                         type = str,
                         required = False,
                         dest = 'ruleName',
                         default = None,
                         help = 'the name of the rule.' )

    parser.add_argument( '-f', '--rule-file',
                         default = None,
                         required = False,
                         dest = 'ruleFile',
                         help = 'the file path holding the rule content.' )

    parser.add_argument( '-n', '--namespace',
                         default = None,
                         required = False,
                         dest = 'namespace',
                         help = 'the namespace to use.' )

    parser.add_argument( '--replace',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'isReplace',
                         help = 'replace the rule by that name if it already exists.' )

    args = parser.parse_args( sourceArgs )

    actions[ args.action.lower() ]( args )

if '__main__' == __name__:
    main()