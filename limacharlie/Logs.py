from limacharlie import Manager
from .utils import LcApiException
from .utils import GET
from .utils import POST

# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

if _IS_PYTHON_2:
    from urllib2 import HTTPError
    from urllib2 import Request as URLRequest
    from urllib2 import urlopen
    from urlparse import urlparse
else:
    from urllib.error import HTTPError
    from urllib.request import Request as URLRequest
    from urllib.request import urlopen
    from urllib.parse import urlparse

import os
import os.path
import uuid
import base64
import json
import requests
import time
import tempfile

MAX_UPLOAD_PART_SIZE = ( 1024 * 1024 * 15 )

class Logs( object ):
    '''Helper object to upload External Logs to limacharlie.io without going through a sensor.'''

    def __init__( self, manager, accessToken = None ):
        '''Create a Log manager object to prepare for upload.

        Args:
            manager (limacharlie.Manager obj): a Manager to use for identification (NOT authentication since API key is not required for this utility class).
            accessToken (str): an ingestion key to use for log upload.
        '''

        self._lc = manager
        self._accessToken = accessToken

        if self._accessToken is None:
            # Load the token from an environment variable.
            self._accessToken = os.environ.get( 'LC_LOGS_TOKEN', None )

        if self._accessToken is not None:
            self._accessToken = str( uuid.UUID( str( self._accessToken ) ) )
        self._uploadUrl = None

    def upload( self, filePath, source = None, hint = None, payloadId = None, allowMultipart = False, originalPath = None, nDaysRetention = 30 ):
        '''Upload a log.

        Args:
            filePath (str): path to the file to upload.
            source (str): optional source identifier for where the log came from.
            hint (str): optional data format hint for the log.
            payloadId (str): optional unique payload identifier for the log, used to perform idempotent uploads.
            allowMultipart (bool): unused, if True will perform multi-part upload for large logs.
            nDaysRetention (int): number of days the data should be retained in the cloud.
        '''

        if self._accessToken is None:
            raise LcApiException( 'access token not specified' )

        if self._uploadUrl is None:
            # Get the ingest URL from the API.
            self._uploadUrl = self._lc.getOrgURLs()[ 'logs' ]

        headers = {
            'Authorization' : 'Basic %s' % ( base64.b64encode( ( '%s:%s' % ( self._lc._oid, self._accessToken ) ).encode() ).decode(), )
        }

        if source is not None:
            headers[ 'lc-source' ] = source
        if hint is not None:
            headers[ 'lc-hint' ] = hint
        if payloadId is not None:
            headers[ 'lc-payload-id' ] = payloadId
        if originalPath is not None:
            headers[ 'lc-path' ] = base64.b64encode( os.path.abspath( originalPath ).encode() ).decode()
        if nDaysRetention is not None:
            headers[ 'lc-retention-days' ] = str( nDaysRetention )

        with open( filePath, 'rb' ) as f:
            # Get the file size.
            f.seek( 0, 2 )
            fileSize = f.tell()
            f.seek( 0 )

            if MAX_UPLOAD_PART_SIZE > fileSize:
                # Simple single-chunk upload.
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
            else:
                # Multi-part upload.
                partId = 0
                if payloadId is None:
                    headers[ 'lc-payload-id' ] = str( uuid.uuid4() )

                while True:
                    chunk = f.read( MAX_UPLOAD_PART_SIZE )
                    if not chunk:
                        break

                    if len( chunk ) != MAX_UPLOAD_PART_SIZE:
                        headers[ 'lc-part' ] = "done"
                    else:
                        headers[ 'lc-part' ] = str( partId )

                    request = URLRequest( str( 'https://%s/ingest' % ( self._uploadUrl, ) ),
                                          data = chunk,
                                          headers = headers )
                    try:
                        u = urlopen( request )
                    except HTTPError as e:
                        raise Exception( '%s: %s' % ( str( e ), e.read().decode() ) )
                    try:
                        response = json.loads( u.read().decode() )
                    except:
                        response = {}

                    partId += 1

        return response

    def getOriginal( self, payloadId, filePath = None, fileObj = None, optParams = {}, customGetter = None ):
        '''Download an orginal log.

        Args:
            payloadId (str): the payload identifier to download.
            filePath (str): optional path where to download the file to.
            fileObj (file obj): optional file object where to write the log.
        '''

        if optParams is None or 0 == len( optParams ):
            response = self._lc._apiCall( '/insight/%s/logs/originals/%s' % ( self._lc._oid, payloadId ), GET )
        else:
            response = self._lc._apiCall( '/insight/%s/logs/originals/%s' % ( self._lc._oid, payloadId ), POST, params = optParams )

        # If no local output is specified, we interpret this
        # as an asynchronous export request.
        if filePath is None and fileObj is None and ( optParams is None or 0 == len( optParams ) ):
            if 'payload' in response:
                return response[ 'payload' ]
            return response[ 'export' ]

        # Response can either be inline if small enough.
        if 'payload' in response:
            data = self._lc._unwrap( response[ 'payload' ], isRaw = True )
            if filePath is not None:
                with open( filePath, 'wb' ) as f:
                    f.write( data )
            elif fileObj is not None:
                fileObj.write( data )
            response.pop( 'payload', None )
        elif optParams is not None and 0 != len( optParams ) and customGetter is None:
            pass
        # Or it can be a GCS signed URL.
        elif 'export' in response:
            # The export is asynchronous, so we will retry
            # every 5 seconds up to 10 minutes.
            maxWaitTime = 60 * 10
            retryEvery = 5
            if customGetter is not None:
                # A custom getter was provided, so assume it takes care of auth.
                # The export is a path to a GCP blob. Break it down into its parts
                # for code clarity.
                exportInfo = urlparse( response[ 'export' ] )
                bucketName, blobName = exportInfo.path.lstrip( '/' ).split( '/', 1 )
                for _ in range( int( maxWaitTime / retryEvery ) ):
                    # Getter signals it has been successful by returning true-ish.
                    if customGetter( bucketName, blobName, filePath, fileObj ):
                        break
                    time.sleep( retryEvery )
                else:
                    raise LcApiException( "Failed to get artifact." )
            else:
                # We attempt to get the data assuming this is an unauthenticated
                # request like a Signed URL (which is the default provided by LC).
                status = None
                for _ in range( int( maxWaitTime / retryEvery ) ):
                    dataReq = requests.get( response[ 'export' ], stream = True )
                    status = dataReq.status_code
                    if 200 == status:
                        break
                    dataReq.close()
                    dataReq = None
                    if 404 != status:
                        break
                    time.sleep( retryEvery )

                if dataReq is None:
                    raise LcApiException( "Failed to get artifact: %s." % ( status, ) )

                try:
                    if filePath is not None:
                        with open( filePath, 'wb' ) as f:
                            for chunk in dataReq.iter_content( chunk_size = 1024 * 512 ):
                                if not chunk:
                                    continue
                                f.write( chunk )
                    elif fileObj is not None:
                        for chunk in dataReq.iter_content( chunk_size = 1024 * 512 ):
                            if not chunk:
                                continue
                            fileObj.write( chunk )
                    response.pop( 'export', None )
                finally:
                    dataReq.close()

        return response

    def listArtifacts( self, type = None, source = None, originalPath = None, after = None, before = None, withData = False, optParams = {}, customGetter = None ):
        '''Get the list of artifacts matching parameters.

        Args:
            type (str): only list artifacts with type.
            source (str): only list artifacts from this source.
            originalPath (str): only list artifacts with this original path.
            after (int): list artifacts after a given second epoch.
            before (int): list artifacts before a given second epoch.
            withData (bool): if True, artifact will be downloaded inline and the return value will be a tuple (artifactRecord, localFilePath).
        '''

        cursor = '-'
        req = {}

        if after is not None:
            req[ 'start' ] = int( after )
        if before is not None:
            req[ 'end' ] = int( before )

        if type is not None:
            req[ 'hint' ] = type
        if source is not None:
            req[ 'source' ] = source

        while cursor:
            req[ 'cursor' ] = cursor
            data = self._lc._apiCall( 'insight/%s/artifacts' % ( self._lc._oid, ), GET, queryParams = req )
            cursor = data.get( 'next_cursor', None )
            for artifact in data[ 'logs' ]:
                # Right now we filter the path in user-mode since it's
                # not yet supported by the service.
                if originalPath is not None and artifact[ 'path' ] != originalPath:
                    continue
                if not withData:
                    yield artifact
                else:
                    tmpFile = tempfile.NamedTemporaryFile( delete = False )
                    try:
                        artifact = self.getOriginal( artifact[ 'payload_id' ], filePath = tmpFile.name, fileObj = tmpFile, optParams = optParams, customGetter = customGetter )
                        yield ( artifact, tmpFile.name )
                    except:
                        tmpFile.close()
                        os.unlink( tmpFile.name )
                        raise


def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie artifacts' )

    actions = {
        'upload' : main_upload,
        'get_original' : main_getOriginal,
    }

    parser.add_argument( 'artifact_action',
                         type = str,
                         help = 'action to take, one of %s' % ( ', '.join( actions.keys(), ) ) )

    parser.add_argument( 'opt_arg',
                         type = str,
                         nargs = "?",
                         default = None,
                         help = 'optional argument depending on artifact_action' )

    args = parser.parse_args( sourceArgs[ 0 : 1 ] )

    if args.artifact_action not in actions:
        print( "Unknown action: %s" % ( args.artifact_action, ) )
        sys.exit( 1 )

    return actions[ args.artifact_action ]( sourceArgs[ 1 : ] )

def main_upload( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie artifacts upload' )

    parser.add_argument( 'artifact_file',
                         type = str,
                         help = 'path to the artifacts file to upload.' )

    parser.add_argument( '--source',
                         type = str,
                         required = False,
                         dest = 'source',
                         default = None,
                         help = 'name of the source to associate with upload.' )

    parser.add_argument( '--original-path',
                         type = str,
                         required = False,
                         dest = 'originalPath',
                         default = None,
                         help = 'override the original path recorded for the artifacts.' )

    parser.add_argument( '--hint',
                         type = str,
                         required = False,
                         dest = 'hint',
                         default = 'auto',
                         help = 'artifacts type hint of the upload.' )

    parser.add_argument( '--payload-id',
                         type = str,
                         required = False,
                         dest = 'payloadId',
                         default = None,
                         help = 'unique identifier of the artifacts uploaded, can be used to de-duplicate artifacts.' )

    parser.add_argument( '--access-token',
                         type = uuid.UUID,
                         required = False,
                         dest = 'accessToken',
                         default = None,
                         help = 'access token to upload.' )

    parser.add_argument( '--oid',
                         type = lambda o: str( uuid.UUID( o ) ),
                         required = False,
                         dest = 'oid',
                         default = None,
                         help = 'organization id to upload for.' )

    parser.add_argument( '--days-retention',
                         type = int,
                         required = False,
                         dest = 'retention',
                         default = None,
                         help = 'number of days of retention for the data.' )

    args = parser.parse_args( sourceArgs )

    logs = Logs( Manager( args.oid, None, jwt = "" ), args.accessToken )

    originalPath = args.originalPath
    if args.originalPath is None:
        originalPath = args.artifact_file

    response = logs.upload( args.artifact_file,
                            source = args.source,
                            hint = args.hint,
                            payloadId = args.payloadId,
                            allowMultipart = False,
                            originalPath = originalPath,
                            nDaysRetention = args.retention )

    print( json.dumps( response ) )

def main_getOriginal( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie artifacts get_original' )

    parser.add_argument( 'payloadid',
                         type = str,
                         help = 'unique identifier of the artifact uploaded.' )
    parser.add_argument( 'destination',
                         type = str,
                         help = 'file path where to download the artifact.' )

    args = parser.parse_args( sourceArgs )

    logs = Logs( Manager() )

    response = logs.getOriginal( args.payloadid, filePath = args.destination )

    print( json.dumps( response ) )