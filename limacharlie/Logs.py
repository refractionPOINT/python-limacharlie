# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

if _IS_PYTHON_2:
    from urllib.error import HTTPError
    from urllib.request import Request as URLRequest
    from urllib.request import urlopen
else:
    from urllib.error import HTTPError
    from urllib.request import Request as URLRequest
    from urllib.request import urlopen

from . import Manager

import os
import os.path
import uuid
import base64
import json

class Logs( object ):
    def __init__( self, manager, accessToken = None ):
        self._lc = manager
        self._accessToken = accessToken

        if self._accessToken is None:
            # Load the token from an environment variable.
            self._accessToken = os.environ[ 'LC_LOGS_TOKEN' ]

        self._accessToken = str( uuid.UUID( str( self._accessToken ) ) )
        self._uploadUrl = None

    def upload( self, filePath, source = None, hint = None, payloadId = None, allowMultipart = False, originalPath = None ):
        if self._uploadUrl is None:
            # Get the ingest URL from the API.
            self._uploadUrl = self._lc.getOrgURLs()[ 'logs' ]

        headers = {
            'Authorization' : 'Basic %s' % ( base64.b64encode( '%s:%s' % ( self._lc._oid, self._accessToken ) ), )
        }

        if source is not None:
            headers[ 'lc-source' ] = source
        if hint is not None:
            headers[ 'lc-hint' ] = hint
        if payloadId is not None:
            headers[ 'lc-payload-id' ] = payloadId
        if originalPath is not None:
            headers[ 'lc-path' ] = base64.b64encode( os.path.abspath( originalPath ) )

        with open( filePath, 'rb' ) as f:
            request = URLRequest( str( 'https://%s/ingest' % ( self._uploadUrl, ) ),
                                  data = f.read(),
                                  headers = headers )
        try:
            u = urlopen( request )
        except HTTPError as e:
            raise Exception( '%s: %s' % ( str( e ), e.read().decode() ) )
        try:
            response = json.loads( u.read().decode() )
        except:
            response = {}
        return response

def main():
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie.io logs' )

    parser.add_argument( 'log_file',
                         type = str,
                         help = 'path to the log file to upload.' )

    parser.add_argument( '--source',
                         type = str,
                         required = False,
                         dest = 'source',
                         default = None,
                         help = 'name of the log source to associate with upload.' )

    parser.add_argument( '--original-path',
                         type = str,
                         required = False,
                         dest = 'originalPath',
                         default = None,
                         help = 'override the original path recorded for the log.' )

    parser.add_argument( '--hint',
                         type = str,
                         required = False,
                         dest = 'hint',
                         default = 'txt',
                         help = 'log type hint of the upload.' )

    parser.add_argument( '--payload-id',
                         type = str,
                         required = False,
                         dest = 'payloadId',
                         default = None,
                         help = 'unique identifier of the log uploaded, can be used to de-duplicate logs.' )

    parser.add_argument( '--access-token',
                         type = uuid.UUID,
                         required = False,
                         dest = 'accessToken',
                         default = None,
                         help = 'access token to upload.' )

    args = parser.parse_args()

    logs = Logs( Manager( None, None ), args.accessToken )

    originalPath = args.originalPath
    if args.originalPath is None:
        originalPath = args.log_file

    response = logs.upload( args.log_file,
                            source = args.source,
                            hint = args.hint,
                            payloadId = args.payloadId,
                            allowMultipart = False,
                            originalPath = originalPath )

    print( json.dumps( response ) )