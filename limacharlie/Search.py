from limacharlie import Manager

import gevent
import gevent.pool
import gevent.lock
import gevent.queue
import os.path
import yaml
import traceback

validIOCs = ( 'file_hash', 'file_name', 'file_path', 'ip', 'domain', 'user' )

class Search( object ):
    def __init__( self, environment = None, output = '-' ):
        self._environmentsToQuery = {}
        with open( os.path.expanduser( '~/.limacharlie' ), 'rb' ) as f:
            conf = yaml.load( f.read().decode() )
            if environment is not None:
                conf = conf.get( 'env', {} ).get( environment, None )
                if conf is None:
                    raise Exception( 'environment %s not found' % ( environment, ) )
                self._environmentsToQuery[ environment ] = conf
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

        self._mutex = gevent.lock.BoundedSemaphore()

    def getNumEnvironments( self ):
        return len( self._environmentsToQuery )

    def query( self, iocType, iocName, info, isCaseInsensitive = False, isWithWildcards = False ):
        threads = gevent.pool.Group()

        results = gevent.queue.Queue()

        for envName, env in self._environmentsToQuery.items():
            threads.add( gevent.spawn_later( 0, self._queryThread, results, envName, env, iocType, iocName, info, isCaseInsensitive, isWithWildcards ) )

        threads.join( timeout = 60 )

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
            self._output.write( yaml.safe_dump( outputs, default_flow_style = False ) )

        self._safePrint( "Done, %s results." % ( reduce( lambda x, y: x + ( len( y[ 'result' ] ) if info != 'summary' else 1 ), outputs, 0 ) ) )

    def _queryThread( self, results, envName, env, iocType, iocName, info, isCaseInsensitive, isWithWildcards ):
        try:
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
                isWithWildcards = isWithWildcards
            )

            if result and 0 != len( result ):
                results.put( { 'env' : envName, 'oid' : env[ 'oid' ], 'result' : result } )
        except:
            self._safePrint( traceback.format_exc() )

    def _safePrint( self, msg ):
        with self._mutex:
            print( msg )

def main():
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie.io search' )
    parser.add_argument( '-t', '--type',
                         type = str,
                         required = True,
                         dest = 'type',
                         help = 'the IOC type to search for, one of: %s.' % ( ", ".join( validIOCs ) ) )

    parser.add_argument( '-o', '--ioc',
                         type = str,
                         required = True,
                         dest = 'ioc',
                         help = 'the valid of the IOC to search for' )

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

    parser.add_argument( '-e', '--environment',
                         type = str,
                         required = False,
                         dest = 'environment',
                         default = None,
                         help = 'the name of the LimaCharlie environment (as defined in ~/.limacharlie) to use, otherwise all environments are used.' )

    parser.add_argument( '--output',
                         type = str,
                         required = False,
                         dest = 'output',
                         default = '-',
                         help = 'location where to send output, "-" by default outputs human readable to stdout, otherwise it should be a file where YAML will be written to.' )

    args = parser.parse_args()

    search = Search( environment = args.environment, output = args.output )

    print( "Querying %s environments for %s (%s) to %s." % ( search.getNumEnvironments(), args.ioc, args.type, args.output ) )

    results = search.query(
        args.type,
        args.ioc,
        args.info,
        isCaseInsensitive = args.is_case_insensitive,
        isWithWildcards = args.is_with_wildcards
    )