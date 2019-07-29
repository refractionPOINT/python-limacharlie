from .Sensor import Sensor
from .utils import LcApiException
from .utils import _isStringCompat
import json
import yaml

class _Replicant( object ):
    def __init__( self, manager ):
        self._manager = manager

class Responder( _Replicant ):
    def sweep( self, sid ):
        if isinstance( sid, Sensor ):
            sid = sid.sid
        return self._manager.replicantRequest( 'responder', {
            'action' : 'sweep',
            'sid' : sid,
        }, True )

class Yara( _Replicant ):
    def scan( self, sid, sources ):
        if isinstance( sid, Sensor ):
            sid = sid.sid
        return self._manager.replicantRequest( 'yara', {
            'action' : 'scan',
            'sid' : sid,
            'sources' : sources,
        }, True )

    def getRules( self ):
        return self._manager.replicantRequest( 'yara', {
            'action' : 'list_rules',
        }, False )

    def getSources( self ):
        return self._manager.replicantRequest( 'yara', {
            'action' : 'list_sources',
        }, False )

    def addRule( self, ruleName, sources = [], tags = [], platforms = [] ):
        return self._manager.replicantRequest( 'yara', {
            'action' : 'add_rule',
            'name' : ruleName,
            'sources' : sources,
            'tags' : tags,
            'platforms' : platforms,
        }, False )

    def removeRule( self, ruleName ):
        return self._manager.replicantRequest( 'yara', {
            'action' : 'remove_rule',
            'name' : ruleName,
        }, False )

    def addSource( self, sourceName, sources = [], tags = [], platforms = [] ):
        return self._manager.replicantRequest( 'yara', {
            'action' : 'add_source',
            'name' : sourceName,
            'source' : sources,
        }, False )

    def removeSource( self, sourceName ):
        return self._manager.replicantRequest( 'yara', {
            'action' : 'remove_source',
            'name' : sourceName,
        }, False )

class Integrity( _Replicant ):
    def getRules( self ):
        return self._manager.replicantRequest( 'integrity', {
            'action' : 'list_rules',
        }, False )

    def addRule( self, ruleName, patterns = [], tags = [], platforms = [] ):
        return self._manager.replicantRequest( 'integrity', {
            'action' : 'add_rule',
            'name' : ruleName,
            'patterns' : patterns,
            'tags' : tags,
            'platforms' : platforms,
        }, False )

    def removeRule( self, ruleName ):
        return self._manager.replicantRequest( 'integrity', {
            'action' : 'remove_rule',
            'name' : ruleName,
        }, False )

class Logging( _Replicant ):
    def getRules( self ):
        return self._manager.replicantRequest( 'logging', {
            'action' : 'list_rules',
        }, False )

    def addRule( self, ruleName, patterns = [], tags = [], platforms = [], isDeleteAfter = False ):
        return self._manager.replicantRequest( 'logging', {
            'action' : 'add_rule',
            'name' : ruleName,
            'patterns' : patterns,
            'is_delete_after' : isDeleteAfter,
            'tags' : tags,
            'platforms' : platforms,
        }, False )

    def removeRule( self, ruleName ):
        return self._manager.replicantRequest( 'logging', {
            'action' : 'remove_rule',
            'name' : ruleName,
        }, False )

class Replay( _Replicant ):
    def runJob( self, startTime, endTime, sid = None, ruleName = None, ruleContent = None ):
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
    def getRules( self ):
        return self._manager.replicantRequest( 'exfil', {
            'action' : 'list_rules',
        }, False )

    def addEventRule( self, ruleName, events = [], tags = [], platforms = [] ):
        return self._manager.replicantRequest( 'exfil', {
            'action' : 'add_event_rule',
            'name' : ruleName,
            'events' : events,
            'tags' : tags,
            'platforms' : platforms,
        }, False )

    def removeEventRule( self, ruleName ):
        return self._manager.replicantRequest( 'exfil', {
            'action' : 'remove_event_rule',
            'name' : ruleName,
        }, False )

    def addWatchRule( self, ruleName, event, operator, value, path = [], tags = [], platforms = [] ):
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
        return self._manager.replicantRequest( 'exfil', {
            'action' : 'remove_watch',
            'name' : ruleName,
        }, False )