from .utils import LcApiException
from .utils import GET
from .utils import DELETE
from .utils import POST
from .utils import HEAD
from .utils import PATCH

from .Manager import Manager
from .Manager import ROOT_URL

import uuid
import sys
import json
import yaml
import os

class Net( object ):
    '''Representation of a limacharlie.io Net.'''

    def __init__( self, manager ):
        self._manager = manager

    def provision( self, iid, names, isEmailUserDirectly = False, withinIPRange = None, excludeLocal = None, dnsServers = None ):
        '''Provision a new LimaCharlie Net sensor.

        Args:
            iid (str): installation key id to use to provision the sensor.
            name (list of str): name(s) to give (used as hostname) to sensor, use email address of user if you use isEmailUserDirectly.
            isEmailUserDirectly (bool): if True, LimaCharlie will email the user set as "name" directly with the credentials.
            withinIPRange (str): optional IP CIDR range where you prefer the provisioned clients to be in.
            excludeLocal (str): optional, by default configs generated for clients route all public IP ranges, this comma separated list of CIDRs describes IP ranges to exclude.
            dnsServers (str): optional, by default configs generated for clients use the Google Public DNS servers (8.8.8.8 and 8.8.4.4), this comma separated list of DNS servers overrides it if specified.
        Returns:
            provisioning information.
        '''
        req = {
            'oid': self._manager._oid,
            'iid': iid,
            'name': names,
            'is_email_to_user': 'true' if isEmailUserDirectly else 'false',
        }
        if withinIPRange is not None:
            req[ 'within_range' ] = withinIPRange
        if excludeLocal is not None:
            req[ 'exclude_local_range' ] = excludeLocal
        if dnsServers is not None:
            req[ 'dns_server' ] = dnsServers
        return self._manager._apiCall( 'net/provision', POST, req, altRoot = ROOT_URL )

    def getStatus( self ):
        '''Get the status of Net for this organization.

        Returns:
            whether the organization has Net enabled or not.
        '''
        req = {
            'oid': self._manager._oid,
        }
        return self._manager._apiCall( 'net/status', GET, queryParams = req, altRoot = ROOT_URL )

    def getUsage( self, sid = None ):
        '''Get usage information for Net sensor.

        Args:
            sid (str): optional, specifies which sensor id to get the information about, entire org otherwise.
        Returns:
            usage information.
        '''
        req = {
            'oid': self._manager._oid,
        }
        if sid is not None:
            req[ 'sid' ] = sid
        return self._manager._apiCall( 'net/usage', GET, queryParams = req, altRoot = ROOT_URL )

    def getApplicablePolicies( self, sid ):
        '''Get policies that apply to Net sensor.

        Args:
            sid (str): sensor id to get the policies for.
        Returns:
            policy names.
        '''
        return self._manager._apiCall( 'net/policy/applicable/%s' % ( sid, ), GET, altRoot = ROOT_URL )

    def getPolicies( self ):
        '''Get active Net policies.

        Args:
            sid (str): optional, specifies which sensor id to get the information about, entire org otherwise.
        Returns:
            dict of all policies.
        '''
        req = {
            'oid': self._manager._oid,
        }
        return self._manager._apiCall( 'net/policy', GET, queryParams = req, altRoot = ROOT_URL ).get( 'policies', {} )

    def setPolicy( self, name, polType, policy, expiresOn = None ):
        '''Set new Net policy.

        Args:
            name (str): policy name.
            polType (str): policy type.
            policy (dict): policy content.
            expiresOn (int): optional second epoch when the policy should become invalid.
        '''
        req = {
            'oid': self._manager._oid,
            'name': name,
            'type': polType,
            'policy': json.dumps( policy ),
        }
        if expiresOn is not None:
            req[ 'expires_on' ] = int( expiresOn )
        return self._manager._apiCall( 'net/policy', POST, req, altRoot = ROOT_URL )

    def delPolicy( self, name ):
        '''Delete active Net policy.

        Args:
            name (str): name of the policy to delete.
        '''
        req = {
            'oid': self._manager._oid,
            'name': name,
        }
        return self._manager._apiCall( 'net/policy', DELETE, queryParams = req, altRoot = ROOT_URL )

def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie net' )
    subparsers = parser.add_subparsers( dest = 'object', help = 'object to work with' )

    parser.add_argument( '--yaml-output',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'isYaml',
                         help = 'if set, output will be in yaml format instead of json' )

    objects = {
        'client' : subparsers.add_parser( 'client', help = 'working with clients' ),
        'policy' : subparsers.add_parser( 'policy', help = 'working with policies' ),
    }

    # client
    subparsers_client = objects[ 'client' ].add_subparsers( dest = 'action', help = 'action to take' )

    # client:status
    parser_client_status = subparsers_client.add_parser( 'status', help = 'get net status' )

    # client:provision
    parser_client_provision = subparsers_client.add_parser( 'provision', help = 'provision a new client' )
    parser_client_provision.add_argument( 'iid', type = str, help = 'installation key id' )
    parser_client_provision.add_argument( '--name',
                                          nargs = '+',
                                          dest = 'names',
                                          help = 'client name (hostname or email)' )
    parser_client_provision.add_argument( '--name-file',
                                          type = str,
                                          default = None,
                                          dest = 'nameFile',
                                          help = 'file containing newline-separated names to provision' )
    parser_client_provision.add_argument( '--output',
                                          type = str,
                                          default = '-',
                                          dest = 'output',
                                          help = 'output directory where to put new config files, or "-" for stdout' )
    parser_client_provision.add_argument( '--email-user',
                                          action = 'store_true',
                                          default = False,
                                          required = False,
                                          dest = 'isEmail',
                                          help = 'if set, limacharlie will email users creds directly' )
    parser_client_provision.add_argument( '--within-range',
                                          type = str,
                                          default = None,
                                          dest = 'withinRange',
                                          help = 'if specified, this IP CIDR range will be favored when attributing an internal IP address in lc-net' )
    parser_client_provision.add_argument( '--exclude-local-ranges',
                                          type = str,
                                          default = None,
                                          dest = 'excludeLocal',
                                          help = 'by default configs generated for clients route all public IP ranges, this comma separated list of CIDRs describes IP ranges to exclude' )
    parser_client_provision.add_argument( '--dns-servers',
                                          type = str,
                                          default = None,
                                          dest = 'dnsServers',
                                          help = 'by default configs generated for clients use the Google Public DNS servers (8.8.8.8 and 8.8.4.4), this comma separated list of DNS servers overrides it if specified' )

    # client:usage
    parser_client_usage = subparsers_client.add_parser( 'usage', help = 'get client usage information' )
    parser_client_usage.add_argument( '--sid',
                                      type = str,
                                      default = None,
                                      help = 'sensor id of the client to get the usage for, otherwise entire org is reported' )

    # client:policies
    parser_client_policies = subparsers_client.add_parser( 'policies', help = 'get policies that apply to client' )
    parser_client_policies.add_argument( 'sid',
                                         type = str,
                                         help = 'sensor id of the client to get the policies of' )

    # policy
    subparsers_policy = objects[ 'policy' ].add_subparsers( dest = 'action', help = 'action to take' )

    # policy:get
    parser_client_usage = subparsers_policy.add_parser( 'get', help = 'get policies' )

    # policy:set
    parser_client_usage = subparsers_policy.add_parser( 'set', help = 'set policy' )
    parser_client_usage.add_argument( 'name', type = str, help = 'policy name' )
    parser_client_usage.add_argument( 'type', type = str, help = 'policy type' )
    parser_client_usage.add_argument( '--expires-on',
                                      type = int,
                                      default = None,
                                      dest = 'expiresOn',
                                      help = 'optional second epoch when the policy should expire' )
    parser_client_usage.add_argument( '--policy-file',
                                      type = str,
                                      default = None,
                                      dest = 'policyFile',
                                      help = 'path to file with policy content in JSON or YAML format' )
    parser_client_usage.add_argument( '--policy',
                                      type = str,
                                      default = None,
                                      dest = 'policy',
                                      help = 'literal policy content in JSON or YAML format' )

    # policy:delete
    parser_client_usage = subparsers_policy.add_parser( 'delete', help = 'delete policy' )
    parser_client_usage.add_argument( 'name', type = str, help = 'policy name' )

    args = parser.parse_args( sourceArgs )

    if args.object is None:
        parser.print_help()
        sys.exit( 1 )
    if args.action is None:
        objects[ args.object ].print_help()
        sys.exit( 1 )

    def getStatus():
        return Net( Manager() ).getStatus()

    def provisionClient():
        names = []
        if args.nameFile is not None:
            with open( args.nameFile, 'rb' ) as f:
                names = [ name.strip() for name in f.read().decode().split( '\n' ) ]
        else:
            names = args.names
        ret = Net( Manager() ).provision( args.iid, names, isEmailUserDirectly = args.isEmail, withinIPRange = args.withinRange, excludeLocal = args.excludeLocal, dnsServers = args.dnsServers )
        if args.output == '-':
            return ret
        for prov in ret.get( 'provisioned', [] ):
            outPath = os.path.join( args.output, "%s_%s_%s" % ( prov[ 'oid' ], prov[ 'sid' ], prov[ 'sensor'][ 'name' ] ) )
            with open( outPath, 'wb' ) as f:
                f.write( prov[ 'sensor' ][ 'wg_config' ].encode() )
        return {}

    def getClientUsage():
        return Net( Manager() ).getUsage( args.sid )

    def getClientPolicies():
        return Net( Manager() ).getApplicablePolicies( args.sid )

    def getPolicies():
        return Net( Manager() ).getPolicies()

    def setPolicy():
        if args.policy is not None:
            polContent = args.policy
        elif args.policyFile is not None:
            polContent = open( args.policyFile, 'rb' ).read().decode()
        else:
            raise argparse.ArgumentTypeError( '--policy or --policy-file required' )
        pol = None
        if polContent.startswith( '{' ):
            pol = json.loads( polContent )
        else:
            pol = yaml.safe_load( polContent )
        return Net( Manager() ).setPolicy( args.name, args.type, pol, expiresOn = args.expiresOn )

    def delPolicy():
        return Net( Manager() ).delPolicy( args.name )

    result = {
        'client:status' : getStatus,
        'client:provision' : provisionClient,
        'client:usage' : getClientUsage,
        'client:policies' : getClientPolicies,
        'policy:get' : getPolicies,
        'policy:set' : setPolicy,
        'policy:delete' : delPolicy,
    }[ '%s:%s' % ( args.object, args.action ) ]()

    if args.isYaml:
        print( yaml.safe_dump( result, default_flow_style = False ) )
    else:
        print( json.dumps( result, indent = 2 ) )

if __name__ == '__main__':
    main()