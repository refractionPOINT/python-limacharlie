from limacharlie import Manager
from limacharlie import Hive
import json

from .utils import POST
from .utils import DELETE
from .utils import GET
from .utils import PUT
from .utils import PATCH
from .utils import LcApiException

class Extension( object ):
    def __init__( self, manager ):
        self._manager = manager

    def convert_rules(self, extName, isDryRun = True): 
        updated_rules = []
        # hive get all rules
        hive = Hive.Hive(self._manager, "dr-general")
        gen_dr_rules = hive.list()
        for rule_name in gen_dr_rules:
            hive_record = hive.get(rule_name)
            dnr = getattr(hive_record, 'data', None)
            if dnr is not None:
                stringDnr = str(dnr)
                if "'action': 'service request', 'name': 'zeek'" in stringDnr:
                    new_dnr_string = stringDnr.replace(
                        "'action': 'service request', 'name': 'zeek', 'request': {'action': 'run_on', ", 
                        "'action': 'extension request', 'extension action': 'run_on', 'extension name': 'ext-zeek', 'extension request': {"
                        )
                    zeek_changed_rule = {
                        'r_name': rule_name,
                        'old_dnr': stringDnr,
                        'new_dnr': new_dnr_string,
                    }
                    updated_rules.append(zeek_changed_rule)
        #  if isDryRun, don't send request, print changes
        if isDryRun and len(updated_rules) > 0:
            for updated_rule in updated_rules:
                print(f"Dry run of change on rule '{updated_rule['r_name']}':")
                print("\033[91m{{-}}{}\033[0m".format(updated_rule['old_dnr']))
                print("\033[92m{{+}}{}\033[0m".format(updated_rule['new_dnr']))
        if not isDryRun and len(updated_rules) > 0:
            for updated_rule in updated_rules:
                formatted_dnr_string = updated_rule['new_dnr'].replace("'", '"')
                data = {
                    "data": json.loads(formatted_dnr_string)
                }
                # hive change rule
                try:
                    hr = Hive.HiveRecord(updated_rule['r_name'], data)
                    hive.set(hr)
                except Exception as e:
                    raise LcApiException(f"failed to create detect response for run : {e}")
            
        print("end of func")
        return  
    
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
    
    def rekey( self, extName ):
        return self._manager._apiCall( 'orgs/%s/subscription/extension/%s' % ( self._manager._oid, extName, ), PATCH, {} )

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

def _do_convert_rules(args, ext):
    printData( ext.convert_rules( args.name, isDryRun = args.impersonated ) )

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
        'convert_rules': _do_convert_rules,
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

    parser.add_argument( '--dry-run',
                            action = 'store_true',
                            default = None,
                            required = False,
                            dest = 'isDryRun',
                            help = 'the convert-rules request will be simulated and all rule conversions will be displayed (default is True)' )

    args = parser.parse_args( sourceArgs )

    ext = Extension( Manager( None, None, environment = args.environment ) )
    actions[ args.action.lower() ]( args, ext )

if '__main__' == __name__:
    main()