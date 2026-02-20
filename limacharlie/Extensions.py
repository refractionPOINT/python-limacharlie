from limacharlie import Manager
from limacharlie import Hive
import json
import gzip
import base64

from .utils import POST
from .utils import DELETE
from .utils import GET
from .utils import PUT
from .utils import PATCH
from .utils import LcApiException

class Extension( object ):
    def __init__( self, manager ):
        self._manager = manager

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
        return self._manager._apiCall( 'extension/schema/%s' % ( extName, ), GET, queryParams = {
            'oid' : self._manager._oid,
        } )
    
    def migrate( self, extName ):
        return self._manager._apiCall( 'extension/migrate/%s' % ( extName, ), POST, {
            'oid' : self._manager._oid,
        } )

    def request( self, extName, action, data = {}, isImpersonated = False ):
        req = {
            'oid' : self._manager._oid,
            'action' : action,
            'gzdata' : base64.b64encode( gzip.compress( json.dumps( data ).encode() ) ),
        }
        if isImpersonated:
            if self._manager._jwt is None:
                self._manager._refreshJWT()
            req[ 'impersonator_jwt' ] = self._manager._jwt
        return self._manager._apiCall( 'extension/request/%s' % ( extName, ), POST, req )
    
    def convert_rules(self, extName, isDryRun = True): 
        extList = self.list()
        if extName not in extList:
            return f'ERROR: unable to convert rules. {self._manager._oid} is not subscribed to {extName}'
        gen_hive = Hive.Hive(self._manager, "dr-general")
        man_hive = Hive.Hive(self._manager, "dr-managed")
        gen_dr_rules = gen_hive.list()
        man_dr_rules = man_hive.list()
        merged_dr_rules = {**gen_dr_rules, **man_dr_rules}
        updated_rules = []
        for rule_name in merged_dr_rules:
            is_general = rule_name in gen_dr_rules 
            is_managed = rule_name in man_dr_rules
            gen_hive_records = None
            man_hive_records = None   
            if is_general:
                gen_hive_records = gen_hive.get(rule_name)
            if is_managed:
                man_hive_records = man_hive.get(rule_name)                   
            dnr = getattr(gen_hive_records, 'data', None) if is_general else getattr(man_hive_records, 'data', None)
            if dnr is not None:
                hive_type = 'dr-general' if is_general else 'dr-managed'
                detect = dnr.get('detect', None)
                resp_items = dnr.get('respond', None)  
                if resp_items is not None and detect is not None:
                    if contains_action_name(resp_items, extName):  
                        rule_data = update_rule(rule_name, dnr, detect, resp_items, hive_type, extName)
                        updated_rules.append(rule_data)          
        if isDryRun and len(updated_rules) > 0: 
            for updated_rule in updated_rules:
                print(f"Dry run of change on rule '{updated_rule['r_name']}':")
                print("\033[91m- {}\033[0m".format(updated_rule['old_dnr'])) # print red text
                print("\033[92m+ {}\033[0m".format(updated_rule['new_dnr'])) # print green text
                return 'flag --no-dry-run to apply these changes'
        if not isDryRun and len(updated_rules) > 0:
            for updated_rule in updated_rules:
                data = {
                    "data": updated_rule['new_dnr']
                }
                try:
                    hr = Hive.HiveRecord(updated_rule['r_name'], data)
                    if updated_rule['h_name'] == 'dr-general':
                        gen_resp_obj = gen_hive.set(hr)
                        return f'rule {gen_resp_obj["name"]} converted'
                    elif updated_rule['h_name'] == 'dr-managed':
                        man_resp_obj = man_hive.set(hr)
                        return f'rule {man_resp_obj["name"]} converted'
                except Exception as e:
                    raise LcApiException(f"failed to create detect response for run : {e}")
        if extName in extList:
            return f'no {extName} rules require updating'
        else:
            return 'no rule conversions applied'
    
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
    printData( ext.convert_rules( args.name, isDryRun = args.isDryRun ) )

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
                        default = True, 
                        action = argparse.BooleanOptionalAction,
                        required = False,
                        dest = 'isDryRun',
                        help = 'the convert-rules request will be simulated and all rule conversions will be displayed (default is True)' )
    args = parser.parse_args( sourceArgs )

    ext = Extension( Manager( None, None, environment = args.environment ) )
    actions[ args.action.lower() ]( args, ext )

if '__main__' == __name__:
    main()



### Convert Rules Helper Functions ###
def update_rule(ruleName, dnr, detect, respond_items, hiveType, extName):  
    updated_respond = []
    for resp_item in respond_items:
        if resp_item['action'] == 'service request':
            request = resp_item['request']
            ext_resp = convert_response(request, extName, ruleName)                                     
            updated_respond.append(ext_resp)
        else :
            updated_respond.append(resp_item)
    new_dnr = {
        "detect": detect,
        "respond": updated_respond,
    }
    updated_rule_data = {
        'r_name': ruleName,
        'h_name': hiveType, 
        'old_dnr': json.dumps(dnr, indent=2),
        'new_dnr': json.dumps(new_dnr, indent=2),
    }
    return updated_rule_data

def convert_response(req, extName, ruleName):
    if extName == "ext-zeek":
        ext_zeek_resp = {
            "action": "extension request",
            "extension action": "run_on",
            "extension name": "ext-zeek",
            "extension request": {
                "artifact_id": make_transform_exp(req['artifact_id']),
                "retention": req['retention']
            },
        }
        return ext_zeek_resp
    elif extName == 'ext-pagerduty':
        ext_pagerduty_resp = {
            "action": "extension request",
            "extension action": "run",
            "extension name": "ext-pagerduty",
            "extension request": {
                "class": make_transform_exp(req['class']),
                "group": make_transform_exp(req['group']),
                "severity": make_transform_exp(req['severity']),
                "source": make_transform_exp(req['source']),
                "component": make_transform_exp(req['component']),
                "summary": req['summary'],
                "details": '{{ .event }}',
            }
        }
        return ext_pagerduty_resp
    elif extName == 'ext-dumper':
        ext_dumper_resp = {
            "action": "extension request",
            "extension name": "ext-dumper",
            "extension action": "request_dump",
            "extension request": {
                "target": make_transform_exp(req['target']),
                "sid": make_transform_exp(req['sid']),
                "retention": req['retention'],
                "ignore_cert": req['ignore_cert'],
            }
        }
        return ext_dumper_resp
    elif extName == 'ext-velociraptor':
        ext_velociraptor_resp = {
            "action": "extension request",
            "extension action": "collect",
            "extension name": "ext-velociraptor",
            "extension request": {
                "artifact_list": req['artifact_list'],
                "sid": make_transform_exp(req['sid']),
                "sensor_selector": make_transform_exp(req['sensor_selector']),
                "args": make_transform_exp(req['args']),
                "collection_ttl": req['collection_ttl'],
                "retention_ttl": req['retention_ttl'],
                "ignore_cert": req['ignore_cert'],
            }
        }
        return ext_velociraptor_resp
    elif extName == 'ext-yara' and req['action'] == 'scan':
        ext_yara_scan_resp = {
            "action": "extension request",
            "extension action": "scan",
            "extension name": "ext-yara",
            "extension request": {
                "sources": req['sources'],
                "selector": make_transform_exp(req['selector']),
                "sid": make_transform_exp(req['sid']),
                "yara_scan_ttl": req['yara_scan_ttl'],
            }
        }
        return ext_yara_scan_resp
    elif extName == 'ext-reliable-tasking' and req['action'] == 'task':
        ext_reliable_tasking_task_resp = {
            "action": "extension request",
            "extension action": "task",
            "extension name": "ext-reliable-tasking",
            "extension request": {
                "sid": make_transform_exp(req['sid']),
                "tag": make_transform_exp('tag'),
                "selector": make_transform_exp('selector'),
                "context": make_transform_exp('context'),
                "task_id": make_transform_exp('task_id'),
                "ttl": req['ttl'],
            }  
        }
        return ext_reliable_tasking_task_resp
    elif extName == 'ext-reliable-tasking' and req['action'] == 'untask':
        ext_reliable_tasking_untask_resp = {
            "action": "extension request",
            "extension action": "untask",
            "extension name": "ext-reliable-tasking",
            "extension request": {
                "sid": make_transform_exp(req['sid']),
                "tag": make_transform_exp('tag'),
                "selector": make_transform_exp('selector'),
                "task_id": make_transform_exp('task_id'),
            }  
        }
        return ext_reliable_tasking_untask_resp
    elif extName == 'ext-reliable-tasking' and req['action'] == 'list':
        ext_reliable_tasking_list_resp = {
            "action": "extension request",
            "extension action": "list",
            "extension name": "ext-reliable-tasking",
            "extension request": {
                "sid": make_transform_exp(req['sid']),
                "tag": make_transform_exp(req['tag']),
                "selector": make_transform_exp(req['selector']),
            }  

        }
        return ext_reliable_tasking_list_resp
    elif extName == 'ext-reliable-tasking' and req['action'] == 'signal_attempt':
        ext_reliable_tasking_signal_attempt_resp = {
            "action": "extension request",
            "extension action": "signal_attempt",
            "extension name": "ext-reliable-tasking",
            "extension request": {
                "sid": make_transform_exp(req['sid']),
            }            
        }
        return ext_reliable_tasking_signal_attempt_resp
    elif extName == 'ext-reliable-tasking' and req['action'] == 'signal_received':
        ext_reliable_tasking_signal_received_resp = {
            "action": "extension request",
            "extension action": "signal_received",
            "extension name": "ext-reliable-tasking",
            "extension request": {
                "sid": make_transform_exp(req['sid']),
                "inv_id": make_transform_exp(req['inv_id']),
            }   
        }
        return ext_reliable_tasking_signal_received_resp
    else:
        return {
            "ERROR" : f"Failed to convert {ruleName} to {extName}"
        }
    
def contains_action_name(respond_items, ext_name):
    svc_name = ext_name.replace('ext-', '')
    for resp_item in respond_items:
        if resp_item['action'] == 'service request' and resp_item['name'] == svc_name:
            return True
    return False
 
def make_transform_exp(str_var):
    if '<<' in str_var and '>>' in str_var and '/' in str_var:
        str_var = str_var.replace('<<', '{{')
        str_var = str_var.replace('>>', '}}')
        str_var = str_var.replace('/', '.')
        return str_var
    return  '{{' + ' "' + str(str_var) + '" ' + '}}' 