from limacharlie import Manager
import json

from .utils import POST
from .utils import DELETE
from .utils import GET
from .utils import PUT

class Extension( object ):
    def __init__( self, manager ):
        self._manager = manager

    def migrate( self, extName ):
        return self._manager._apiCall( 'extension/migrate/%s' % ( extName, ), POST, {
            'oid' : self._manager._oid,
        } )

    def request( self, extName, action, data = {}, isImpersonated = False ):
        req = {
            'oid' : self._manager._oid,
            'action' : action,
            'data' : json.dumps( data ),
        }
        if isImpersonated:
            if self._manager._jwt is None:
                self._manager._refreshJWT()
            req[ 'impersonator_jwt' ] = self._manager._jwt
        return self._manager._apiCall( 'extension/request/%s' % ( extName, ), POST, req )
    
    def list( self ):
        return self._manager._apiCall( 'orgs/%s/subscriptions' % ( self._manager._oid, ), GET )

    def subscribe( self, extName ):
        return self._manager._apiCall( 'orgs/%s/subscription/extension/%s' % ( self._manager._oid, extName, ), POST, {} )

    def unsubscribe( self, extName ):
        return self._manager._apiCall( 'orgs/%s/subscription/extension/%s' % ( self._manager._oid, extName, ), DELETE, {} )
    
    def getAll( self ):
        return self._manager._apiCall( 'extension/definition', GET, {} )

    def create( self, extObj ):
        return self._manager._apiCall( 'extension/definition', POST, {}, rawBody = json.dumps( extObj ).encode(), contentType = 'application/json' )
    
    def update( self, extObj ):
        return self._manager._apiCall( 'extension/definition', PUT, {}, rawBody = json.dumps( extObj ).encode(), contentType = 'application/json' )
    
    def get( self, extName ):
        return self._manager._apiCall( 'extension/definition/%s' % ( extName, ), GET )
    
    def delete( self, extName ):
        return self._manager._apiCall( 'extension/definition/%s' % ( extName, ), DELETE )
    
    def getSchema( self, extName ):
        return self._manager._apiCall( 'extension/schema/%s' % ( extName, ), GET )

def printData( data ):
    if isinstance( data, str ):
        print( data )
    else:
        print( json.dumps( data, indent = 2 ) )

def _do_list( args, ext ):
    printData( ext.list() )

def _do_sub( args, ext ):
    printData( ext.subscribe( args.name ) )

def _do_unsub( args, ext ):
    printData( ext.unsubscribe( args.name ) )

def _do_get_all( args, ext ):
    printData( ext.getAll() )

def _do_get( args, ext ):
    printData( ext.get( args.name ) )

def _do_get_schema( args, ext ):
    printData( ext.getSchema( args.name ) )

def _do_request( args, ext ):
    if args.data is None:
        data = {}
    else:
        data = json.loads( args.data )
    printData( ext.request( args.name, args.ext_action, data, isImpersonated = args.impersonated ) )

def main( sourceArgs = None ):
    import argparse

    actions = {
        'list' : _do_list,
        'sub' : _do_sub,
        'unsub' : _do_unsub,
        'get_all' : _do_get_all,
        'get' : _do_get,
        'get_schema' : _do_get_schema,
        'request' : _do_request,
    }

    parser = argparse.ArgumentParser( prog = 'limacharlie extension' )
    parser.add_argument( 'action',
                         type = str,
                         help = 'the action to take, one of: %s' % ( ', '.join( actions.keys(), ) ) )

    parser.add_argument( '--name',
                         default = None,
                         required = False,
                         dest = 'name',
                         help = 'the optional extension name when needed.' )

    parser.add_argument( '--action',
                         default = None,
                         required = False,
                         dest = 'ext_action',
                         help = 'the action for requests.' )

    parser.add_argument( '--data',
                         default = None,
                         required = False,
                         dest = 'data',
                         help = 'the data (JSON) for requests.' )

    parser.add_argument( '--is-impersonated',
                         default = False,
                         required = False,
                         action = 'store_true',
                         dest = 'impersonated',
                         help = 'whether to ask the extension to impersonate you.' )

    parser.add_argument( '-e', '--environment',
                         type = str,
                         required = False,
                         dest = 'environment',
                         default = None,
                         help = 'the name of the LimaCharlie environment (as defined in ~/.limacharlie) to use, otherwise global creds will be used.' )

    args = parser.parse_args( sourceArgs )

    ext = Extension( Manager( None, None, environment = args.environment ) )
    actions[ args.action.lower() ]( args, ext )

if '__main__' == __name__:
    main()