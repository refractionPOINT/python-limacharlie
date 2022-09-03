from limacharlie import Manager

# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

if _IS_PYTHON_2:
    from Queue import Queue
else:
    from queue import Queue

import threading
import os.path
import yaml
import traceback
import functools

validIOCs = (
    'file_hash',
    'file_name',
    'file_path',
    'ip', 
    'domain',
    'user',
    'service_name',
)

class Search( object ):
    '''Helper object to perform cross-organization IOC searches.'''

    def __init__( self, environments = None, output = '-' ):
        '''Create a Search object specifying which environments to search.

        Args:
            environments (list of str): optional list of specific environment names to search.
            output (str): optional file path where to output results.
        '''

        self._environmentsToQuery = {}
        with open( os.path.expanduser( '~/.limacharlie' ), 'rb' ) as f:
            conf = yaml.safe_load( f.read().decode() )
            if 'oid' in conf and 'api_key' in conf and conf.get( 'env', {} ).get( 'default', None ) is None:
                conf.setdefault( 'env', {} )[ 'default' ] = {
                    'oid' : conf[ 'oid' ],
                    'api_key' : conf[ 'api_key' ]
                }
            if 0 != len( environments ):
                for envName in environments:
                    envConf = conf.get( 'env', {} ).get( envName, None )
                    if envConf is None:
                        raise Exception( 'environment %s not found' % ( envName, ) )
                    self._environmentsToQuery[ envName ] = envConf
            else:
                self._environmentsToQuery = conf.get( 'env', {} )
                if 'oid' in conf and 'api_key' in conf:
                    self._environmentsToQuery[ 'default' ] = {
                        'oid' : conf[ 'oid' ],
                        'api_key' : conf[ 'api_key' ]
                    }

        if '-' == output:
            self._output = None
        else:
            self._output = open( output, 'wb' )

        self._mutex = threading.Lock()

    def getNumEnvironments( self ):
        return len( self._environmentsToQuery )

    def query( self, iocType, iocName, info, isCaseInsensitive = False, isWithWildcards = False, limit = None, isPerIoc = False ):
        '''Performa a search.

        Args:
            iocType (str): type of IOC to search for.
            iocName (str): name of the IOC to search for.
            info (str): information type to retrieve.
            isCaseInsensitive (bool): if True, search for IOC in a case insensitive way.
            isWithWildcards (bool): if True, use "%" as a wildcard in the IOC name.
            limit (int): optional maximum number of sensors/logs to report about, otherwise defaults to internal LimaCharlie limit.
            isPerIoc (bool): if the search has wildcards, return results grouped per individual ioc.

        Returns:
            Dict of requested information.
        '''

        threads = []

        results = Queue()

        for envName, env in self._environmentsToQuery.items():
            t = threading.Thread( target = self._queryThread, args = ( results, envName, env, iocType, iocName, info, isCaseInsensitive, isWithWildcards, limit, isPerIoc ) )
            threads.append( t )
            t.start()

        for t in threads:
            t.join( timeout = 60 )

        outputs = []
        while True:
            try:
                outputs.append( results.get_nowait() )
            except:
                break

        if self._output is None:
            for result in outputs:
                self._safePrint( "\n%s (%s)\n=========================================\n%s" % ( result[ 'env' ], result[ 'oid' ], yaml.safe_dump( result[ 'result' ], default_flow_style = False ) ) )
        else:
            self._output.write( yaml.safe_dump( outputs, default_flow_style = False ).encode() )

        self._safePrint( "Done, %s results." % ( functools.reduce( lambda x, y: x + ( len( y[ 'result' ] ) if info != 'summary' else 1 ), outputs, 0 ) ) )

    def _queryThread( self, results, envName, env, iocType, iocName, info, isCaseInsensitive, isWithWildcards, limit, isPerIoc ):
        try:
            # If using a user API key, pass the uid parameter from the env var
            try:
                lc = Manager( env[ 'oid' ], env[ 'api_key' ], uid=env['uid'] )
            except:
                lc = Manager( env[ 'oid' ], env[ 'api_key' ] )
                
            try:
                isInsightEnabled = lc.isInsightEnabled()
            except:
                isInsightEnabled = False
            if not isInsightEnabled:
                self._safePrint( "Skipping %s (%s) as Insight is not enabled." % ( envName, env[ 'oid' ], ) )
                return

            result = lc.getObjectInformation(
                iocType,
                iocName,
                info,
                isCaseSensitive = not isCaseInsensitive,
                isWithWildcards = isWithWildcards,
                limit = limit,
                isPerObject = isPerIoc
            )

            if result and 0 != len( result ):
                results.put( { 'env' : envName, 'oid' : env[ 'oid' ], 'result' : result } )
        except:
            self._safePrint( traceback.format_exc() )

    def _safePrint( self, msg ):
        with self._mutex:
            print( msg )

def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie search' )
    parser.add_argument( '-t', '--type',
                         type = str,
                         required = True,
                         dest = 'type',
                         help = 'the IOC type to search for, one of: %s.' % ( ", ".join( validIOCs ) ) )

    parser.add_argument( '-o', '--ioc',
                         type = str,
                         required = True,
                         dest = 'ioc',
                         help = 'the value of the IOC to search for' )

    parser.add_argument( '-i', '--info',
                         type = str,
                         required = False,
                         dest = 'info',
                         default = 'summary',
                         help = 'the type of information to return, one of "summary" or "locations", "summary" is default.' )

    parser.add_argument( '--case-insensitive',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'is_case_insensitive',
                         help = 'make the search case insensitive.' )

    parser.add_argument( '--with-wildcards',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'is_with_wildcards',
                         help = 'make the search using the "%%" wildcard.' )

    parser.add_argument( '-e', '--environments',
                         type = str,
                         required = False,
                         dest = 'environments',
                         default = [],
                         nargs = '*',
                         help = 'the name of the LimaCharlie environments (as defined in ~/.limacharlie) to use, otherwise all environments are used.' )

    parser.add_argument( '--output',
                         type = str,
                         required = False,
                         dest = 'output',
                         default = '-',
                         help = 'location where to send output, "-" by default outputs human readable to stdout, otherwise it should be a file where YAML will be written to.' )

    parser.add_argument( '-l', '--limit',
                         type = int,
                         required = False,
                         dest = 'limit',
                         help = 'optional maximum number of sensors/logs to report about, otherwise defaults to internal LimaCharlie limit.' )

    parser.add_argument( '--per-ioc',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'is_per_ioc',
                         help = 'if the search has wildcards, return results grouped per individual ioc.' )

    args = parser.parse_args( sourceArgs )

    search = Search( environments = args.environments, output = args.output )

    print( "Querying %s environments for %s (%s) to %s." % ( search.getNumEnvironments(), args.ioc, args.type, args.output ) )

    _ = search.query(
        args.type,
        args.ioc,
        args.info,
        isCaseInsensitive = args.is_case_insensitive,
        isWithWildcards = args.is_with_wildcards,
        limit = args.limit,
        isPerIoc = args.is_per_ioc,
    )