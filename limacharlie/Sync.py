from .Manager import Manager
from .Replicants import Integrity
from .Replicants import Logging
from .Replicants import Exfil
from .utils import _isStringCompat

# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

import uuid
import os
import sys
import yaml
import json

class LcConfigException( Exception ):
    pass

class Sync( object ):
    def __init__( self, oid, apiKey ):
        self._confVersion = 2
        self._oid = oid
        self._apiKey = apiKey
        self._man = Manager( self._oid, self._apiKey )

    def _coreRuleContent( self, rule ):
        return { k : v for k, v in rule.items() if k in ( 'name', 'detect', 'respond', 'namespace' ) }

    def _coreOutputContent( self, output ):
        return { k : v for k, v in output.items() if k != 'name' }

    def _coreIntegrityContent( self, rule ):
        rule = { k : v for k, v in rule.items() if k not in ( 'by', 'updated' ) }
        rule[ 'tags' ] = rule[ 'filters' ][ 'tags' ]
        rule[ 'platforms' ] = rule[ 'filters' ][ 'platforms' ]
        del( rule[ 'filters' ] )
        return rule

    def _coreLoggingContent( self, rule ):
        rule = { k : v for k, v in rule.items() if k not in ( 'by', 'updated' ) }
        rule[ 'tags' ] = rule[ 'filters' ][ 'tags' ]
        rule[ 'platforms' ] = rule[ 'filters' ][ 'platforms' ]
        del( rule[ 'filters' ] )
        return rule

    def _coreExfilContent( self, rule ):
        rule = { k : v for k, v in rule.items() if k not in ( 'by', 'updated' ) }
        rule[ 'tags' ] = rule[ 'filters' ][ 'tags' ]
        rule[ 'platforms' ] = rule[ 'filters' ][ 'platforms' ]
        del( rule[ 'filters' ] )
        return rule

    def _isJsonEqual( self, a, b ):
        if json.dumps( a, sort_keys = True ) != json.dumps( b, sort_keys = True ):
            return False

        return True

    def fetch( self, toConfigFile, isNoRules = False, isNoOutputs = False, isNoIntegrity = False, isNoLogging = False, isNoExfil = False ):
        '''Retrieves the effective configuration in the cloud to a local config file.

        Args:
            toConfigFile (str): the path to the local config file.
        '''
        toConfigFile = os.path.abspath( toConfigFile )
        asConf = { 'version' : self._confVersion }
        if not isNoRules:
            rules = {}
            # Check which namespaces we have access to.
            availableNamespaces = []
            if self._man.testAuth( permissions = [ 'dr.list' ] ):
                availableNamespaces.append( 'general' )
            if self._man.testAuth( permissions = [ 'dr.list.managed' ] ):
                availableNamespaces.append( 'managed' )

            # Fetch the rules from all the namespaces we have access to.
            for namespace in availableNamespaces:
                rules.update( self._man.rules( namespace = namespace ) )

            for ruleName, rule in list( rules.items() ):
                # Special rules from replicants are ignored.
                if ruleName.startswith( '__' ):
                    del( rules[ ruleName ] )
                    continue
                rules[ ruleName ] = self._coreRuleContent( rule )
            asConf[ 'rules' ] = rules
        if not isNoOutputs:
            outputs = self._man.outputs()
            for outputName, output in outputs.items():
                outputs[ outputName ] = self._coreOutputContent( output )
            asConf[ 'outputs' ] = outputs
        if not isNoIntegrity:
            integrityRules = Integrity( self._man ).getRules()
            for ruleName, rule in integrityRules.items():
                integrityRules[ ruleName ] = self._coreIntegrityContent( rule )
            asConf[ 'integrity' ] = integrityRules
        if not isNoLogging:
            loggingRules = Logging( self._man ).getRules()
            for ruleName, rule in loggingRules.items():
                loggingRules[ ruleName ] = self._coreLoggingContent( rule )
            asConf[ 'logging' ] = loggingRules
        if not isNoExfil:
            exfilRules = Exfil( self._man ).getRules()
            for ruleName, rule in exfilRules[ 'watch' ].items():
                exfilRules[ 'watch' ][ ruleName ] = self._coreExfilContent( rule )
            for ruleName, rule in exfilRules[ 'list' ].items():
                exfilRules[ 'list' ][ ruleName ] = self._coreExfilContent( rule )
            asConf[ 'exfil' ] = exfilRules
        with open( toConfigFile, 'wb' ) as f:
            f.write( yaml.safe_dump( asConf, default_flow_style = False ).encode() )

    def push( self, fromConfigFile, isForce = False, isDryRun = False, isNoRules = False, isNoOutputs = False, isNoIntegrity = False, isNoLogging = False, isNoExfil = False ):
        '''Apply the configuratiion in a local config file to the effective configuration in the cloud.

        Args:
            fromConfigFile (str): the path to the config file.
            isForce (boolean): if True will remove configurations in the cloud that are not present in the local file.
            isDryRun (boolean): if True will only simulate the effect of a push.

        Returns:
            a generator of changes as tuple (changeType, dataType, dataName).
        '''
        fromConfigFile = os.path.abspath( fromConfigFile )

        # Config files are always evaluated relative to the current one.
        contextPath = os.path.dirname( fromConfigFile )
        currentPath = os.getcwd()
        os.chdir( contextPath )

        # This function also does the bulk of the validation.
        asConf = self._loadEffectiveConfig( fromConfigFile )

        # Revert the previous CWD.
        os.chdir( currentPath )

        if not isNoRules:
            # Check all the namespaces we have access to.
            availableNamespaces = []
            if self._man.testAuth( permissions = [ 'dr.list' ] ):
                availableNamespaces.append( 'general' )
            if self._man.testAuth( permissions = [ 'dr.list.managed' ] ):
                availableNamespaces.append( 'managed' )

            # Get the current rules, we will try not to push for no reason.
            currentRules = {}
            for namespace in availableNamespaces:
                currentRules.update( { k : self._coreRuleContent( v ) for k, v in self._man.rules( namespace = namespace ).items() } )

            # Start by adding the rules with isReplace.
            for ruleName, rule in asConf.get( 'rules', {} ).items():
                rule = self._coreRuleContent( rule )
                ruleNamespace = rule.get( 'namespace', 'general' )
                # Check to see if it is already in the current rules and in the right format.
                previousNamespace = None
                if ruleName in currentRules:
                    previousNamespace = currentRules[ ruleName ].get( 'namespace', 'general' )
                    if ( self._isJsonEqual( rule[ 'detect' ], currentRules[ ruleName ][ 'detect' ] ) and
                         self._isJsonEqual( rule[ 'respond' ], currentRules[ ruleName ][ 'respond' ] ) and
                         ruleNamespace == previousNamespace ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'rule', ruleName )
                        continue
                if 'test' == ruleName:
                    print( currentRules[ ruleName ] )
                    print( rule )
                if not isDryRun:
                    if previousNamespace is not None and ruleNamespace != previousNamespace:
                        # Looks like the rule changed namespace.
                        self._man.del_rule( ruleName, namespace = previousNamespace )
                    self._man.add_rule( ruleName, rule[ 'detect' ], rule[ 'respond' ], isReplace = True, namespace = ruleNamespace )
                yield ( '+', 'rule', ruleName )

            # If we are not told to isForce, this is it.
            if isForce:
                # Check all the namespaces we have access to.
                currentRules = {}
                for namespace in availableNamespaces:
                    currentRules.update( self._man.rules( namespace = namespace ) )
                # Now if isForce was specified, list existing rules and remove the ones
                # not in our list.
                for ruleName, rule in currentRules.items():
                    # Ignore special replicant rules.
                    if ruleName.startswith( '__' ):
                        continue
                    if ruleName not in asConf[ 'rules' ]:
                        if not isDryRun:
                            self._man.del_rule( ruleName, namespace = rule.get( 'namespace', 'general' ) )
                        yield ( '-', 'rule', ruleName )

        if not isNoOutputs:
            # Get the current outputs, we will try not to push for no reason.
            currentOutputs = { k : self._coreOutputContent( v ) for k, v in self._man.outputs().items() }

            for outputName, output in asConf.get( 'outputs', {} ).items():
                if outputName in currentOutputs:
                    if self._isJsonEqual( output, currentOutputs[ outputName ] ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'output', outputName )
                        continue
                if not isDryRun:
                    self._man.add_output( outputName, output[ 'module' ], output[ 'for' ], **{ k : v for k, v in output.items() if k not in ( 'module', 'for' ) } )
                yield ( '+', 'output', outputName )

            if isForce:
                # Now if isForce was specified, list the existing outputs and remove the ones
                # not in our list.
                for outputName, output in self._man.outputs().items():
                    if outputName not in asConf[ 'outputs' ]:
                        if not isDryRun:
                            self._man.del_output( outputName )
                        yield ( '-', 'output', outputName )

        if not isNoIntegrity:
            integrityReplicant = Integrity( self._man )
            currentIntegrityRules = { k : self._coreIntegrityContent( v ) for k, v in integrityReplicant.getRules().items() }

            for ruleName, rule in asConf.get( 'integrity', {} ).items():
                if ruleName in currentIntegrityRules:
                    if self._isJsonEqual( rule, currentIntegrityRules[ ruleName ] ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'integrity', ruleName )
                        continue
                if not isDryRun:
                    integrityReplicant.addRule( ruleName,
                                                patterns = rule[ 'patterns' ],
                                                tags = rule.get( 'tags', [] ),
                                                platforms = rule.get( 'platforms', [] ) )
                yield ( '+', 'integrity', ruleName )

            if isForce:
                # Now if isForce was specified, list the existing rules and remove the ones
                # not in our list.
                for ruleName, rule in integrityReplicant.getRules().items():
                    if ruleName not in asConf[ 'integrity' ]:
                        if not isDryRun:
                            integrityReplicant.removeRule( ruleName )
                        yield ( '-', 'integrity', ruleName )

        if not isNoLogging:
            loggingReplicant = Logging( self._man )
            currentLoggingRules = { k : self._coreLoggingContent( v ) for k, v in loggingReplicant.getRules().items() }
            for ruleName, rule in asConf.get( 'logging', {} ).items():
                if ruleName in currentLoggingRules:
                    if self._isJsonEqual( rule, currentLoggingRules[ ruleName ] ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'logging', ruleName )
                        continue
                if not isDryRun:
                    loggingReplicant.addRule( ruleName,
                                              patterns = rule[ 'patterns' ],
                                              tags = rule.get( 'tags', [] ),
                                              platforms = rule.get( 'platforms', [] ) )
                yield ( '+', 'logging', ruleName )

            if isForce:
                # Now if isForce was specified, list the existing rules and remove the ones
                # not in our list.
                for ruleName, rule in loggingReplicant.getRules().items():
                    if ruleName not in asConf[ 'logging' ]:
                        if not isDryRun:
                            loggingReplicant.removeRule( ruleName )
                        yield ( '-', 'logging', ruleName )

        if not isNoExfil:
            exfilReplicant = Exfil( self._man )
            currentExfilRules = exfilReplicant.getRules()
            for ruleName, rule in asConf.get( 'exfil', {} ).get( 'watch', {} ).items():
                if ruleName in currentExfilRules.get( 'watch', {} ):
                    if self._isJsonEqual( rule, self._coreExfilContent( currentExfilRules[ 'watch' ][ ruleName ] ) ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'exfil-watch', ruleName )
                        continue
                if not isDryRun:
                    exfilReplicant.addWatchRule( ruleName,
                                                 event = rule[ 'event' ],
                                                 operator = rule[ 'operator' ],
                                                 value = rule[ 'value' ],
                                                 path = rule[ 'path' ],
                                                 tags = rule.get( 'tags', [] ),
                                                 platforms = rule.get( 'platforms', [] ) )
                yield ( '+', 'exfil-watch', ruleName )

            for ruleName, rule in asConf.get( 'exfil', {} ).get( 'list', {} ).items():
                if ruleName in currentExfilRules.get( 'list', {} ):
                    if self._isJsonEqual( rule, self._coreExfilContent( currentExfilRules[ 'list' ][ ruleName ] ) ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'exfil-list', ruleName )
                        continue
                if not isDryRun:
                    exfilReplicant.addEventRule( ruleName,
                                                 events = rule[ 'events' ],
                                                 tags = rule.get( 'tags', [] ),
                                                 platforms = rule.get( 'platforms', [] ) )
                yield ( '+', 'exfil-list', ruleName )

            if isForce:
                # Now if isForce was specified, list the existing rules and remove the ones
                # not in our list.
                for ruleName, rule in exfilReplicant.getRules().get( 'watch', {} ).items():
                    if ruleName not in asConf[ 'exfil' ].get( 'watch', {} ):
                        if not isDryRun:
                            exfilReplicant.removeWatchRule( ruleName )
                        yield ( '-', 'exfil-watch', ruleName )
                for ruleName, rule in exfilReplicant.getRules().get( 'list', {} ).items():
                    if ruleName not in asConf[ 'exfil' ].get( 'list', {} ):
                        if not isDryRun:
                            exfilReplicant.removeEventRule( ruleName )
                        yield ( '-', 'exfil-list', ruleName )

    def _loadEffectiveConfig( self, configFile ):
        configFile = os.path.abspath( configFile )
        with open( configFile, 'rb' ) as f:
            asConf = yaml.safe_load( f.read().decode() )
        if 'version' not in asConf:
            raise LcConfigException( 'Version not found.' )
        if self._confVersion < asConf[ 'version' ]:
            raise LcConfigException( 'Version not supported.' )

        includes = asConf.get( 'include', [] )
        if _isStringCompat( includes ):
            includes = [ includes ]
        for include in includes:
            if not _isStringCompat( include ):
                raise LcConfigException( 'Include should be a string, not %s' % ( str( type( include ) ), ) )
            # Config files are always evaluated relative to the current one.
            contextPath = os.path.dirname( configFile )
            currentPath = os.getcwd()
            os.chdir( contextPath )

            subConf = self._loadEffectiveConfig( include )

            # Revert the previous CWD.
            os.chdir( currentPath )

            for cat in ( 'rules', 'outputs' ):
                subCat = subConf.get( cat, None )
                if subCat is not None:
                    asConf.setdefault( cat, {} ).update( subCat )

        return asConf

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie.io sync' )
    parser.add_argument( 'action',
                         type = lambda x: str( x ).lower().strip(),
                         help = 'the action to perform, one of "fetch" or "push".' )
    parser.add_argument( '-o', '--oid',
                         type = lambda x: str( uuid.UUID( x.strip() ) ),
                         required = False,
                         dest = 'oid',
                         help = 'the OID to authenticate as, if not specified global creds will be used.' )
    parser.add_argument( '-f', '--force',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isForce',
                         help = 'if specified, in a push will remove all rules not in the config file' )
    parser.add_argument( '--dry-run',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isDryRun',
                         help = 'if specified, in a push simulates the push without making any changes.' )
    parser.add_argument( '--no-rules',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isNoRules',
                         help = 'if specified, ignore D&R rules from operations' )
    parser.add_argument( '--no-outputs',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isNoOutputs',
                         help = 'if specified, ignore Outputs from operations' )
    parser.add_argument( '--no-integrity',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isNoIntegrity',
                         help = 'if specified, ignore Integrity Replicants from operations' )
    parser.add_argument( '--no-logging',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isNoLogging',
                         help = 'if specified, ignore Logging Replicants from operations' )
    parser.add_argument( '--no-exfil',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isNoExfil',
                         help = 'if specified, ignore Exfil Replicants from operations' )
    parser.add_argument( '-c', '--config',
                         type = str,
                         default = 'LCConf',
                         required = False,
                         dest = 'config',
                         help = 'path to the LCConf file to use' )
    parser.add_argument( '-k', '--api-key',
                         type = str,
                         default = None,
                         required = False,
                         dest = 'apiKey',
                         help = 'path to the file holding your API Key, or "-" to consume it from STDIN' )
    args = parser.parse_args()

    if args.isDryRun:
        print( '!!! DRY RUN !!!' )
    if args.isNoRules:
        print( '!!! NO RULES !!!' )
    if args.isNoOutputs:
        print( '!!! NO OUTPUTS !!!' )
    if args.isNoIntegrity:
        print( '!!! NO INTEGRITY REPLICANT !!!' )
    if args.isNoLogging:
        print( '!!! NO LOGGING REPLICANT !!!' )
    if args.isNoExfil:
        print( '!!! NO EXFIL REPLICANT !!!' )

    if args.apiKey is not None:
        secretKey = args.apiKey.strip()
        if '-' == secretKey:
            print( "Using API Key from STDIN" )
            if _IS_PYTHON_2:
                secretKey = raw_input().strip()
            else:
                secretKey = input().strip()
        else:
            secretKey = os.path.abspath( secretKey )
            print( "Using API Key in: %s" % secretKey )
            with open( secretKey, 'rb' ) as f:
                secretKey = f.read().decode().strip()
    else:
        secretKey = None

    if args.action not in ( 'fetch', 'push' ):
        print( "Action %s is not supported." % args.action )
        sys.exit( 1 )

    s = Sync( args.oid, secretKey )

    if 'fetch' == args.action:
        s.fetch( args.config, isNoRules = args.isNoRules, isNoOutputs = args.isNoOutputs, isNoIntegrity = args.isNoIntegrity, isNoLogging = args.isNoLogging, isNoExfil = args.isNoExfil )
    elif 'push' == args.action:
        for modification, category, element in s.push( args.config, isForce = args.isForce, isDryRun = args.isDryRun, isNoRules = args.isNoRules, isNoOutputs = args.isNoOutputs, isNoIntegrity = args.isNoIntegrity, isNoLogging = args.isNoLogging, isNoExfil = args.isNoExfil ):
            print( '%s %s %s' % ( modification, category, element ) )