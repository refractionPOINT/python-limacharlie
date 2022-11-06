from . import Manager
from .Replay import Replay
import json


def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie query' )

    parser.add_argument( '--query',
                         type = str,
                         required = False,
                         dest = 'query',
                         default = None,
                         help = 'query to issue.' )

    parser.add_argument( '--limit-event',
                         type = int,
                         required = False,
                         dest = 'limitEvent',
                         default = None,
                         help = 'limits the number of events evaluated to approximately this number.' )

    parser.add_argument( '--limit-eval',
                         type = int,
                         required = False,
                         dest = 'limitEval',
                         default = None,
                         help = 'limits the number of rule evaluations to approximately this number.' )

    parser.add_argument( '--dry-run',
                         action = 'store_true',
                         default = None,
                         required = False,
                         dest = 'isDryRun',
                         help = 'if set, the request will be simulated and the maximum number of evaluations expected will be returned.' )

    parser.add_argument( '--pretty',
                         action = 'store_true',
                         default = None,
                         required = False,
                         dest = 'isPretty',
                         help = 'print json in pretty format.' )

    args = parser.parse_args( sourceArgs )

    replay = Replay( Manager() )

    response = replay._doQuery( args.query,
                                limitEvent = args.limitEvent,
                                limitEval = args.limitEval,
                                isDryRun = args.isDryRun )

    for result in response[ 'results' ]:
        if args.isPretty:
            print( json.dumps( result[ 'data' ], indent = 2 ) )
        else:
            print( json.dumps( result[ 'data' ] ) )

if '__main__' == __name__:
    main()