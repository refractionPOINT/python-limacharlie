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
    '''Sync object to fetch and apply configs to and from organizations.'''

    def __init__( self, oid = None, env = None, manager = None ):
        '''Create a Sync object.

        Args:
            oid (str): organization ID to operate on.
            env (str): environment name to use.
            manager (limacharlie.Manager): Manager object to use instead.
        '''

        self._confVersion = 2
        if manager is None:
            self._man = Manager( oid = oid, environment = env )
        else:
            self._man = manager

    def _coreRuleContent( self, rule ):
        return { k : v for k, v in rule.items() if k in ( 'name', 'detect', 'respond', 'namespace' ) }

    def _coreFPContent( self, rule ):
        return { k : v for k, v in rule.items() if k in ( 'name', 'data' ) }

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

    def fetch( self, toConfigFile, isNoRules = False, isNoFPs = False, isNoOutputs = False, isNoIntegrity = False, isNoLogging = False, isNoExfil = False, isNoResources = False ):
        '''Retrieves the effective configuration in the cloud to a local config file.

        Args:
            toConfigFile (str, dict): the path to the local config file or dict where to store config.
        '''
        if not isinstance( toConfigFile, dict ):
            toConfigFile = os.path.abspath( toConfigFile )
            asConf = { 'version' : self._confVersion }
        else:
            asConf = toConfigFile
        if not isNoRules:
            rules = {}
            # Check which namespaces we have access to.
            availableNamespaces = []
            if self._man.testAuth( permissions = [ 'dr.list' ] ):
                availableNamespaces.append( 'general' )
            if self._man.testAuth( permissions = [ 'dr.list.managed' ] ):
                availableNamespaces.append( 'managed' )
            if self._man.testAuth( permissions = [ 'dr.list.replicant' ] ):
                availableNamespaces.append( 'replicant' )

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
        if not isNoFPs:
            rules = {}
            fps = self._man.fps()

            for ruleName, rule in list( fps.items() ):
                rules[ ruleName ] = self._coreFPContent( rule )
            asConf[ 'fps' ] = rules
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
                if '' == rule[ 'operator' ]:
                    # This is a [secret] rule, let's not mirror it since
                    # it is handled by a Service.
                    continue
                exfilRules[ 'watch' ][ ruleName ] = self._coreExfilContent( rule )
            for ruleName, rule in exfilRules[ 'list' ].items():
                exfilRules[ 'list' ][ ruleName ] = self._coreExfilContent( rule )
            asConf[ 'exfil' ] = exfilRules
        if not isNoResources:
            asConf[ 'resources' ] = self._man.getSubscriptions()
        if not isinstance( toConfigFile, dict ):
            with open( toConfigFile, 'wb' ) as f:
                f.write( yaml.safe_dump( asConf, default_flow_style = False ).encode() )

    def push( self, fromConfigFile, isForce = False, isDryRun = False, isNoRules = False, isNoFPs = False, isNoOutputs = False, isNoIntegrity = False, isNoLogging = False, isNoExfil = False, isNoResources = False ):
        '''Apply the configuratiion in a local config file to the effective configuration in the cloud.

        Users should favor using the "push<Type>()" convenience functions instead of the
        main "push()" function as they are safer to use in the event support for new
        data-types is added to the "push()" function.

        Args:
            fromConfigFile (str/dict): the path to the config file or dict of a config file content.
            isForce (boolean): if True will remove configurations in the cloud that are not present in the local file.
            isDryRun (boolean): if True will only simulate the effect of a push.

        Returns:
            a generator of changes as tuple (changeType, dataType, dataName).
        '''
        if isinstance( fromConfigFile, dict ):
            # The config is already in memory.
            asConf = fromConfigFile
        else:
            # Load the config file from disk.
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
            if self._man.testAuth( permissions = [ 'dr.list.replicant' ] ):
                availableNamespaces.append( 'replicant' )

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
                    if ruleName not in asConf.get( 'rules', {} ):
                        if not isDryRun:
                            self._man.del_rule( ruleName, namespace = rule.get( 'namespace', 'general' ) )
                        yield ( '-', 'rule', ruleName )

        if not isNoFPs:
            # Get the current rules, we will try not to push for no reason.
            currentRules = { k : self._coreFPContent( v ) for k, v in self._man.fps().items() }

            # Start by adding the rules with isReplace.
            for ruleName, rule in asConf.get( 'fps', {} ).items():
                rule = self._coreFPContent( rule )
                # Check to see if it is already in the current rules and in the right format.
                if ruleName in currentRules:
                    if self._isJsonEqual( rule[ 'data' ], currentRules[ ruleName ][ 'data' ] ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'fp', ruleName )
                        continue
                if not isDryRun:
                    self._man.add_fp( ruleName, rule[ 'data' ], isReplace = True )
                yield ( '+', 'fp', ruleName )

            # If we are not told to isForce, this is it.
            if isForce:
                currentRules = self._man.fps()

                # Now if isForce was specified, list existing rules and remove the ones
                # not in our list.
                for ruleName, rule in currentRules.items():
                    # Ignore special replicant rules.
                    if ruleName not in asConf.get( 'fps', {} ):
                        if not isDryRun:
                            self._man.del_fp( ruleName )
                        yield ( '-', 'fp', ruleName )

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
                    if outputName not in asConf.get( 'outputs', {} ):
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
                    if ruleName not in asConf.get( 'integrity', {} ):
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
                                              platforms = rule.get( 'platforms', [] ),
                                              isDeleteAfter = rule.get( 'is_delete_after', False ),
                                              isIgnoreCert = rule.get( 'is_ignore_cert', False ) )
                yield ( '+', 'logging', ruleName )

            if isForce:
                # Now if isForce was specified, list the existing rules and remove the ones
                # not in our list.
                for ruleName, rule in loggingReplicant.getRules().items():
                    if ruleName not in asConf.get( 'logging', {} ):
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
                    if ruleName not in asConf.get( 'exfil', {} ).get( 'watch', {} ):
                        if not isDryRun:
                            exfilReplicant.removeWatchRule( ruleName )
                        yield ( '-', 'exfil-watch', ruleName )
                for ruleName, rule in exfilReplicant.getRules().get( 'list', {} ).items():
                    if ruleName not in asConf[ 'exfil' ].get( 'list', {} ):
                        if not isDryRun:
                            exfilReplicant.removeEventRule( ruleName )
                        yield ( '-', 'exfil-list', ruleName )
        if not isNoResources:
            currentResources = self._man.getSubscriptions()
            for cat in asConf.get( 'resources', {} ):
                for resName in asConf.get( 'resources', {} )[ cat ]:
                    fullResName = '%s/%s' % ( cat, resName )
                    if resName not in currentResources.get( cat, [] ):
                        if not isDryRun:
                            self._man.subscribeToResource( fullResName )
                        yield ( '+', 'resource', fullResName )
                    else:
                        yield ( '=', 'resource', fullResName )
            # Only force "resources" if it is present in the config.
            # This avoids unexpected disabling of all configs.
            if isForce and 'resources' in asConf:
                for cat in currentResources:
                    for resName in currentResources[ cat ]:
                        if resName not in asConf.get( 'resources', {} ).get( cat, [] ):
                            fullResName = '%s/%s' % ( cat, resName )
                            if not isDryRun:
                                self._man.unsubscribeFromResource( fullResName )
                            yield ( '-', 'resource', fullResName )

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

    def pushRules( self, fromConfigFile, isForce = False, isDryRun = False ):
        '''Convenience function to push the D&R rules in a local config file to the effective configuration in the cloud.

        Args:
            fromConfigFile (str/dict): the path to the config file or dict of a config file content.
            isForce (boolean): if True will remove configurations in the cloud that are not present in the local file.
            isDryRun (boolean): if True will only simulate the effect of a push.

        Returns:
            a generator of changes as tuple (changeType, dataType, dataName).
        '''
        return list( self.push( fromConfigFile, isForce = isForce, isDryRun = isDryRun, isNoRules = False, isNoFPs = True, isNoOutputs = True, isNoIntegrity = True, isNoLogging = True, isNoExfil = True, isNoResources = True ) )

    def pushFPs( self, fromConfigFile, isForce = False, isDryRun = False ):
        '''Convenience function to push the FP rules in a local config file to the effective configuration in the cloud.

        Args:
            fromConfigFile (str/dict): the path to the config file or dict of a config file content.
            isForce (boolean): if True will remove configurations in the cloud that are not present in the local file.
            isDryRun (boolean): if True will only simulate the effect of a push.

        Returns:
            a generator of changes as tuple (changeType, dataType, dataName).
        '''
        return list( self.push( fromConfigFile, isForce = isForce, isDryRun = isDryRun, isNoRules = True, isNoFPs = False, isNoOutputs = True, isNoIntegrity = True, isNoLogging = True, isNoExfil = True, isNoResources = True ) )

    def pushOutputs( self, fromConfigFile, isForce = False, isDryRun = False ):
        '''Convenience function to push the outputs in a local config file to the effective configuration in the cloud.

        Args:
            fromConfigFile (str/dict): the path to the config file or dict of a config file content.
            isForce (boolean): if True will remove configurations in the cloud that are not present in the local file.
            isDryRun (boolean): if True will only simulate the effect of a push.

        Returns:
            a generator of changes as tuple (changeType, dataType, dataName).
        '''
        return list( self.push( fromConfigFile, isForce = isForce, isDryRun = isDryRun, isNoRules = True, isNoFPs = True, isNoOutputs = False, isNoIntegrity = True, isNoLogging = True, isNoExfil = True, isNoResources = True ) )

    def pushIntegrity( self, fromConfigFile, isForce = False, isDryRun = False ):
        '''Convenience function to push the Integrity configs in a local config file to the effective configuration in the cloud.

        Args:
            fromConfigFile (str/dict): the path to the config file or dict of a config file content.
            isForce (boolean): if True will remove configurations in the cloud that are not present in the local file.
            isDryRun (boolean): if True will only simulate the effect of a push.

        Returns:
            a generator of changes as tuple (changeType, dataType, dataName).
        '''
        return list( self.push( fromConfigFile, isForce = isForce, isDryRun = isDryRun, isNoRules = True, isNoFPs = True, isNoOutputs = True, isNoIntegrity = False, isNoLogging = True, isNoExfil = True, isNoResources = True ) )

    def pushLogging( self, fromConfigFile, isForce = False, isDryRun = False ):
        '''Convenience function to push the Logging configs in a local config file to the effective configuration in the cloud.

        Args:
            fromConfigFile (str/dict): the path to the config file or dict of a config file content.
            isForce (boolean): if True will remove configurations in the cloud that are not present in the local file.
            isDryRun (boolean): if True will only simulate the effect of a push.

        Returns:
            a generator of changes as tuple (changeType, dataType, dataName).
        '''
        return list( self.push( fromConfigFile, isForce = isForce, isDryRun = isDryRun, isNoRules = True, isNoFPs = True, isNoOutputs = True, isNoIntegrity = True, isNoLogging = False, isNoExfil = True, isNoResources = True ) )

    def pushExfil( self, fromConfigFile, isForce = False, isDryRun = False ):
        '''Convenience function to push the Exfil configs in a local config file to the effective configuration in the cloud.

        Args:
            fromConfigFile (str/dict): the path to the config file or dict of a config file content.
            isForce (boolean): if True will remove configurations in the cloud that are not present in the local file.
            isDryRun (boolean): if True will only simulate the effect of a push.

        Returns:
            a generator of changes as tuple (changeType, dataType, dataName).
        '''
        return list( self.push( fromConfigFile, isForce = isForce, isDryRun = isDryRun, isNoRules = True, isNoFPs = True, isNoOutputs = True, isNoIntegrity = True, isNoLogging = True, isNoExfil = False, isNoResources = True ) )

    def pushResources( self, fromConfigFile, isForce = False, isDryRun = False ):
        '''Convenience function to push the Resources configs in a local config file to the effective configuration in the cloud.

        Args:
            fromConfigFile (str/dict): the path to the config file or dict of a config file content.
            isForce (boolean): if True will remove configurations in the cloud that are not present in the local file.
            isDryRun (boolean): if True will only simulate the effect of a push.

        Returns:
            a generator of changes as tuple (changeType, dataType, dataName).
        '''
        return list( self.push( fromConfigFile, isForce = isForce, isDryRun = isDryRun, isNoRules = True, isNoFPs = True, isNoOutputs = True, isNoIntegrity = True, isNoLogging = True, isNoExfil = True, isNoResources = False ) )

def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie sync' )
    parser.add_argument( 'action',
                         type = lambda x: str( x ).lower().strip(),
                         help = 'the action to perform, one of "fetch" or "push".' )
    parser.add_argument( '-o', '--oid',
                         type = lambda x: str( uuid.UUID( x.strip() ) ),
                         required = False,
                         dest = 'oid',
                         default = None,
                         help = 'the OID to authenticate as, if not specified global creds will be used.' )
    parser.add_argument( '-e', '--environment',
                         type = str,
                         required = False,
                         dest = 'environment',
                         default = None,
                         help = 'the name of the LimaCharlie environment (as defined in ~/.limacharlie) to use, otherwise global creds will be used.' )
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
    parser.add_argument( '--no-fp',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isNoFPs',
                         help = 'if specified, ignore False Psitive rules from operations' )
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
    parser.add_argument( '--no-resources',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isNoResources',
                         help = 'if specified, ignore resource subscriptions from operations' )
    parser.add_argument( '-c', '--config',
                         type = str,
                         default = 'LCConf',
                         required = False,
                         dest = 'config',
                         help = 'path to the LCConf file to use' )
    args = parser.parse_args( sourceArgs )

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

    if args.action not in ( 'fetch', 'push' ):
        print( "Action %s is not supported." % args.action )
        sys.exit( 1 )

    s = Sync( oid = args.oid, env = args.environment )

    if 'fetch' == args.action:
        s.fetch( args.config, isNoRules = args.isNoRules, isNoFPs = args.isNoFPs, isNoOutputs = args.isNoOutputs, isNoIntegrity = args.isNoIntegrity, isNoLogging = args.isNoLogging, isNoExfil = args.isNoExfil, isNoResources = args.isNoResources )
    elif 'push' == args.action:
        for modification, category, element in s.push( args.config, isForce = args.isForce, isDryRun = args.isDryRun, isNoRules = args.isNoRules, isNoFPs = args.isNoFPs, isNoOutputs = args.isNoOutputs, isNoIntegrity = args.isNoIntegrity, isNoLogging = args.isNoLogging, isNoExfil = args.isNoExfil, isNoResources = args.isNoResources ):
            print( '%s %s %s' % ( modification, category, element ) )

if __name__ == '__main__':
    main()