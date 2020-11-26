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

import pyqrcode

class Net( object ):
    '''Representation of a limacharlie.io Net.'''

    def __init__( self, manager ):
        self._manager = manager

    def provision( self, iid, name, isEmailUserDirectly = False ):
        '''Provision a new LimaCharlie Net sensor.

        Args:
            iid (str): installation key id to use to provision the sensor.
            name (str): name to give (used as hostname) to sensor, use email address of user if you use isEmailUserDirectly.
            isEmailUserDirectly (bool): if True, LimaCharlie will email the user set as "name" directly with the credentials.
        Returns:
            provisioning information.
        '''
        req = {
            'oid': self._manager._oid,
            'iid': iid,
            'name': name,
            'is_email_to_user': 'true' if isEmailUserDirectly else 'false',
        }
        return self._manager._apiCall( 'net/provision', POST, req, altRoot = ROOT_URL )

def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie net' )
    subparsers = parser.add_subparsers( dest = 'object', help = 'object to work with' )

    objects = {
        'client' : subparsers.add_parser( 'client', help = 'working with clients' ),
    }

    # client
    subparsers_client = objects[ 'client' ].add_subparsers( dest = 'action', help = 'action to take' )

    # client:create
    parser_client_create = subparsers_client.add_parser( 'provision', help = 'provision a new client' )
    parser_client_create.add_argument( 'iid', type = str, help = 'installation key id' )
    parser_client_create.add_argument( 'name', type = str, help = 'client name (hostname or email)' )
    parser_client_create.add_argument( '--is-email-user',
                                       action = 'store_true',
                                       default = False,
                                       required = False,
                                       dest = 'isEmail',
                                       help = 'if set, limacharlie will email users creds directly' )

    args = parser.parse_args( sourceArgs )

    if args.object is None:
        parser.print_help()
        sys.exit( 1 )
    if args.action is None:
        objects[ args.object ].print_help()
        sys.exit( 1 )

    def provisionClient():
        res = Net( Manager() ).provision( args.iid, args.name, isEmailUserDirectly = args.isEmail )
        conf = res.get( 'wg_conf', None )
        if conf is not None:
            print( pyqrcode.create( conf ).terminal() )
        return res

    result = {
        'client:provision' : provisionClient,
    }[ '%s:%s' % ( args.object, args.action ) ]()

    print( json.dumps( result, indent = 2 ) )

if __name__ == '__main__':
    main()