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
    from urllib import quote_plus as urlescape
else:
    from urllib.parse import quote_plus as urlescape

def printData( data ):
    if isinstance( data, str ):
        print( data )
    else:
        print( json.dumps( data, indent = 2 ) )

def reportError( msg ):
    sys.stderr.write( msg + '\n' )
    sys.exit( 1 )

class Hive( object ):
    def __init__( self, man, hiveName, altPartitionKey = None ):
        self._hiveName = hiveName
        self._man = man
        self._partitionKey = altPartitionKey
        if self._partitionKey is None:
            self._partitionKey = self._man._oid

    def list( self ):
        return { recordName : HiveRecord( recordName, record, self ) for recordName, record in self._man._apiCall( 'hive/%s/%s' % ( self._hiveName, self._partitionKey ), GET ).items() }

    def get( self, recordName ):
        return HiveRecord( recordName, self._man._apiCall( 'hive/%s/%s/%s/data' % ( self._hiveName, self._partitionKey, urlescape( recordName ) ), GET ), self )

    def getMetadata( self, recordName ):
        return HiveRecord( recordName, self._man._apiCall( 'hive/%s/%s/%s/mtd' % ( self._hiveName, self._partitionKey, urlescape( recordName ) ), GET ), self )

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

        return self._man._apiCall( 'hive/%s/%s/%s/%s' % ( self._hiveName, self._partitionKey, urlescape( record.name ), target ), POST, req )

    def delete( self, recordName ):
        return self._man._apiCall( 'hive/%s/%s/%s' % ( self._hiveName, self._partitionKey, urlescape( recordName ) ), DELETE )

class HiveRecord( object ):
    def __init__( self, recordName, data, api = None ):
        self._api = api
        self.name = recordName
        self.data = data.get( 'data', None )
        if self.data is not None and not isinstance( self.data, dict ):
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

    def toJSON( self ):
        return {
            'data' : self.data,
            'usr_mtd' : {
                'expiry' : self.expiry,
                'enabled' : self.enabled,
                'tags' : self.tags,
            },
            'sys_mtd' : {
                'created_at' : self.createdAt,
                'created_by' : self.createdBy,
                'guid' : self.guid,
                'last_author' : self.lastAuthor,
                'last_mod' : self.lastModified,
                'last_error' : self.lastError,
                'last_error_ts' : self.lastErrorTime,
            },
        }

    def delete( self ):
        return self._api.delete( self.name )

    def fetch( self ):
        return self._api.get( self.name )

    def update( self, cb = None ):
        # Perform a transactional update of the record
        # by using the "etag" provided by the API to make
        # sure we don't overwrite changes made to the
        # record between a fetch and a set.
        # The cb function will get called with the record
        # and expects a modified record to be returned by
        # it. This may get called more than once with updated
        # records if the transaction hits changes.
        if cb is None:
            cb = lambda x: x
        record = self
        while True:
            record = cb( record )
            if record is None:
                # This is the user indicating update
                # is not needed.
                return None
            try:
                ret = self._api.set( record )
            except Exception as e:
                if 'ETAG_MISMATCH' not in str( e ):
                    raise
                ret = None
            if ret:
                return ret
            record = self.fetch()

def _do_list( args, man ):
    printData( { r.name: r.toJSON() for r in Hive( man, args.hive_name, altPartitionKey = args.partitionKey ).list().values() } )

def _do_list_mtd( args, man ):
    resp = { r.name: r.toJSON() for r in Hive( man, args.hive_name, altPartitionKey = args.partitionKey ).list().values() }
    for k, r in resp.items():
        r[ 'data' ] = None
    printData( resp )

def _do_get( args, man ):
    if args.key is None:
        reportError( 'Key required' )

    printData( Hive( man, args.hive_name, altPartitionKey = args.partitionKey ).get( args.key ).toJSON() )

def _do_get_mtd( args, man ):
    if args.key is None:
        reportError( 'Key required' )

    printData( Hive( man, args.hive_name, altPartitionKey = args.partitionKey ).getMetadata( args.key ).toJSON() )

def _do_add( args, man ):
    if args.key is None:
        reportError( 'Key required' )

    record = {
        'data' : None,
    }

    if args.data is not None:
        data = open( args.data, 'rb' ).read().decode()
        data = json.loads( data )
        record[ 'data' ] = data

    usrMtd = {}
    if args.expiry is not None:
        usrMtd[ 'expiry' ] = args.expiry
    if args.enabled is not None:
        usrMtd[ 'enabled' ] = args.enabled.lower() not in ( '0', 'false', 'no', 'off' )
    if args.tags is not None:
        usrMtd[ 'tags' ] = [ t.strip() for t in args.tags.split( ',' ) ]
    record[ 'usr_mtd' ] = usrMtd

    sysMtd = {}
    if args.etag is not None:
        sysMtd[ 'etag' ] = args.etag
    record[ 'sys_mtd' ] = sysMtd

    printData( Hive( man, args.hive_name, altPartitionKey = args.partitionKey ).set( HiveRecord( args.key, record ) ) )

def _do_update( args, man ):
    if args.key is None:
        reportError( 'Key required' )

    _do_add( args, man )

def _do_remove( args, man ):
    if args.key is None:
        reportError( 'Key required' )

    printData( Hive( man, args.hive_name, altPartitionKey = args.partitionKey ).delete( args.key ) )

def main( sourceArgs = None ):
    import argparse

    actions = {
        'list' : _do_list,
        'list_mtd' : _do_list_mtd,
        'get' : _do_get,
        'get_mtd' : _do_get_mtd,
        'set' : _do_add,
        'update' : _do_update,
        'remove' : _do_remove,
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