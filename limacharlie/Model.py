from limacharlie import Manager
import yaml
import sys
import json

from .utils import GET
from .utils import POST
from .utils import DELETE

# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

if _IS_PYTHON_2:
    from urllib import quote as urlescape
else:
    from urllib.parse import quote as urlescape

def printData( data ):
    if isinstance( data, str ):
        print( data )
    else:
        print( json.dumps( data, indent = 2 ) )

def reportError( msg ):
    sys.stderr.write( msg + '\n' )
    sys.exit( 1 )

class Model( object ):
    def __init__( self, man, modelName ):
        self._modelName = modelName
        self._man = man

    def mget( self, index_key_name, index_key_value ):
        return self._man._apiCall( 'models/%s/model/%s/records' % ( self._man._oid, self._modelName ), GET, queryParams = {
            'model_name': self._modelName,
            'index_key_name' : index_key_name,
            'index_key_value' : index_key_value,
        } )

    def get( self, primary_key ):
        return self._man._apiCall( 'models/%s/model/%s/record' % ( self._man._oid, self._modelName, ), GET, queryParams = {
            'primary_key' : primary_key,
        } )

    def delete( self, primary_key ):
        return self._man._apiCall( 'models/%s/model/%s/record' % ( self._man._oid, self._modelName, ), GET, queryParams = {
            'primary_key' : primary_key,
        } )

    def query( self, start_index_key_name, start_index_key_value, plan = [] ):
        return self._man._apiCall( 'models/%s/query' % ( self._man._oid, self._modelName ), GET, params = {
            'starting_model_name': self._modelName,
            'starting_key_name' : start_index_key_name,
            'starting_key_value' : start_index_key_value,
        } )
    
    def add( self, primary_key, fields = {} ):
        return self._man._apiCall( 'models/%s/model/%s/record' % ( self._man._oid, self._modelName ), POST, params = {
            'model_name': self._modelName,
            'primary_key': primary_key,
            'fields': json.dumps( fields ),
        } )

def _do_get( args, man ):
    if args.model_name is None:
        reportError( 'Model name required' )

    if args.primary_key is not None:
        printData( Model( man, args.model_name ).get( args.primary_key ) )
        return

    printData( Model( man, args.model_name ).mget( args.index_key_name, args.index_key_value ) )

def _do_add( args, man ):
    if args.model_name is None:
        reportError( 'Model name required' )
    
    data = json.loads( args.data )

    printData( Model( man, args.model_name ).add( args.primary_key, fields = data ) )

def _do_del( args, man ):
    if args.model_name is None:
        reportError( 'Model name required' )

    printData( Model( man, args.model_name ).delete( args.index_key_name, args.index_key_value ) )

def _do_query( args, man ):
    if args.model_name is None:
        reportError( 'Model name required' )

    printData( Model( man, args.model_name ).query( args.index_key_name, args.index_key_value, [ planStringToDict( p ) for p in args.plan ] ) )

def planStringToDict( plan ):
    if plan is None:
        return None
    
    ret = {}
    components = plan.split( ':' )
    if len( components ) < 1:
        raise Exception( 'Invalid plan format ("model_name:hop_limit:relationship1,relationship2,...)' )
    modelName = components[ 0 ]
    ret[ 'model_name' ] = modelName
    if len( components ) > 1:
        ret[ 'hop_limit' ] = int( components[ 1 ] )
    if len( components ) > 2:
        ret[ 'relationships' ] = components[ 2 ].split( ',' )
    return ret

def main( sourceArgs = None ):
    import argparse

    actions = {
        'get' : _do_get,
        'add': _do_add,
        'del': _do_del,
        'query': _do_query,
    }

    parser = argparse.ArgumentParser( prog = 'limacharlie model' )
    parser.add_argument( 'action',
                         type = str,
                         help = 'the action to take, one of: %s' % ( ', '.join( actions.keys(), ) ) )
    
    parser.add_argument( 'model_name',
                         type = str,
                         help = 'the model name' )

    parser.add_argument( '-ikn', '--index-key-name',
                         type = str,
                         required = False,
                         dest = 'index_key_name',
                         default = None,
                         help = 'the name of the index key' )
    parser.add_argument( '-ikv', '--index-key-value',
                         type = str,
                         required = False,
                         dest = 'index_key_value',
                         default = None,
                         help = 'the value of the index key' )
    parser.add_argument( '-pk', '--primary-key',
                         type = str,
                         required = False,
                         dest = 'primary_key',
                         default = None,
                         help = 'the primary key' )
    parser.add_argument( '-p', '--plan',
                         type = str,
                         required = False,
                         dest = 'plan',
                         default = None,
                         nargs = '*',
                         help = 'the query plan' )
    parser.add_argument( '-d', '--data',
                         type = str,
                         required = False,
                         dest = 'data',
                         default = None,
                         help = 'a JSON object to use as record data' )

   

    args = parser.parse_args( sourceArgs )

    man = Manager( None, None )
    actions[ args.action.lower() ]( args, man )

if '__main__' == __name__:
    main()