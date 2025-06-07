from . import Manager
from .utils import LcApiException
from .utils import parallelExec

import uuid
import json
import yaml
import time
import sys

class queryContext( object ):
    def __init__( self, replay, req, forceUrl = None ):
        self._req = req
        self._replay = replay
        self._forceUrl = forceUrl
        self.hasMore = True

        if self._forceUrl:
            self._altRoot = self._forceUrl
        else:
            self._altRoot = 'https://%s/' % ( self._replay._replayURL, )

        if not self._altRoot.endswith( '/' ):
            self._altRoot += '/'

    def __iter__( self ):
        # If the queryContext is used as an iterator, the returned data
        # during iteration will be the per-row data, not including stats.
        return ResultsIterator( self )

    def next( self ):
        # If the queryContext is not used as an iterator, the user can call
        # next() to get one page at a time of results including stats.
        if self._req[ 'event_source' ][ 'sensor_events' ][ 'cursor' ] is None:
            return None

        resp = self._replay._lc._apiCall( '',
                                          'POST',
                                          {},
                                          altRoot = self._altRoot,
                                          rawBody = json.dumps( self._req ).encode(),
                                          contentType = 'application/json' )
        cursor = resp.get( 'cursor', None )
        if not cursor:
            cursor = None
        self._req[ 'event_source' ][ 'sensor_events' ][ 'cursor' ] = cursor
        if cursor is None:
            self.hasMore = False
        return resp

class ResultsIterator( object ):
    '''Iterator that yields individual results from a queryContext.

    This provides a Python 3 compatible iterator interface that yields
    one result at a time from the API response, automatically fetching
    the next page when needed.
    '''

    def __init__( self, queryContext ):
        self._queryContext = queryContext
        self._currentResults = []
        self._currentIndex = 0
        self._hasMore = True

    def __iter__( self ):
        return self

    def __next__( self ):
        # If we've exhausted the current results, fetch the next page
        if self._currentIndex >= len( self._currentResults ):
            if not self._hasMore:
                raise StopIteration()

            # Get next page of results
            resp = self._queryContext.next()
            if resp is None:
                self._hasMore = False
                raise StopIteration()

            # Update our state
            self._currentResults = resp.get( 'results', [] )
            self._currentIndex = 0
            self._hasMore = self._queryContext.hasMore

            # If we still have no results, we're done
            if not self._currentResults:
                raise StopIteration()

        # Return the next result and advance the index
        result = self._currentResults[ self._currentIndex ]
        self._currentIndex += 1
        return result['data']

class Replay( object ):
    '''Interface to query historical sensor data in Insight with specific D&R rules.'''

    def __init__( self, manager ):
        '''Create a Replay manager object.

        Args:
            manager (limacharlie.Manager): manager providing authentication.
            maxTimeWindow (int): number of seconds to split sensor data during analysis.
            maxConcurrent (int): number of sensors windows to process in parallel.
            isInteractive (bool): if True, display progress updates to standard out.
        '''

        self._lc = manager
        self._replayURL = self._lc.getOrgURLs()[ 'replay' ]

    def _doQuery( self, query, limitEvent = None, limitEval = None, isDryRun = False, isCursorBased = False, stream = 'event',
                  includeStats = False, forceUrl = None, isValidation = False ):
        if not query:
            raise LcApiException( 'no query specified' )

        req = {
            'oid' : self._lc._oid,
            'query' : query,
            'limit_event' : 0 if limitEvent is None else limitEvent,
            'limit_eval' : 0 if limitEval is None else limitEval,
            'is_dry_run' : isDryRun,
            'event_source' : {
                'stream' : stream,
                'sensor_events' : {
                    'cursor' : '-' if isCursorBased else '',
                },
            },
        }

        if includeStats:
            req[ 'include_histogram' ] = True
            req[ 'include_facets' ] = True

        if isValidation:
            req[ 'is_validation' ] = True

        if not isCursorBased:
            return queryContext( self, req, forceUrl = forceUrl ).next()

        return queryContext( self, req, forceUrl = forceUrl )

    def _scanHistoricalSensor( self, sid = None, startTime = None, endTime = None, events = None, ruleName = None, namespace = None, ruleContent = None, isRunTrace = False, isStateful = None, limitEvent = None, limitEval = None, isDryRun = False, stream = 'event' ):
        resp = None

        if ruleName is None and ruleContent is None:
            raise LcApiException( 'no rule specified' )

        req = {
            'oid' : self._lc._oid,
            'rule_source' : {
                'rule_name' : '' if ruleName is None else ruleName,
                'namespace' : '' if namespace is None else namespace,
                'rule' : ruleContent,
            },
            'event_source' : {
                'stream' : stream,
                'sensor_events' : {
                    'sid' : '' if sid is None else sid,
                    'start_time' : 0 if startTime is None else startTime,
                    'end_time' : 0 if endTime is None else endTime,
                },
                'events' : events,
            },
            'trace' : isRunTrace,
            'limit_event' : 0 if limitEvent is None else limitEvent,
            'limit_eval' : 0 if limitEval is None else limitEval,
            'is_dry_run' : isDryRun,
        }

        if isStateful is not None:
            req[ 'is_stateful' ] = isStateful

        resp = self._lc._apiCall( '',
                                  'POST',
                                  {},
                                  altRoot = 'https://%s/' % ( self._replayURL, ),
                                  rawBody = json.dumps( req ).encode(),
                                  contentType = 'application/json' )

        return resp

    def scanHistoricalSensor( self, sid, startTime, endTime, ruleName = None, namespace = None, ruleContent = None, isRunTrace = False, limitEvent = None, limitEval = None, isStateful = None, isDryRun = False, stream = 'event' ):
        '''Scan a specific sensor's data with a D&R rule.

        Args:
            sid (str): sensor ID to scan.
            startTime (int): seconds epoch to start scanning at.
            endTime (int): seconds epoch to stop scanning at.
            ruleName (str): the name of an existing D&R rule to use.
            namespace (str): the namespace the ruleName lives in.
            ruleContent (dict): D&R rule to use to scan, with a "detect" key and a "respond" key.
            isRunTrace (bool): if True, generate a trace of the evaluation.
            limitEvent (int): approximately limit the number of events evaluated.
            limitEval (int): approximately limit the number of rule evaluations.
            isIgnoreState (bool): if True, parallelize processing of single sensors to increase performance but limit effectiveness of stateful detection.
            stream (str): data stream to replay.

        Returns:
            a dict containing results of the query.
        '''

        resp = self._scanHistoricalSensor( sid = sid, startTime = startTime, endTime = endTime, ruleName = ruleName, namespace = namespace, ruleContent = ruleContent, isRunTrace = isRunTrace, limitEvent = limitEvent, limitEval = limitEval, isStateful = isStateful, isDryRun = isDryRun, stream = stream )

        return resp

    def scanEntireOrg( self, startTime, endTime, ruleName = None, namespace = None, ruleContent = None, isRunTrace = False, limitEvent = None, limitEval = None, isStateful = None, isDryRun = False, stream = 'event' ):
        '''Scan an entire organization's data with a D&R rule.

        Args:
            startTime (int): seconds epoch to start scanning at.
            endTime (int): seconds epoch to stop scanning at.
            ruleName (str): the name of an existing D&R rule to use.
            namespace (str): the namespace the ruleName lives in.
            ruleContent (dict): D&R rule to use to scan, with a "detect" key and a "respond" key.
            isRunTrace (bool): if True, generate a trace of the evaluation.
            limitEvent (int): approximately limit the number of events evaluated.
            limitEval (int): approximately limit the number of rule evaluations.
            isIgnoreState (bool): if True, parallelize processing of single sensors to increase performance but limit effectiveness of stateful detection.
            stream (str): data stream to replay.

        Returns:
            a dict containing results of the query.
        '''

        resp = self._scanHistoricalSensor( startTime = startTime, endTime = endTime, ruleName = ruleName, namespace = namespace, ruleContent = ruleContent, isRunTrace = isRunTrace, limitEvent = limitEvent, limitEval = limitEval, isStateful = isStateful, isDryRun = isDryRun, stream = stream )

        return resp

    def scanEvents( self, events, ruleName = None, namespace = None, ruleContent = None, isRunTrace = False, limitEvent = None, limitEval = None, isDryRun = False, stream = 'event' ):
        '''Scan the specific events with a D&R rule.

        Args:
            events (list): list of events to scan.
            ruleName (str): the name of an existing D&R rule to use.
            namespace (str): the namespace the ruleName lives in.
            ruleContent (dict): D&R rule to use to scan, with a "detect" key and a "respond" key.
            isRunTrace (bool): if True, generate a trace of the evaluation.
            limitEvent (int): approximately limit the number of events evaluated.
            limitEval (int): approximately limit the number of rule evaluations.
            stream (str): data stream to replay.

        Returns:
            a dict containing results of the query.
        '''

        resp = self._scanHistoricalSensor( events = events, ruleName = ruleName, namespace = namespace, ruleContent = ruleContent, isRunTrace = isRunTrace, limitEvent = limitEvent, limitEval = limitEval, isDryRun = isDryRun, stream = stream )

        return resp

    def validateRule( self, ruleContent ):
        '''Validate a D&R rule compiles properly.

        Args:
            ruleContent (dict): D&R rule to use to scan, with a "detect" key and a "respond" key.

        Returns:
            a dict containing results of the query.
        '''

        resp = self._scanHistoricalSensor( ruleContent = ruleContent, stream='event', events=[{'event':{},'routing':{}}] )

        return resp

def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie replay' )

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

    parser.add_argument( '--namespace',
                         type = str,
                         required = False,
                         dest = 'namespace',
                         default = None,
                         help = 'namespace the rule-name lives in, like "general" or "managed".' )

    parser.add_argument( '--rule-content',
                         type = str,
                         required = False,
                         dest = 'ruleContent',
                         default = None,
                         help = 'file path where rule to scan is.' )

    parser.add_argument( '--last-seconds',
                         type = int,
                         required = False,
                         dest = 'lastSeconds',
                         default = None,
                         help = 'can be specified instead of --start and --end, will make the time window the last X seconds.' )

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
                         action = 'store_false',
                         default = None,
                         required = False,
                         dest = 'isStateful',
                         help = 'if set, processing from single sensors will be parallelized increasing performance but limiting effectiveness of stateful detection. Auto-detect if not set.' )
    parser.add_argument( '--enforce-state',
                         action = 'store_true',
                         default = None,
                         required = False,
                         dest = 'isStateful',
                         help = 'if set, processing of rules will be serialized by sensor to enable stateful detection. Auto-detect if not set.' )
    parser.add_argument( '--dry-run',
                         action = 'store_true',
                         default = None,
                         required = False,
                         dest = 'isDryRun',
                         help = 'if set, the request will be simulated and the maximum number of evaluations expected will be returned.' )

    parser.add_argument( '--stream',
                         type = str,
                         required = False,
                         dest = 'stream',
                         default = 'event',
                         help = 'data stream to replay, like "event", "audit", "detect", defaults to "event".' )

    args = parser.parse_args( sourceArgs )

    replay = Replay( Manager() )

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
        if ruleContent is None:
            raise LcApiException( 'missing rule content to validate' )
        response = replay.validateRule( ruleContent )
    else:
        if args.events is None:
            if ( args.start is None or args.end is None ) and args.lastSeconds is None:
                raise LcApiException( 'must specify start and end, or last-seconds' )

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
                                                        namespace = args.namespace,
                                                        ruleContent = ruleContent,
                                                        isRunTrace = args.isRunTrace,
                                                        limitEvent = args.limitEvent,
                                                        limitEval = args.limitEval,
                                                        isStateful = args.isStateful,
                                                        isDryRun = args.isDryRun,
                                                        stream = args.stream )
            elif args.isEntireOrg:
                response = replay.scanEntireOrg( start,
                                                 end,
                                                 ruleName = args.ruleName,
                                                 namespace = args.namespace,
                                                 ruleContent = ruleContent,
                                                 isRunTrace = args.isRunTrace,
                                                 limitEvent = args.limitEvent,
                                                 limitEval = args.limitEval,
                                                 isStateful = args.isStateful,
                                                 isDryRun = args.isDryRun,
                                                 stream = args.stream )
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
                                          namespace = args.namespace,
                                          ruleContent = ruleContent,
                                          isRunTrace = args.isRunTrace,
                                          limitEvent = args.limitEvent,
                                          limitEval = args.limitEval,
                                          isDryRun = args.isDryRun,
                                          stream = args.stream )

    print( json.dumps( response, indent = 2 ) )

if '__main__' == __name__:
    main()
