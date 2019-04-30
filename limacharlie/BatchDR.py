from . import Manager
from .utils import LcApiException

import os
import os.path
import uuid
import urllib2
import base64
import json
import yaml

class BatchDR( object ):
    def __init__( self, manager ):
        self._lc = manager
        self._apiURL = None


    def scanHistoricalSensor( self, sid, startTime, endTime, ruleName = None, ruleContent = None ):
        if self._apiURL is None:
            # Get the ingest URL from the API.
            self._apiURL = 'https://%s/' % ( self._lc.getOrgURLs()[ 'replay' ], )
        req = {
            'start' : startTime,
            'end' : endTime,
            'is_trace' : 'true',
        }
        body = None
        if ruleName is not None:
            req[ 'rule_name' ] = ruleName
        elif ruleContent is not None:
            body = json.dumps( ruleContent )
        else:
            raise LcApiException( 'no rule specified' )

        statusCode, resp = self._lc._restCall( 'sensor/%s/%s' % ( self._lc._oid, sid, ), 
                                               'POST', 
                                               {}, 
                                               altRoot = self._apiURL,
                                               queryParams = req,
                                               rawBody = body,
                                               contentType = 'application/json' )

        if 200 != statusCode:
            raise LcApiException( '%s: %s' % ( statusCode, resp ) )

        return resp

def main():
    import argparse
    import getpass

    parser = argparse.ArgumentParser( prog = 'limacharlie.io replay detection and response' )

    parser.add_argument( '--sid',
                         type = uuid.UUID,
                         required = True,
                         dest = 'sid',
                         default = None,
                         help = 'sensor id to scan traffic from.' )

    parser.add_argument( '--start',
                         type = int,
                         required = True,
                         dest = 'start',
                         default = None,
                         help = 'epoch seconds at which to start scanning sensor traffic.' )

    parser.add_argument( '--end',
                         type = int,
                         required = True,
                         dest = 'end',
                         default = None,
                         help = 'epoch seconds at which to end scanning sensor traffic.' )

    parser.add_argument( '--rule-name',
                         type = str,
                         required = False,
                         dest = 'ruleName',
                         default = None,
                         help = 'name of the an already-existing rule to scan with.' )

    parser.add_argument( '--rule-content',
                         type = str,
                         required = False,
                         dest = 'ruleContent',
                         default = None,
                         help = 'file path where rule to scan is.' )

    args = parser.parse_args()

    batchDr = BatchDR( Manager( None, None ) )

    ruleContent = None
    if args.ruleContent is not None:
        with open( args.ruleContent, 'rb' ) as f:
            ruleContent = f.read()
        try:
            ruleContent = yaml.safe_load( ruleContent )
        except:
            try:
                ruleContent = json.loads( ruleContent )
            except:
                raise LcApiException( 'rule content not valid yaml or json' )

    response = batchDr.scanHistoricalSensor( str( args.sid ), 
                                             args.start, 
                                             args.end,
                                             ruleName = args.ruleName,
                                             ruleContent = ruleContent )

    print( json.dumps( response ) )