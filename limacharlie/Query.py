from functools import cache
from functools import wraps
from . import Manager
from .Replay import Replay
import cmd
import atexit
import sys
import shutil
import json
from collections import OrderedDict
try:
    import pydoc
except:
    pydoc = None
from tabulate import tabulate
from termcolor import colored
import os.path
try:
    import readline
except ImportError:
    readline = None

from .utils import Spinner
from .term_utils import prettyFormatDict
from .term_utils import printFacets, printHistogram


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
                         help = 'print json in pretty format (in single-query mode).' )

    parser.add_argument( '--format',
                         type = str,
                         default = 'table',
                         required = False,
                         dest = 'format',
                         help = 'print format for interactive mode.' )

    parser.add_argument( '--out-file',
                         type = str,
                         default = None,
                         required = False,
                         dest = 'outFile',
                         help = 'in interactive mode, output log to this file.' )

    parser.add_argument( '--force-replay-url',
                         default = None,
                         required = False,
                         dest = 'forceReplayUrl',
                         help = 'force use a specific replay instance url' )

    parser.add_argument( '--labs',
                         action = 'store_true',
                         default = None,
                         required = False,
                         dest = 'enableLabs',
                         help = 'enable labs / experimental features.' )


    args = parser.parse_args( sourceArgs )

    replay = Replay( Manager() )

    if not args.query:
        LCQuery( replay, args.format, args.outFile ).cmdloop()
        return

    if args.forceReplayUrl:
        print("Using Replay URL: %s" % ( args.forceReplayUrl, ) )

    response = replay._doQuery( args.query,
                                limitEvent = args.limitEvent,
                                limitEval = args.limitEval,
                                isDryRun = args.isDryRun,
                                isCursorBased = False,
                                includeStats = args.enableLabs,
                                forceUrl = args.forceReplayUrl,
                )

    error = response.get( 'error', None )
    if error:
        print( "ERROR: %s" % ( error, ) )
        return
    if not response[ 'results' ]:
        print( f"No results found matching query: {args.query}" )
        return

    histogram = response.get("histogram")
    facets = response.get("facets")

    if args.enableLabs and histogram:
        printHistogram(histogram)
        print("")

    if args.enableLabs and facets:
        printFacets(facets)

    for result in response[ 'results' ]:
        if args.isPretty:
            print(prettyFormatDict(result[ 'data' ]))
        else:
            print( json.dumps( result[ 'data' ] ) )


def requireIntValue(command_name: str):
    """
    Decorator which can be wrapped around do_set_xxx functions which require interger values.

    It ensures the provided input is an integer, otherwise it logs an error.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, inp, *args, **kwargs):
            if inp is None:
                print(f"Error: {command_name} requires an integer value.", file=sys.stderr)
                return None
            try:
                inp = int(inp)
            except ValueError:
                print(f"Error: {command_name} requires an integer value.", file=sys.stderr)
                return None
            return func(self, inp, *args, **kwargs)
        return wrapper
    return decorator


class LCQuery( cmd.Cmd ):
    def __init__( self, replay, format, outFile ):
        self.intro = 'This LimaCharlie feature is in Beta, LCQL is likely going to evolve!\nThe LimaCharlie Query allows you to query the dataset in a more free-form fashion based on the LC Query Language.'
        self._timeFrame = "-10m"
        self._sensors = "*"
        self._events = "*"
        self._stream = 'event'
        self._limitEvent = 0
        self._limitEval = 0
        self._billed = 0
        self._pricingBlock = 200000
        self._histfile = os.path.expanduser( '~/.limacharlie_history' )
        self._histfile_size = 1000
        self._outFile = outFile
        self._replay = replay
        self._format = format
        self._lastData = None
        self._lastQuery = None
        self._lastStats = None
        self._lastRule = None
        self._schema = set()
        self._allEvents = []
        self._q = None
        readline.set_completer_delims( ' ' )
        super(LCQuery, self).__init__()
        self._getAllEvents()
        self._populateSchema()
        self._setPrompt()

        # Ensure it's called even if user exist with CTRL+C and similar - as such, we use atexit
        # handler instead of postloop which is only called on quit command.
        atexit.register(self.saveHistory)

    def preloop( self ):
        if readline and os.path.exists( self._histfile ):
            readline.read_history_file( self._histfile )

    def saveHistory( self ):
        """
        Save interactive prompt history to a history file on disk.
        """
        if readline:
            readline.set_history_length( self._histfile_size )
            readline.write_history_file( self._histfile )
            # Ensure secure permissions, there is a small race, but we can fix this later
            os.chmod(self._histfile, 0o600)

    def precmd( self, inp ):
        self._logOutput( inp, isNoPrint = True )
        return inp

    def _logOutput( self, output, isNoPrint = False ):
        if not isNoPrint:
            print( output )
        if not self._outFile:
            return
        with open( self._outFile, 'a' ) as f:
            f.write( output )
            f.write( "\n" )

    def do_q( self, inp, isCursorBased = True ):
        '''Query (paged).'''
        thisQuery = "%s | %s | %s | %s" % ( self._timeFrame, self._sensors, self._events, inp )
        cacheKey = "%s%s%s" % ( self._limitEval, self._limitEvent, thisQuery )

        q = None
        isFromCache = False

        # Check if the is the same last query we did, if so, re-use the result.
        if cacheKey == self._lastQuery:
            self._logOutput( f"{len( self._lastData )} results from cache" )
            toRender = self._lastData
            isFromCache = True
        else:
            sys.stdout.write( colored("Query running ", 'cyan') )
            if isCursorBased:
                q = self._replay._doQuery( thisQuery,
                                           limitEvent = self._limitEvent if self._limitEvent else None,
                                           limitEval = self._limitEval if self._limitEval else None,
                                           isCursorBased = isCursorBased,
                                           stream = self._stream )
                with Spinner():
                    response = q.next()
                    error = response.get( 'error', None )
                    if error:
                        self._logOutput( f"ERROR: {error}" )
                        return
            else:
                with Spinner():
                    response = self._replay._doQuery( thisQuery,
                                                      limitEvent = self._limitEvent if self._limitEvent else None,
                                                      limitEval = self._limitEval if self._limitEval else None,
                                                      isCursorBased = isCursorBased,
                                                      stream = self._stream )
                    error = response.get( 'error', None )
                    if error:
                        self._logOutput( f"ERROR: {error}" )
                        return

            print( "" )
            thisBilled = response.get( 'stats', {} ).get( 'n_billed', 0 )
            self._lastStats = response.get( 'stats', {} )
            self._lastRule = response.get( 'transcoded_rule', None )
            self._billed += thisBilled
            self._logOutput( f"Query cost: ${(thisBilled / self._pricingBlock) / 100}" )
            self._logOutput( f"{len( response[ 'results' ] )} results" )

            self._lastData = tuple( d[ 'data' ] for d in response[ 'results' ] )
            self._lastQuery = cacheKey
            toRender = self._lastData

        if len( toRender ) != 0:
            self._outputPage( toRender )

        if q is not None and q.hasMore:
            print( "...query has more pages, use 'n' to get the next page" )
            self._q = q
        elif not isFromCache:
            self._q = None

    def do_qa( self, inp ):
        '''Query All (non-paged).'''
        return self.do_q( inp, isCursorBased = False )
    def complete_qa( self, text, line, begidx, endidx ):
        return self.complete_q( text, line, begidx, endidx )

    def complete_q( self, text, line, begidx, endidx ):
        pathToComplete = line.split()[ -1 ]
        results = []
        for evt in self._schema:
            if not evt.startswith( pathToComplete ):
                continue
            results.append( evt )
        return results

    def _outputPage( self, toRender ):
        if self._format == 'json':
            if pydoc is None:
                self._logOutput( "\n".join( json.dumps( d, indent = 2 ) for d in toRender ) )
            else:
                dat = "\n".join( json.dumps( d, indent = 2 ) for d in toRender )
                self._logOutput( dat, isNoPrint = True )
                pydoc.pager( dat )
        elif self._format == 'table':
            if pydoc is None:
                self._logOutput( self._renderTable( toRender ) )
            else:
                # Ensure ANSI escape codes are preserved by setting the pager appropriately.
                if shutil.which('less') and not os.environ.get('PAGER'):
                    os.environ['PAGER'] = 'less -R'
                dat = self._renderTable( toRender )
                self._logOutput( dat, isNoPrint = True )
                pydoc.pager( dat )
        else:
            self._logOutput( 'unknown format' )

    def _renderTable( self, elem ):
        data = []

        for event in elem:
            # Ensure ts, routing, event ctable column ordering for events
            is_event = "ts" in event and "routing" in event and "event" in event

            item = OrderedDict()

            if is_event:
                item['ts'] = self._formatVal( event['ts'] )
                item['routing'] = self._formatVal( event['routing'] )
                item['event'] = self._formatVal( event['event'] )
            else:
                for key, value in event.items():
                    item[key] = self._formatCol(value)
            data.append(item)

        return tabulate( data, headers = 'keys', tablefmt = 'grid', maxcolwidths=[None, None, None] )

    def _formatCol( self, col ):
        if isinstance( col, dict ):
            return prettyFormatDict(col, indent = 2)
        return col

    def _formatVal ( self, val ):
        if isinstance( val , dict ):
            return prettyFormatDict( val )
        return val

    def do_n( self, inp ):
        '''Fetch the Next page of results.'''
        if self._q is None:
            print( "no more pages in previous query" )
            return
        sys.stdout.write( colored("Query running ", 'cyan') )
        q = self._q
        with Spinner():
            response = q.next()
            error = response.get( 'error', None )
            if error:
                self._logOutput( f"ERROR: {error}" )
                return

        print( "" )
        thisBilled = response.get( 'stats', {} ).get( 'n_billed', 0 )
        self._lastStats = response.get( 'stats', {} )
        self._billed += thisBilled
        self._logOutput( f"Query cost: ${(thisBilled / self._pricingBlock) / 100}" )
        self._logOutput( f"{len( response[ 'results' ] )} results" )

        self._lastData = tuple( d[ 'data' ] for d in response[ 'results' ] )
        toRender = self._lastData

        if len( toRender ) != 0:
            self._outputPage( toRender )

        if q is not None and q.hasMore:
            print( "...query has more pages, use 'next' to get the next page" )
            self._q = q
        else:
            self._q = None

    def do_dryrun( self, inp ):
        '''Execute a command as a dry-run and get back aproximate cost of the query.'''
        sys.stdout.write( colored("Query running ", 'cyan') )
        with Spinner():
            response = self._replay._doQuery( f"{self._timeFrame} | {self._sensors} | {self._events} | {inp}",
                                            limitEvent = self._limitEvent if self._limitEvent else None,
                                            limitEval = self._limitEval if self._limitEval else None,
                                            isDryRun = True,
                                            isCursorBased = False,
                                            stream = self._stream )
        thisBilled = response.get( 'stats', {} ).get( 'n_billed', 0 )
        print( "Note that aproximate costs for queries with a time frame within the last 6h may be under-reported.")
        self._logOutput( f"Aproximate cost: ${(thisBilled / self._pricingBlock) / 100}" )
        self._logOutput( json.dumps( response, indent = 2 ) )

    def complete_dryrun( self, text, line, begidx, endidx ):
        return self.complete_q( text, line, begidx, endidx )

    def do_stats( self, inp ):
        '''Get statistics on the total cost incurred during this session.'''
        self._logOutput( f"Session cost: ${(self._billed / self._pricingBlock) / 100}" )
        self._logOutput( f"Last query stats: {json.dumps( self._lastStats, indent = 2 )}" )
        self._logOutput( f"Last D&R rule generated: {json.dumps( self._lastRule, indent = 2 )}" )

    def do_quit( self, inp ):
        '''Quit the LCQL interface.'''
        self.do_stats( None )
        return True

    def _setPrompt( self ):
        limits = "Context: "
        if self._limitEvent:
            limits += f"limit_event: {self._limitEvent} "
        if self._limitEval:
            limits += f"limit eval: {self._limitEval} "
        self.prompt = f"{limits}{colored(self._timeFrame, 'red')} | {colored(self._sensors, 'blue')} | {colored(self._events, 'green')} | \n> "

    def do_exit( self, inp ):
        '''Quit the LCQL interface.'''
        self.do_stats( None )
        return True

    def emptyline(self):
         pass

    def do_set_format( self, inp ):
        '''Set the display format to output, one of "json", "table"'''
        self._format = inp

    def do_set_time( self, inp ):
        '''Set the time range to query, like "-1h" or "2022-01-16 to 2022-01-18"'''
        self._timeFrame = inp
        self._setPrompt()

    def do_set_sensors( self, inp ):
        '''Set the sensors to query like: "*", a list of SIDs, or a sensor selector like "plat == windows"'''
        self._sensors = inp
        self._setPrompt()

    def do_set_events( self, inp ):
        '''Set the event types to query, like "NEW_PROCESS DNS_REQUEST'''
        self._events = inp

        self._populateSchema()

        self._setPrompt()

    def do_set_stream( self, inp ):
        '''Set the data stream to query, one of "event", "audit", "detect", defaults to "event"'''
        self._stream = inp

    def complete_set_events( self, text, line, begidx, endidx ):
        return [ e for e in self._allEvents if e.startswith( text ) ]

    def _getAllEvents( self ):
        sys.stdout.write( colored("Fetching event list  ", 'cyan') )
        with Spinner():
            self._allEvents = [ e[4:] for e in self._replay._lc.getSchemas()[ 'event_types' ] if e.startswith( 'evt:' ) ]
        print( "" )

    def _populateSchema( self ):
        sys.stdout.write( colored("Fetching autocomplete data  ", 'cyan') )
        with Spinner():
            toSearch = []
            if self._events == '*':
                # Query all evt:
                toSearch = [ '' ]
            else:
                toSearch = [ e.strip() for e in self._events.split() ]

            self._schema = set()
            for evt in toSearch:
                if evt == '':
                    for s, v in self._replay._lc.getSchema( 'evt:' )[ 'schemas' ].items():
                        self._schema.update( ( e[ 2 : ] for e in v ) )
                else:
                    self._schema.update( ( e[ 2 : ] for e in self._replay._lc.getSchema( f"evt:{evt}" )[ 'schema' ][ 'elements' ] ) )
        print( "" )

    @requireIntValue("set_limit_event")
    def do_set_limit_event( self, inp ):
        '''Set the aproximate maximum number of events processed per request, like "1000"'''
        self._limitEvent = int(inp)
        self._setPrompt()

    @requireIntValue("set_limit_eval")
    def do_set_limit_eval( self, inp ):
        '''Set the aproximate maximum number of evaluations per request, like "20000"'''
        self._limitEval = int(inp)
        self._setPrompt()

    def do_set_output( self, inp ):
        '''Set an output file path where this session will be mirrored, like "~/limacharlie_session.txt"'''
        self._outFile = inp

    def do_env( self, inp ):
        '''Display the current environment this session is executing in'''
        self._logOutput( f"Current env: time={self._timeFrame} sensors={self._sensors} events={self._events} format={self._format} output={self._outFile}" )

    def do_lcql( self, inp ):
        '''See the official LCQL documentation here: https://doc.limacharlie.io/docs/documentation/b0915c7a5f598-lima-charlie-query-language'''
        pass

if '__main__' == __name__:
    main()
