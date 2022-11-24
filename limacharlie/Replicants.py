from .Sensor import Sensor
from .utils import LcApiException
from .utils import _isStringCompat
import json
import yaml

class _Replicant( object ):
    def __init__( self, manager ):
        self._manager = manager

class Responder( _Replicant ):
    '''Responder service manager object.'''

    def sweep( self, sid ):
        '''Perform a sweep of a given host.

        Args:
            sid (str): sensor ID to sweep.
        '''

        if isinstance( sid, Sensor ):
            sid = sid.sid
        return self._manager.replicantRequest( 'responder', {
            'action' : 'sweep',
            'sid' : sid,
        }, True )

class Yara( _Replicant ):
    '''Yara service manager object.'''

    def scan( self, sid, sources ):
        '''Perform an ad-hoc scan of a sensor with Yara signatures.

        Args:
            sid (str): sensor ID to scan.
            sources (list of str): list of source Yara signature names to use in the scan.
        '''

        if isinstance( sid, Sensor ):
            sid = sid.sid
        return self._manager.replicantRequest( 'yara', {
            'action' : 'scan',
            'sid' : sid,
            'sources' : sources,
        }, True )

    def getRules( self ):
        '''Get the constant Yara scanning rules in effect.

        Returns:
            Dict of rules.
        '''

        return self._manager.replicantRequest( 'yara', {
            'action' : 'list_rules',
        }, False )

    def getSources( self ):
        '''Get the Yara signature sources.

        Returns:
            Dict of sources.
        '''

        return self._manager.replicantRequest( 'yara', {
            'action' : 'list_sources',
        }, False )

    def getSource( self, sourceName ):
        '''Get the content of a Yara signature source.

        Args:
            sourceName (str): name of the source to get.

        Returns:
            Source content.
        '''

        return self._manager.replicantRequest( 'yara', {
            'action' : 'get_source',
            'source' : sourceName,
        }, False ).get( 'content', None )

    def addRule( self, ruleName, sources = [], tags = [], platforms = [] ):
        '''Add a constant Yara scanning rule.

        Args:
            ruleName (str): name of the rule to add.
            sources (list of str): list of sources this rule should scan with.
            tags (list of str): list of tags sensors must posses for this rule to apply.
            platforms (list of str): list of platform names this rule applies to.
        '''

        return self._manager.replicantRequest( 'yara', {
            'action' : 'add_rule',
            'name' : ruleName,
            'sources' : sources,
            'tags' : tags,
            'platforms' : platforms,
        }, False )

    def removeRule( self, ruleName ):
        '''Remove a constant Yara scanning rule.

        Args:
            ruleName (str): name of the rule to remove.
        '''

        return self._manager.replicantRequest( 'yara', {
            'action' : 'remove_rule',
            'name' : ruleName,
        }, False )

    def addSource( self, sourceName, source ):
        '''Add a Yara signature source.

        Args:
            sourceName (str): name of the source to add.
            source (str): source URL for the Yara signature(s).
        '''

        return self._manager.replicantRequest( 'yara', {
            'action' : 'add_source',
            'name' : sourceName,
            'source' : source,
        }, False )

    def removeSource( self, sourceName ):
        '''Remove a Yara rule source.

        Args:
            sourceName (str): name of the source to remove.
        '''

        return self._manager.replicantRequest( 'yara', {
            'action' : 'remove_source',
            'name' : sourceName,
        }, False )

class Integrity( _Replicant ):
    '''File and Registry Integrity Monitoring (FIM) service manager object.'''

    def getRules( self ):
        '''Get FIM rules in effect.

        Returns:
            Dict of rules.
        '''

        return self._manager.replicantRequest( 'integrity', {
            'action' : 'list_rules',
        }, False )

    def addRule( self, ruleName, patterns = [], tags = [], platforms = [] ):
        '''Add an FIM rule.

        Args:
            ruleName (str): name of the rule to add.
            patterns (list of str): list of file/registry patterns to monitor.
            tags (list of str): list of tags sensors must posses for this rule to apply.
            platforms (list of str): list of platform names this rule applies to.
        '''

        return self._manager.replicantRequest( 'integrity', {
            'action' : 'add_rule',
            'name' : ruleName,
            'patterns' : patterns,
            'tags' : tags,
            'platforms' : platforms,
        }, False )

    def removeRule( self, ruleName ):
        '''Remove an FIM rule.

        Args:
            ruleName (str): name of the rule to remove.
        '''

        return self._manager.replicantRequest( 'integrity', {
            'action' : 'remove_rule',
            'name' : ruleName,
        }, False )

class Logging( _Replicant ):
    '''Logging service manager object.'''

    def getRules( self ):
        '''Get the Log collection rules in effect.
        '''

        return self._manager.replicantRequest( 'logging', {
            'action' : 'list_rules',
        }, False )

    def addRule( self, ruleName, patterns = [], tags = [], platforms = [], isDeleteAfter = False, isIgnoreCert = False, daysRetention = 0 ):
        '''Add a Log collection rule.

        Args:
            ruleName (str): name of the rule to add.
            patterns (list of str): list of file patterns describing Logs to monitor and retrieve.
            tags (list of str): list of tags sensors must posses for this rule to apply.
            platforms (list of str): list of platform names this rule applies to.
            isDeleteAfter (bool): if True, delete the Log after retrieval.
            isIgnoreCert (bool): if True, sensor ignores SSL cert errors during log upload.
        '''

        return self._manager.replicantRequest( 'logging', {
            'action' : 'add_rule',
            'name' : ruleName,
            'patterns' : patterns,
            'is_delete_after' : isDeleteAfter,
            'is_ignore_cert' : isIgnoreCert,
            'days_retention' : daysRetention,
            'tags' : tags,
            'platforms' : platforms,
        }, False )

    def removeRule( self, ruleName ):
        '''Remove a Log collection rule.

        Args:
            ruleName (str): name of the rule to remove.
        '''

        return self._manager.replicantRequest( 'logging', {
            'action' : 'remove_rule',
            'name' : ruleName,
        }, False )

class Replay( _Replicant ):
    '''Replay service manager object.'''

    def runJob( self, startTime, endTime, sid = None, ruleName = None, ruleContent = None ):
        '''Run a Replay service job.

        Args:
            startTime (int): epoch start time to replay.
            endTime (int): epoch end time to replay.
            sid (str): sensor ID to replay the data from.
            ruleName (str): optional name of an existing D&R rule to replay.
            ruleContent (dict): optional content of a D&R rule to replay.
        '''

        if isinstance( sid, Sensor ):
            sid = sid.sid
        req = {
            'action' : 'replay',
            'start' : startTime,
            'end' : endTime,
        }
        if sid is not None:
            req[ 'sid' ] = sid
        if ruleName is not None:
            req[ 'rule_name' ] = ruleName
        if ruleContent is not None:
            if _isStringCompat( ruleContent ):
                try:
                    ruleContent = yaml.safeLoad( ruleContent )
                except:
                    try:
                        ruleContent = json.loads( ruleContent )
                    except:
                        raise LcApiException( 'rule content not JSON and not YAML' )
            req[ 'rule_content' ] = ruleContent
        return self._manager.replicantRequest( 'replay', req, True )

class Exfil( _Replicant ):
    '''Exfil control service manager object.'''

    def getRules( self ):
        '''Get the exfil rules in effect.

        Returns:
            Dict of rules.
        '''

        return self._manager.replicantRequest( 'exfil', {
            'action' : 'list_rules',
        }, False )

    def addEventRule( self, ruleName, events = [], tags = [], platforms = [] ):
        '''Add an event rule describing events sent to the cloud in real-time.

        Args:
            ruleName (str): name of the rule to add.
            events (list of str): list of event names to send in real-time.
            tags (list of str): list of tags sensors must posses for this rule to apply.
            platforms (list of str): list of platform names this applies to.
        '''

        return self._manager.replicantRequest( 'exfil', {
            'action' : 'add_event_rule',
            'name' : ruleName,
            'events' : events,
            'tags' : tags,
            'platforms' : platforms,
        }, False )

    def removeEventRule( self, ruleName ):
        '''Remove an event rule.

        Args:
            ruleName (str): name of the rule to remove.
        '''

        return self._manager.replicantRequest( 'exfil', {
            'action' : 'remove_event_rule',
            'name' : ruleName,
        }, False )

    def addWatchRule( self, ruleName, event, operator, value, path = [], tags = [], platforms = [] ):
        '''Add a watch rule to send matching events to the cloud in real-time.

        Args:
            ruleName (str): name of the watch rule to add.
            event (str): name of the event this rule applies to.
            operator (str): comparison operator name to determine match.
            value (str): value to compare to for matching.
            path (list of str): path within the event to compare the value of, without a leading "event".
            tags (list of str): list of tags sensors must posses for this rule to apply.
            platforms (list of str): list of platform names this applies to.
        '''

        return self._manager.replicantRequest( 'exfil', {
            'action' : 'add_watch',
            'name' : ruleName,
            'operator' : operator,
            'event' : event,
            'value' : value,
            'path' : path,
            'tags' : tags,
            'platforms' : platforms,
        }, False )

    def removeWatchRule( self, ruleName ):
        '''Remove a watch rule.

        Args:
            ruleName (str): name of the rule to remove.
        '''

        return self._manager.replicantRequest( 'exfil', {
            'action' : 'remove_watch',
            'name' : ruleName,
        }, False )

class Dumper( _Replicant ):
    '''Memory dumper service object.'''

    def dump( self, sid ):
        '''Dump the full memory of a given host.

        Args:
            sid (str): sensor ID to sweep.
        '''

        if isinstance( sid, Sensor ):
            sid = sid.sid
        return self._manager.replicantRequest( 'dumper', {
            'sid' : sid,
        }, True )

class ReliableTasking( _Replicant ):
    '''Reliable Tasking service object.'''

    def task( self, task, sid = None, tag = None, ttl = None ):
        '''Issue a task for a set of sensors even if offline.

        Args:
            task (str): actual task command line to send.
            sid (str): optional sensor ID to task or '*' for all.
            tag (str): optional tag to select sensors to send the task to.
            ttl (int): optional number of seconds before unsent tasks expire, defaults to a week.
        '''

        req = {
            'action' : 'task',
            'task' : task,
        }
        if sid is not None:
            if isinstance( sid, Sensor ):
                sid = sid.sid
            req[ 'sid' ] = sid
        if tag is not None:
            req[ 'tag' ] = tag
        if ttl is not None:
            req[ 'ttl' ] = ttl
        return self._manager.replicantRequest( 'reliable-tasking', req, True )

    def getTasks( self, sid = None, tag = None ):
        '''Issue a task for a set of sensors even if offline.

        Args:
            sid (str): optional sensor ID to get the tasks for or '*' for all.
            tag (str): optional tag to select sensors to get the tasks for.
        '''

        req = {
            'action' : 'list',
        }
        if sid is not None:
            if isinstance( sid, Sensor ):
                sid = sid.sid
            req[ 'sid' ] = sid
        if tag is not None:
            req[ 'tag' ] = tag
        return self._manager.replicantRequest( 'reliable-tasking', req, False )