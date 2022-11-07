from . import Manager
from .Replay import Replay
import json
import cmd
import pydoc
import os.path
try:
    import readline
except ImportError:
    readline = None

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

    if not args.query:
        LCQuery( replay ).cmdloop()
        return

    response = replay._doQuery( args.query,
                                limitEvent = args.limitEvent,
                                limitEval = args.limitEval,
                                isDryRun = args.isDryRun )

    error = response.get( 'error', None )
    if error:
        print( f"ERROR: {error}" )
        return
    for result in response[ 'results' ]:
        if args.isPretty:
            print( json.dumps( result[ 'data' ], indent = 2 ) )
        else:
            print( json.dumps( result[ 'data' ] ) )

class LCQuery( cmd.Cmd ):
    def __init__( self, replay ):
        self._timeFrame = "-10m"
        self._sensors = "*"
        self._events = "NEW_PROCESS"
        self._limitEvent = 0
        self._limitEval = 0
        self._billed = 0
        self._pricingBlock = 25000
        self._histfile = os.path.expanduser( '~/.limacharlie_history' )
        self._histfile_size = 1000
        self._replay = replay
        super(LCQuery, self).__init__()
        self._setPrompt()

    def preloop( self ):
        if readline and os.path.exists( self._histfile ):
            readline.read_history_file( self._histfile )

    def postloop( self ):
        if readline:
            readline.set_history_length( self._histfile_size )
            readline.write_history_file( self._histfile )

    def default( self, inp ):
        response = self._replay._doQuery( f"{self._timeFrame} | {self._sensors} | {self._events} | {inp}",
                                          limitEvent = self._limitEvent if self._limitEvent else None,
                                          limitEval = self._limitEval if self._limitEval else None )
        error = response.get( 'error', None )
        if error:
            print( f"ERROR: {error}" )
            return
        thisBilled = response.get( 'stats', {} ).get( 'n_billed', 0 )
        self._billed += thisBilled
        print( f"Query cost: ${(thisBilled / self._pricingBlock) / 100}" )
        print( f"{len( response[ 'results' ] )} results" )
        pydoc.pager( "\n".join( json.dumps( d[ 'data' ], indent = 2 ) for d in response[ 'results' ] ) )

    def do_dryrun( self, inp ):
        response = self._replay._doQuery( f"{self._timeFrame} | {self._sensors} | {self._events} | {inp}",
                                          limitEvent = self._limitEvent if self._limitEvent else None,
                                          limitEval = self._limitEval if self._limitEval else None,
                                          isDryRun = True )
        thisBilled = response.get( 'stats', {} ).get( 'n_billed', 0 )
        print( f"Aproximate cost: ${(thisBilled / self._pricingBlock) / 100}" )
        print( json.dumps( response, indent = 2 ) )

    def do_stats( self, inp ):
        print( f"Session cost: ${(self._billed / self._pricingBlock) / 100}" )

    def do_quit( self, inp ):
        self.do_stats( None )
        return True

    def _setPrompt( self ):
        limits = ""
        if self._limitEvent:
            limits += f"limit_event: {self._limitEvent} "
        if self._limitEval:
            limits += f"limit eval: {self._limitEval}"
        self.prompt = f"{self._timeFrame} | {self._sensors} | {self._events} | "

    def do_exit( self, inp ):
        print( "Bye" )
        return True

    def emptyline(self):
         pass

    def do_set_time( self, inp ):
        self._timeFrame = inp
        self._setPrompt()

    def do_set_sensors( self, inp ):
        self._sensors = inp
        self._setPrompt()

    def do_set_events( self, inp ):
        self._events = inp
        self._setPrompt()

    def do_set_limit_event( self, inp ):
        self._limitEvent = int(inp)
        self._setPrompt()

    def do_set_limit_eval( self, inp ):
        self._limitEval = int(inp)
        self._setPrompt()

    def do_env( self, inp ):
        print( f"Current env: time={self._timeFrame} sensors={self._sensors} events={self._events}" )

if '__main__' == __name__:
    main()