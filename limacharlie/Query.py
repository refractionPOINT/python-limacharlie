from functools import cache
from . import Manager
from .Replay import Replay
import json
import cmd
try:
    import pydoc
except:
    pydoc = None
try:
    from tabulate import tabulate
except:
    tabulate = None
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

    args = parser.parse_args( sourceArgs )

    replay = Replay( Manager() )

    if not args.query:
        LCQuery( replay, args.format, args.outFile ).cmdloop()
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
    def __init__( self, replay, format, outFile ):
        self.intro = 'This LimaCharlie feature is in Alpha, LCQL is likely going to evolve!\nThe LimaCharlie Query allows you to query the dataset in a more free-form fashion based on the LC Query Language.'
        self._timeFrame = "-10m"
        self._sensors = "*"
        self._events = "*"
        self._limitEvent = 0
        self._limitEval = 0
        self._billed = 0
        self._pricingBlock = 25000
        self._histfile = os.path.expanduser( '~/.limacharlie_history' )
        self._histfile_size = 1000
        self._outFile = outFile
        self._replay = replay
        self._format = format
        self._lastData = None
        self._lastQuery = None
        super(LCQuery, self).__init__()
        self._setPrompt()

    def preloop( self ):
        if readline and os.path.exists( self._histfile ):
            readline.read_history_file( self._histfile )

    def postloop( self ):
        if readline:
            readline.set_history_length( self._histfile_size )
            readline.write_history_file( self._histfile )

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

    def default( self, inp ):
        thisQuery = f"{self._timeFrame} | {self._sensors} | {self._events} | {inp}"
        cacheKey = f"{self._limitEval}{self._limitEvent}{thisQuery}"

        # Check if the is the same last query we did, if so, re-use the result.
        if cacheKey == self._lastQuery:
            self._logOutput( f"{len( self._lastData )} results from cache" )
            toRender = self._lastData
        else:
            response = self._replay._doQuery( thisQuery,
                                            limitEvent = self._limitEvent if self._limitEvent else None,
                                            limitEval = self._limitEval if self._limitEval else None )
            error = response.get( 'error', None )
            if error:
                self._logOutput( f"ERROR: {error}" )
                return

            thisBilled = response.get( 'stats', {} ).get( 'n_billed', 0 )
            self._billed += thisBilled
            self._logOutput( f"Query cost: ${(thisBilled / self._pricingBlock) / 100}" )
            self._logOutput( f"{len( response[ 'results' ] )} results" )

            self._lastData = tuple( d[ 'data' ] for d in response[ 'results' ] )
            self._lastQuery = cacheKey
            toRender = self._lastData

        if self._format == 'json':
            if pydoc is None:
                self._logOutput( "\n".join( json.dumps( d, indent = 2 ) for d in toRender ) )
            else:
                dat = "\n".join( json.dumps( d, indent = 2 ) for d in toRender )
                self._logOutput( dat, isNoPrint = True )
                pydoc.pager( dat )
        elif self._format == 'table':
            if tabulate is None:
                self._logOutput( 'failed to import tabulate' )
            else:
                if pydoc is None:
                    self._logOutput( tabulate( toRender, headers = 'keys', tablefmt = 'github' ) )
                else:
                    dat = tabulate( toRender, headers = 'keys', tablefmt = 'github' )
                    self._logOutput( dat, isNoPrint = True )
                    pydoc.pager( dat )
        else:
            self._logOutput( 'unknown format' )

    def do_dryrun( self, inp ):
        '''Execute a command as a dry-run and get back aproximate cost of the query.'''
        response = self._replay._doQuery( f"{self._timeFrame} | {self._sensors} | {self._events} | {inp}",
                                          limitEvent = self._limitEvent if self._limitEvent else None,
                                          limitEval = self._limitEval if self._limitEval else None,
                                          isDryRun = True )
        thisBilled = response.get( 'stats', {} ).get( 'n_billed', 0 )
        self._logOutput( f"Aproximate cost: ${(thisBilled / self._pricingBlock) / 100}" )
        self._logOutput( json.dumps( response, indent = 2 ) )

    def do_stats( self, inp ):
        '''Get statistics on the total cost incurred during this session.'''
        self._logOutput( f"Session cost: ${(self._billed / self._pricingBlock) / 100}" )

    def do_quit( self, inp ):
        '''Quit the LCQL interface.'''
        self.do_stats( None )
        return True

    def _setPrompt( self ):
        limits = ""
        if self._limitEvent:
            limits += f"limit_event: {self._limitEvent} "
        if self._limitEval:
            limits += f"limit eval: {self._limitEval} "
        self.prompt = f"{limits}{self._timeFrame} | {self._sensors} | {self._events} | "

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
        self._setPrompt()

    def do_set_limit_event( self, inp ):
        '''Set the aproximate maximum number of events processed per request, like "1000"'''
        self._limitEvent = int(inp)
        self._setPrompt()

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
        '''
        Keep in mind LCQL is currently in Alpha, changes are likely in the future.
        LCQL queries contain 4 components with a 5th optional one, each component is
        separated by a pipe ("|"):
        1-  Timeframe: the time range the query applies to. This can be either a single
            offset in the past like "-1h" or "-30m". Or it can be a date time range
            like "2022-01-22 10:00:00 to 2022-01-25 14:00:00".
        2-  Sensors: the set of sensors to query. This can be either "*" for all sensors,
            a list of space separated SIDs like "111-... 222-... 333-...", or it can
            be a sensor selector (https://doc.limacharlie.io/docs/documentation/36c920f4f7bc9-sensor-selector-expressions)
            like "plat == windows".
        3-  Events: the list of events to include in the query, space separated like
            "NEW_PROCESS DNS_REQUEST", or a "*" to go over all event types.
        4-  Filter: the actual query filter. The filters are a series of statements
            combined with " and " and " or " that can be associated with parenthesis ("()").
            String literals, when used, can be double-quoted to be case insensitive
            or single-quoted to be case sensitive.
            Selectors behave like D&R rules, for example: "event/FILE_PATH".
            These are the currently supported operators:
            - "is" (or "==") example: event/FILE_IS_SIGNED is 1 or event/FILE_PATH is "c:\windows\calc.exe"
            - "is not" (or "!=") example: event/FILE_IS_SIGNED != 0
            - "contains" example: event/FILE_PATH contains 'evil'
            - "not contains"
            - "matches" example: event/FILE_PATH matches ".*system[0-9a-z].*"
            - "not matches"
            - "starts with" example: event/FILE_PATH starts with "c:\windows"
            - "not starts with"
            - "ends with" example: event/FILE_PATH ends with '.eXe'
            - "not ends with"
            - "cidr" example: event/NETWORK_CONNECTIONS/IP_ADDRESS cidr "10.1.0.0/16"
            - "is lower than" example: event/NETWORK_CONNECTIONS/PORT is lower than 1024
            - "is greater than"
            - "is platform" example: is platform "windows"
            - "is not platform"
            - "is tagged" example: is tagged "vip"
            - "is not tagged"
            - "is public address" example: event/NETWORK_CONNECTIONS/IP_ADDRESS is public address
            - "is private address"
            - "scope" example: event/NETWORK_CONNECTIONS scope (event/IP_ADDRESS is public address and event/PORT is 443)
            - "with child" / "with descendant" / "with events" example: event/FILE_PATH contains "evil" with child (event/COMMAND_LINE contains "powershell")
        5-  Projection (optional): a list of fields you would like to extract from the results
            with a possible alias, like: "event/FILE_PATH as path event/USER_NAME AS user_name event/COMMAND_LINE"

        All of this can result in a query like:
        -30m | plat == windows | NEW_PROCESS | event/COMMAND_LINE contains "powershell" and event/FILE_PATH not contains "powershell" | event/COMMAND_LINE as cli event/FILE_PATH as path routing/hostname as host
        OR
        -30m | plat == windows | * | event/COMMAND_LINE contains "powershell" and event/FILE_PATH not contains "powershell" |
        '''
        pass

if '__main__' == __name__:
    main()