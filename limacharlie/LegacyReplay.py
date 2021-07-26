from gevent.lock import BoundedSemaphore
from . import Manager
from .utils import LcApiException
from .utils import parallelExec

import uuid
import json
import yaml
import gevent
import time
import sys

class Replay( object ):
    '''Interface to query historical sensor data in Insight with specific D&R rules.'''

    def __init__( self, manager, maxTimeWindow = ( 60 * 60 * 24 * 1 ), maxConcurrent = 10, isInteractive = False ):
        '''Create a Replay manager object.

        Args:
            manager (limacharlie.Manager): manager providing authentication.
            maxTimeWindow (int): number of seconds to split sensor data during analysis.
            maxConcurrent (int): number of sensors windows to process in parallel.
            isInteractive (bool): if True, display progress updates to standard out.
        '''

        self._lc = manager
        self._apiURL = None
        self._maxTimeWindow = maxTimeWindow
        self._maxConcurrent = maxConcurrent
        self._replayURL = self._lc.getOrgURLs()[ 'replay' ]

        self._isInteracive = isInteractive
        self._statusMutex = BoundedSemaphore()
        self._queryPending = 0
        self._sensorPending = 0
        self._limitEvent = None
        self._imitEval = None
        self._queryStartedAt = None
        if self._isInteracive:
            self._queryStartedAt = time.time()
            gevent.spawn_later( 0, self._reportStatus )

    def _reportStatus( self ):
        timing = 1
        flag = self._isInteracive
        if isinstance( self._isInteracive, ( tuple, list ) ):
            timing, flag = self._isInteracive
        with self._statusMutex:
            if self._queryStartedAt is None:
                # Indicating the query is done, don't print.
                return
            if flag is True:
                sys.stdout.write( "\rSensors pending: %8s, queries pending: %8s, elapsed: %8.2f seconds" % ( self._sensorPending, self._queryPending, time.time() - self._queryStartedAt ) )
                sys.stdout.flush()
            else:
                # Assuming this is a callback instead.
                flag( self._sensorPending, self._queryPending )

        gevent.spawn_later( timing, self._reportStatus )

    def scanHistoricalSensor( self, sid, startTime, endTime, ruleName = None, ruleContent = None, isRunTrace = False, limitEvent = None, limitEval = None, isIgnoreState = False ):
        '''Scan a specific sensor's data with a D&R rule.

        Args:
            sid (str): sensor ID to scan.
            startTime (int): seconds epoch to start scanning at.
            endTime (int): seconds epoch to stop scanning at.
            ruleName (str): the name of an existing D&R rule to use.
            ruleContent (dict): D&R rule to use to scan, with a "detect" key and a "respond" key.
            isRunTrace (bool): if True, generate a trace of the evaluation.
            limitEvent (int): approximately limit the number of events evaluated.
            limitEval (int): approximately limit the number of rule evaluations.
            isIgnoreState (bool): if True, parallelize processing of single sensors to increase performance but limit effectiveness of stateful detection.

        Returns:
            a dict containing results of the query.
        '''
        windows = []

        with self._statusMutex:
            isSingleQuery = False
            if 0 == self._sensorPending:
                isSingleQuery = True
                self._sensorPending = 1
                # Only initialize the limits if we are not called for
                # an org-wide query. Otherwise the caller will have
                # set the limits already.
                self._limitEvent = limitEvent
                self._limitEval = limitEval

        try:
            # Split up the total time into windows we can query in parallel.
            if endTime - startTime > self._maxTimeWindow:
                tmpStart = startTime
                while tmpStart < endTime:
                    tmpEnd = min( tmpStart + self._maxTimeWindow, endTime )
                    windows.append( ( tmpStart, tmpEnd ) )
                    tmpStart += self._maxTimeWindow
            else:
                windows = [ ( startTime, endTime ) ]

            with self._statusMutex:
                self._queryPending += len( windows )

            if isIgnoreState:
                # Just run it all together.
                results = parallelExec( lambda w: self._scanHistoricalSensor( sid, w[ 0 ], w[ 1 ], ruleName = ruleName, ruleContent = ruleContent, isRunTrace = isRunTrace, isIgnoreState = isIgnoreState ), windows, maxConcurrent = self._maxConcurrent )
            else:
                # We need to iterate one at a time and keep passing the state along.
                results = []
                state = None
                for w in windows:
                    tmpResult = self._scanHistoricalSensor( sid, w[ 0 ], w[ 1 ], ruleName = ruleName, ruleContent = ruleContent, isRunTrace = isRunTrace, isIgnoreState = isIgnoreState, state = state )
                    if 'state' in tmpResult:
                        # Extract the state update so we can pass it to the next call.
                        state = tmpResult[ 'state' ]
                        # Remove the state data from the result.
                        del( tmpResult[ 'state' ] )
                    results.append( tmpResult )
        finally:
            with self._statusMutex:
                self._sensorPending -= 1

        if isSingleQuery:
            with self._statusMutex:
                if self._queryStartedAt is not None:
                    self._queryStartedAt = None

        return self._rollupResults( results )

    def _scanHistoricalSensor( self, sid, startTime, endTime, ruleName = None, ruleContent = None, isRunTrace = False, isIgnoreState = False, state = None ):
        # print( "Starting query %s-%s for %s" % ( startTime, endTime, sid ) )
        # qStart = time.time()

        resp = None

        try:
            if self._apiURL is None:
                # Get the ingest URL from the API.
                self._apiURL = 'https://%s/' % ( self._replayURL, )
            req = {
                'start' : startTime,
                'end' : endTime,
            }
            if isRunTrace:
                req[ 'trace' ] = 'true'
            if isIgnoreState is False:
                req[ 'return_state' ] = 'true'

            # If limits were reached, short circuit the execution.
            with self._statusMutex:
                if self._limitEvent is not None:
                    if 0 >= self._limitEvent:
                        return {}
                    req[ 'limit_event' ] = str( self._limitEvent )
                if self._limitEval is not None:
                    if 0 >= self._limitEval:
                        return {}
                    req[ 'limit_eval' ] = str( self._limitEval )

            body = {}
            if state is not None:
                body[ 'state' ] = state
            if ruleName is not None:
                req[ 'rule_name' ] = ruleName
            elif ruleContent is not None:
                body[ 'rule' ] = ruleContent
            else:
                raise LcApiException( 'no rule specified' )

            if 0 == len( body ):
                body = None
            else:
                body = json.dumps( body ).encode()

            nRetry = 0
            while True:
                try:
                    resp = self._lc._apiCall( 'sensor/%s/%s' % ( self._lc._oid, sid, ),
                                              'POST',
                                              {},
                                              altRoot = self._apiURL,
                                              queryParams = req,
                                              rawBody = body,
                                              contentType = 'application/json' )

                    break
                except:
                    nRetry += 1
                    if nRetry > 5:
                        raise
                    time.sleep( 2 * nRetry )
        finally:
            with self._statusMutex:
                self._queryPending -= 1

                # If there are limits, compute the left-over quota.
                if isinstance( resp, dict ):
                    if self._limitEvent is not None:
                        self._limitEvent -= resp.get( 'num_events', 0 )
                    if self._limitEval is not None:
                        self._limitEval -= resp.get( 'num_evals', 0 )
        # print( "Finished query %s-%s for %s in %s seconds" % ( startTime, endTime, sid, time.time() - qStart ) )

        return resp

    def scanEntireOrg( self, startTime, endTime, ruleName = None, ruleContent = None, isRunTrace = False, limitEvent = None, limitEval = None, isIgnoreState = False ):
        '''Scan an entire organization's data with a D&R rule.

        Args:
            startTime (int): seconds epoch to start scanning at.
            endTime (int): seconds epoch to stop scanning at.
            ruleName (str): the name of an existing D&R rule to use.
            ruleContent (dict): D&R rule to use to scan, with a "detect" key and a "respond" key.
            isRunTrace (bool): if True, generate a trace of the evaluation.
            limitEvent (int): approximately limit the number of events evaluated.
            limitEval (int): approximately limit the number of rule evaluations.
            isIgnoreState (bool): if True, parallelize processing of single sensors to increase performance but limit effectiveness of stateful detection.

        Returns:
            a dict containing results of the query.
        '''
        sensors = list( self._lc.sensors() )

        with self._statusMutex:
            self._sensorPending = len( sensors )
            self._limitEvent = limitEvent
            self._limitEval = limitEval

        results = parallelExec( lambda sid: self.scanHistoricalSensor( sid, startTime, endTime, ruleName = ruleName, ruleContent = ruleContent, isRunTrace = isRunTrace, isIgnoreState = isIgnoreState ), sensors, maxConcurrent = self._maxConcurrent )

        with self._statusMutex:
            if self._queryStartedAt is not None:
                self._queryStartedAt = None

        return self._rollupResults( results )

    def scanEvents( self, events, ruleName = None, ruleContent = None, isRunTrace = False, limitEvent = None, limitEval = None ):
        '''Scan the specific events with a D&R rule.

        Args:
            events (list): list of events to scan.
            ruleName (str): the name of an existing D&R rule to use.
            ruleContent (dict): D&R rule to use to scan, with a "detect" key and a "respond" key.
            isRunTrace (bool): if True, generate a trace of the evaluation.
            limitEvent (int): approximately limit the number of events evaluated.
            limitEval (int): approximately limit the number of rule evaluations.

        Returns:
            a dict containing results of the query.
        '''
        # qStart = time.time()

        with self._statusMutex:
            self._sensorPending = 1

        try:
            if self._apiURL is None:
                # Get the ingest URL from the API.
                self._apiURL = 'https://%s/' % ( self._replayURL, )
            req = {}
            body = {
                'events' : events,
            }
            if ruleName is not None:
                req[ 'rule_name' ] = ruleName
            elif ruleContent is not None:
                body[ 'rule' ] = ruleContent
            else:
                raise LcApiException( 'no rule specified' )

            if isRunTrace:
                req[ 'trace' ] = 'true'

            if limitEvent is not None:
                req[ 'limit_event' ] = str( limitEvent )
            if limitEval is not None:
                req[ 'limit_eval' ] = str( limitEval )

            nRetry = 0
            while True:
                try:
                    resp = self._lc._apiCall( 'simulate/%s' % ( self._lc._oid, ),
                                              'POST',
                                              {},
                                              altRoot = self._apiURL,
                                              queryParams = req,
                                              rawBody = json.dumps( body ).encode(),
                                              contentType = 'application/json' )

                    break
                except:
                    nRetry += 1
                    if nRetry > 5:
                        raise
                    time.sleep( 2 * nRetry )
        finally:
            with self._statusMutex:
                self._queryPending -= 1
        # print( "Finished query %s-%s for %s in %s seconds" % ( startTime, endTime, sid, time.time() - qStart ) )

        return resp

    def validateRule( self, ruleContent = None ):
        '''Validate a D&R rule compiles properly.

        Args:
            ruleContent (dict): D&R rule to use to scan, with a "detect" key and a "respond" key.

        Returns:
            a dict containing results of the query.
        '''
        # qStart = time.time()

        if self._apiURL is None:
            # Get the ingest URL from the API.
            self._apiURL = 'https://%s/' % ( self._replayURL, )
        req = {}
        body = {
            'rule' : ruleContent,
        }
        if ruleContent is None:
            raise LcApiException( 'no rule specified' )

        nRetry = 0
        while True:
            try:
                resp = self._lc._apiCall( 'validate/%s' % ( self._lc._oid, ),
                                          'POST',
                                          {},
                                          altRoot = self._apiURL,
                                          queryParams = req,
                                          rawBody = json.dumps( body ).encode(),
                                          contentType = 'application/json' )

                break
            except:
                nRetry += 1
                if nRetry > 5:
                    raise
                time.sleep( 2 * nRetry )
        # print( "Finished query %s-%s for %s in %s seconds" % ( startTime, endTime, sid, time.time() - qStart ) )

        return resp

    def _rollupResults( self, results ):
        final = {}
        for result in results:
            if not isinstance( result, dict ):
                raise result
            for k, v in result.items():
                if isinstance( v, bool ):
                    # MUST test for bool before int because in Python
                    # a bool IS an instance of an INT.....
                    if k not in final:
                        final[ k ] = v
                    elif not final[ k ] and v:
                        final[ k ] = v
                elif isinstance( v, ( int, float ) ):
                    if k not in final:
                        final[ k ] = 0
                    final[ k ] += v
                elif isinstance( v, ( str, bytes ) ):
                    final.setdefault( k, [] ).append( v )
                elif isinstance( v, dict ):
                    final.setdefault( k, {} ).update( v )
                elif isinstance( v, ( list, tuple ) ):
                    tmp = final.setdefault( k, [] )
                    tmp += list( v )
                else:
                    raise LcApiException( 'unexpected data type: %s' % ( type( v ), ) )
        return final

def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie.io replay detection and response' )

    parser.add_argument( '--sid',
                         type = uuid.UUID,
                         required = False,
                         dest = 'sid',
                         default = None,
                         help = 'sensor id to scan traffic from.' )

    parser.add_argument( '--entire-org',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'isEntireOrg',
                         help = 'if set and --sid is not set, replay traffic from entire organization.' )

    parser.add_argument( '--start',
                         type = int,
                         required = False,
                         dest = 'start',
                         default = None,
                         help = 'epoch seconds at which to start scanning sensor traffic.' )

    parser.add_argument( '--end',
                         type = int,
                         required = False,
                         dest = 'end',
                         default = None,
                         help = 'epoch seconds at which to end scanning sensor traffic.' )

    parser.add_argument( '--events',
                         type = str,
                         required = False,
                         dest = 'events',
                         default = None,
                         help = 'path to file containing events to use in evaluation.' )

    parser.add_argument( '--rule-name',
                         type = str,
                         required = False,
                         dest = 'ruleName',
                         default = None,
                         help = 'name of the an already-existing rule to scan with.' )

    parser.add_argument( '--rule-content',
                         type = str,
                         required = False,
                         dest = 'ruleContent',
                         default = None,
                         help = 'file path where rule to scan is.' )

    parser.add_argument( '--max-time-window',
                         type = int,
                         required = False,
                         dest = 'maxTimeWindow',
                         default = ( 60 * 60 * 24 * 1 ),
                         help = 'maximum number of seconds in a window used to shard the search.' )

    parser.add_argument( '--max-concurrent',
                         type = int,
                         required = False,
                         dest = 'maxConcurrent',
                         default = 10,
                         help = 'maximum number of concurrent queries per sensor searched.' )

    parser.add_argument( '--last-seconds',
                         type = int,
                         required = False,
                         dest = 'lastSeconds',
                         default = None,
                         help = 'can be specified instead of --start and --end, will make the time window the last X seconds.' )

    parser.add_argument( '--quiet',
                         action = 'store_false',
                         default = True,
                         required = False,
                         dest = 'isInteractive',
                         help = 'if set, will not print status update to stdout.' )

    parser.add_argument( '--trace',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'isRunTrace',
                         help = 'if set will output a trace of each operator evaluation and the result' )

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

    parser.add_argument( '--validate',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'isValidate',
                         help = 'if set will only validate the rule compiles properly' )

    parser.add_argument( '--ignore-state',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'isIgnoreState',
                         help = 'if set, processing from single sensors will be parallelized increasing performance but limiting effectiveness of stateful detection.' )

    args = parser.parse_args( sourceArgs )

    replay = Replay( Manager( None, None ),
                     isInteractive = args.isInteractive,
                     maxTimeWindow = args.maxTimeWindow,
                     maxConcurrent = args.maxConcurrent )

    ruleContent = None
    if args.ruleContent is not None:
        with open( args.ruleContent, 'rb' ) as f:
            ruleContent = f.read().decode()
        try:
            ruleContent = yaml.safe_load( ruleContent )
        except:
            try:
                ruleContent = json.loads( ruleContent )
            except:
                raise LcApiException( 'rule content not valid yaml or json' )

    if args.isValidate:
        response = replay.validateRule( ruleContent )
    else:
        if args.events is None:
            if ( args.start is None or args.end is None ) and args.lastSeconds is None:
                print( 'must specify start and end, or last-seconds' )
                parser.print_help()
                sys.exit(1)

        if args.events is None:
            # We want to use Insight-based events.
            start = args.start
            end = args.end
            if start is None and end is None and args.lastSeconds is not None:
                now = int( time.time() )
                start = now - args.lastSeconds
                end = now

            if args.sid is not None:
                response = replay.scanHistoricalSensor( str( args.sid ),
                                                        start,
                                                        end,
                                                        ruleName = args.ruleName,
                                                        ruleContent = ruleContent,
                                                        isRunTrace = args.isRunTrace,
                                                        limitEvent = args.limitEvent,
                                                        limitEval = args.limitEval,
                                                        isIgnoreState = args.isIgnoreState )
            elif args.isEntireOrg:
                response = replay.scanEntireOrg( start,
                                                 end,
                                                 ruleName = args.ruleName,
                                                 ruleContent = ruleContent,
                                                 isRunTrace = args.isRunTrace,
                                                 limitEvent = args.limitEvent,
                                                 limitEval = args.limitEval,
                                                 isIgnoreState = args.isIgnoreState )
            else:
                raise LcApiException( '--sid or --entire-org must be specified' )
        else:
            # We are using an events file.
            with open( args.events, 'rb' ) as f:
                fileContent = f.read().decode()
            # We support two formats.
            try:
                try:
                    # This is a JSON list containing all the events like you get
                    # from the historical view download button. Or just single
                    # JSON event.
                    events = json.loads( fileContent )
                except:
                    # This is newline-delimited like you get from LC Outputs.
                    events = [ json.loads( e ) for e in fileContent.split( '\n' ) ]

                # If the result is a dictionary and not a list we assume this was
                # just a single event so we will wrap it.
                if isinstance( events, dict ):
                    events = [ events ]
            except:
                print( "!!! Invalid events provided. Content should be a JSON event, a JSON LIST of events or newline-separated JSON." )
                sys.exit( 1 )
            response = replay.scanEvents( events,
                                          ruleName = args.ruleName,
                                          ruleContent = ruleContent,
                                          isRunTrace = args.isRunTrace,
                                          limitEvent = args.limitEvent,
                                          limitEval = args.limitEval )

    if args.isInteractive:
        # If this is interactive, we displayed progress, so we need a new line.
        print( "" )

    print( json.dumps( response, indent = 2 ) )

if '__main__' == __name__:
    main()