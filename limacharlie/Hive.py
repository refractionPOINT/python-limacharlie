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

class Hive( object ):
    def __init__( self, man, hiveName ):
        self._hiveName = hiveName
        self._man = man

    def list( self ):
        return { recordName : HiveRecord( recordName, record, self ) for recordName, record in self._man._apiCall( 'hive/%s/%s' % ( self._hiveName, self._man._oid ), GET ).items() }

    def get( self, recordName ):
        return HiveRecord( recordName, self._man._apiCall( 'hive/%s/%s/%s/data' % ( self._hiveName, self._man._oid, urlescape( recordName ) ), GET ), self )

    def getMetadata( self, recordName ):
        return HiveRecord( recordName, self._man._apiCall( 'hive/%s/%s/%s/mtd' % ( self._hiveName, self._man._oid, urlescape( recordName ) ), GET ), self )

    def set( self, record ):
        target = 'mtd'

        data = None
        if record.data is not None:
            target = 'data'

        usrMtd = {}
        if record.expiry is not None:
            usrMtd[ 'expiry' ] = record.expiry
        if record.enabled is not None:
            usrMtd[ 'enabled' ] = record.enabled
        if record.tags is not None:
            usrMtd[ 'tags' ] = record.tags

        req = {
            'data' : json.dumps( record.data ),
        }

        if record.etag is not None:
            req[ 'etag' ] = record.etag
        if len( usrMtd ) != 0:
            req[ 'usr_mtd' ] = json.dumps( usrMtd )

        return self._man._apiCall( 'hive/%s/%s/%s/%s' % ( self._hiveName, self._man._oid, urlescape( record.name ), target ), POST, req )

    def delete( self, recordName ):
        return self._man._apiCall( 'hive/%s/%s/%s' % ( self._hiveName, self._man._oid, urlescape( recordName ) ), DELETE )

class HiveRecord( object ):
    def __init__( self, recordName, data, api = None ):
        self._api = api
        self.name = recordName
        self.data = data.get( 'data', None )
        if not isinstance( self.data, dict ):
            self.data = json.loads( self.data )
        self.expiry = data.get( 'usr_mtd', {} ).get( 'expiry', None )
        self.enabled = data.get( 'usr_mtd', {} ).get( 'enabled', None )
        self.tags = data.get( 'usr_mtd', {} ).get( 'tags', None )
        self.etag = data.get( 'sys_mtd', {} ).get( 'etag', None )
        self.createdAt = data.get( 'sys_mtd', {} ).get( 'created_at', None )
        self.createdBy = data.get( 'sys_mtd', {} ).get( 'created_by', None )
        self.guid = data.get( 'sys_mtd', {} ).get( 'guid', None )
        self.lastAuthor = data.get( 'sys_mtd', {} ).get( 'last_author', None )
        self.lastModified = data.get( 'sys_mtd', {} ).get( 'last_mod', None )
        self.lastError = data.get( 'sys_mtd', {} ).get( 'last_error', None )
        self.lastErrorTime = data.get( 'sys_mtd', {} ).get( 'last_error_ts', None )

    def delete( self ):
        return self._api.delete( self.name )

    def fetch( self ):
        return self._api.get( self.name )

    def update( self, cb = None ):
        if cb is None:
            cb = lambda x: x
        record = self
        while True:
            record = cb( record )
            try:
                ret = self._api.set( record )
            except Exception as e:
                if 'ETAG_MISMATCH' not in str( e ):
                    raise
                ret = None
            if ret:
                return ret
            record = self.fetch()

def do_list( args, man, isPrint = True ):
    resp = man._apiCall( 'hive/%s/%s' % ( args.hive_name, args.partitionKey ), GET )
    if isPrint:
        printData( resp )
    return resp

def do_list_mtd( args, man, isPrint = True ):
    resp = man._apiCall( 'hive/%s/%s' % ( args.hive_name, args.partitionKey ), GET )
    if isPrint:
        for k, r in resp.items():
            r[ 'data' ] = None
        printData( resp )
    return resp

def do_get( args, man, isPrint = True ):
    if args.key is None:
        reportError( 'Key required' )

    resp = man._apiCall( 'hive/%s/%s/%s/data' % ( args.hive_name, args.partitionKey, urlescape( args.key ) ), GET )
    if isPrint:
        printData( resp )
    return resp

def do_get_mtd( args, man, isPrint = True ):
    if args.key is None:
        reportError( 'Key required' )

    resp = man._apiCall( 'hive/%s/%s/%s/mtd' % ( args.hive_name, args.partitionKey, urlescape( args.key ) ), GET )
    if isPrint:
        printData( resp )
    return resp

def do_add( args, man, isPrint = True ):
    if args.key is None:
        reportError( 'Key required' )

    target = 'mtd'

    data = None
    if args.data is not None:
        data = open( args.data, 'rb' ).read().decode()
        data = json.loads( data )
        target = 'data'

    usrMtd = {}
    if args.expiry is not None:
        usrMtd[ 'expiry' ] = args.expiry
    if args.enabled is not None:
        usrMtd[ 'enabled' ] = args.enabled.lower() not in ( '0', 'false', 'no', 'off' )
    if args.tags is not None:
        usrMtd[ 'tags' ] = [ t.strip() for t in args.tags.split( ',' ) ]

    req = {
        'data' : json.dumps( data ),
    }

    if args.etag is not None:
        req[ 'etag' ] = args.etag
    if len( usrMtd ) != 0:
        req[ 'usr_mtd' ] = json.dumps( usrMtd )

    resp = man._apiCall( 'hive/%s/%s/%s/%s' % ( args.hive_name, args.partitionKey, urlescape( args.key ), target ), POST, req )
    if isPrint:
        printData( resp )
    return resp

def do_update( args, man, isPrint = True ):
    if args.key is None:
        reportError( 'Key required' )

    target = 'mtd'

    data = None
    if args.data is not None:
        data = open( args.data, 'rb' ).read().decode()
        data = json.loads( data )
        target = 'data'
        existing = do_get( args, man, isPrint = False )
        existing[ 'data' ] = json.dumps( data )
    else:
        existing = do_get_mtd( args, man, isPrint = False )
        existing.pop( 'data', None )
        existing[ 'etag' ] = existing[ 'sys_mtd' ].pop( 'etag' )
        existing.pop( 'sys_mtd', None )

    if args.expiry is not None:
        existing[ 'usr_mtd' ][ 'expiry' ] = args.expiry
    if args.enabled is not None:
        existing[ 'usr_mtd' ][ 'enabled' ] = args.enabled.lower() not in ( '0', 'false', 'no', 'off' )
    if args.tags is not None:
        existing[ 'usr_mtd' ][ 'tags' ] = [ t.strip() for t in args.tags.split( ',' ) ]

    existing[ 'usr_mtd' ] = json.dumps( existing[ 'usr_mtd' ] )

    resp = man._apiCall( 'hive/%s/%s/%s/%s' % ( args.hive_name, args.partitionKey, urlescape( args.key ), target ), POST, existing )
    if isPrint:
        printData( resp )
    return resp

def do_remove( args, man, isPrint = True ):
    if args.key is None:
        reportError( 'Key required' )

    resp = man._apiCall( 'hive/%s/%s/%s' % ( args.hive_name, args.partitionKey, urlescape( args.key ) ), DELETE )
    if isPrint:
        printData( resp )
    return resp

def main( sourceArgs = None ):
    import argparse

    actions = {
        'list' : do_list,
        'list_mtd' : do_list_mtd,
        'get' : do_get,
        'get_mtd' : do_get_mtd,
        'set' : do_add,
        'update' : do_update,
        'remove' : do_remove,
    }

    parser = argparse.ArgumentParser( prog = 'limacharlie hive' )
    parser.add_argument( 'action',
                         type = str,
                         help = 'the action to take, one of: %s' % ( ', '.join( actions.keys(), ) ) )
    
    parser.add_argument( 'hive_name',
                         type = str,
                         help = 'the hive name' )

    parser.add_argument( '-k', '--key',
                         type = str,
                         required = False,
                         dest = 'key',
                         default = None,
                         help = 'the name of the key.' )

    parser.add_argument( '-d', '--data',
                         default = None,
                         required = False,
                         dest = 'data',
                         help = 'the JSON data for the record.' )

    parser.add_argument( '-pk', '--partition-key',
                         default = None,
                         required = False,
                         dest = 'partitionKey',
                         help = 'the partition key to use instead of the default OID.' )

    parser.add_argument( '--etag',
                         default = None,
                         required = False,
                         dest = 'etag',
                         help = 'the optional previous etag expected for transactions.' )

    parser.add_argument( '--expiry',
                         default = None,
                         required = False,
                         type = int,
                         dest = 'expiry',
                         help = 'a millisecond epoch timestamp when the record should expire.' )

    parser.add_argument( '--enabled',
                         default = None,
                         required = False,
                         dest = 'enabled',
                         help = 'whether the record is enabled or disabled.' )

    parser.add_argument( '--tags',
                         default = None,
                         required = False,
                         dest = 'tags',
                         help = 'comma separated list of tags.' )

    args = parser.parse_args( sourceArgs )

    man = Manager( None, None )
    if args.partitionKey is None:
        args.partitionKey = man._oid
    actions[ args.action.lower() ]( args, man )

if '__main__' == __name__:
    main()