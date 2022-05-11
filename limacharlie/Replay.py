from . import Manager
from .utils import LcApiException
from .utils import parallelExec

import uuid
import json
import yaml
import time
import sys

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

    def _scanHistoricalSensor( self, sid = None, startTime = None, endTime = None, events = None, ruleName = None, ruleContent = None, isRunTrace = False, isStateful = None, limitEvent = None, limitEval = None ):
        resp = None

        if ruleName is None and ruleContent is None:
            raise LcApiException( 'no rule specified' )

        req = {
            'oid' : self._lc._oid,
            'rule_source' : {
                'rule_name' : '' if ruleName is None else ruleName,
                'rule' : ruleContent,
            },
            'event_source' : {
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

    def scanHistoricalSensor( self, sid, startTime, endTime, ruleName = None, ruleContent = None, isRunTrace = False, limitEvent = None, limitEval = None, isStateful = None ):
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

        resp = self._scanHistoricalSensor( sid = sid, startTime = startTime, endTime = endTime, ruleName = ruleName, ruleContent = ruleContent, isRunTrace = isRunTrace, limitEvent = limitEvent, limitEval = limitEval, isStateful = isStateful )
        
        return resp

    def scanEntireOrg( self, startTime, endTime, ruleName = None, ruleContent = None, isRunTrace = False, limitEvent = None, limitEval = None, isStateful = None ):
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
        
        resp = self._scanHistoricalSensor( startTime = startTime, endTime = endTime, ruleName = ruleName, ruleContent = ruleContent, isRunTrace = isRunTrace, limitEvent = limitEvent, limitEval = limitEval, isStateful = isStateful )

        return resp

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

        resp = self._scanHistoricalSensor( events = events, ruleName = ruleName, ruleContent = ruleContent, isRunTrace = isRunTrace, limitEvent = limitEvent, limitEval = limitEval )

        return resp

    def validateRule( self, ruleContent ):
        '''Validate a D&R rule compiles properly.

        Args:
            ruleContent (dict): D&R rule to use to scan, with a "detect" key and a "respond" key.

        Returns:
            a dict containing results of the query.
        '''
        
        resp = self._scanHistoricalSensor( ruleContent = ruleContent )

        return resp

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
                                                        ruleContent = ruleContent,
                                                        isRunTrace = args.isRunTrace,
                                                        limitEvent = args.limitEvent,
                                                        limitEval = args.limitEval,
                                                        isStateful = args.isStateful )
            elif args.isEntireOrg:
                response = replay.scanEntireOrg( start,
                                                 end,
                                                 ruleName = args.ruleName,
                                                 ruleContent = ruleContent,
                                                 isRunTrace = args.isRunTrace,
                                                 limitEvent = args.limitEvent,
                                                 limitEval = args.limitEval,
                                                 isStateful = args.isStateful )
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

    print( json.dumps( response, indent = 2 ) )

if '__main__' == __name__:
    main()