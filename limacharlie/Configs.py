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

class Configs( object ):
    '''Configs object to fetch and apply configs to and from organizations.'''

    def __init__( self, oid = None, env = None, manager = None ):
        '''Create a Configs object.

        Args:
            oid (str): organization ID to operate on.
            env (str): environment name to use.
            manager (limacharlie.Manager): Manager object to use instead.
        '''

        self._confVersion = 3
        if manager is None:
            self._man = Manager( oid = oid, environment = env )
        else:
            self._man = manager

        self._configRoots = {
            'rules',
            'outputs',
            'resources',
            'integrity',
            'fps',
            'exfil',
            'artifact',
        }

    def _coreRuleContent( self, rule ):
        return { k : v for k, v in rule.items() if k in ( 'name', 'detect', 'respond', 'namespace' ) }

    def _coreFPContent( self, rule ):
        return { k : v for k, v in rule.items() if k in ( 'name', 'data' ) }

    def _coreOutputContent( self, output ):
        return { k : v for k, v in output.items() if k not in ( 'name', 'oid', 'by' ) }

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

    def _ignoreLockErrors( self, e, isIgnoreInaccessible ):
        if not isIgnoreInaccessible:
            return False
        if 'lock' in str( e ).lower():
            return True
        return False

    def fetch( self, toConfigFile, isRules = False, isFPs = False, isOutputs = False, isIntegrity = False, isArtifact = False, isExfil = False, isResources = False ):
        '''Retrieves the effective configuration in the cloud to a local config file.

        Args:
            toConfigFile (str, dict): the path to the local config file or dict where to store config.
        '''
        if not isinstance( toConfigFile, dict ):
            toConfigFile = os.path.abspath( toConfigFile )
            asConf = { 'version' : self._confVersion }
        else:
            asConf = toConfigFile
        if isRules:
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
                # Special rules from services are ignored.
                if ruleName.startswith( '__' ):
                    del( rules[ ruleName ] )
                    continue
                rules[ ruleName ] = self._coreRuleContent( rule )
            asConf[ 'rules' ] = rules
        if isFPs:
            rules = {}
            fps = self._man.fps()

            for ruleName, rule in list( fps.items() ):
                rules[ ruleName ] = self._coreFPContent( rule )
            asConf[ 'fps' ] = rules
        if isOutputs:
            outputs = self._man.outputs()
            for outputName, output in list( outputs.items() ):
                if output.get( 'is_delete_on_failure', 'false' ) == 'true':
                    # Delete on failure is associated with temporary
                    # outputs so we won't consider them.
                    outputs.pop( outputName )
                    continue
                outputs[ outputName ] = self._coreOutputContent( output )
            asConf[ 'outputs' ] = outputs
        if isIntegrity:
            integrityRules = Integrity( self._man ).getRules()
            for ruleName, rule in integrityRules.items():
                integrityRules[ ruleName ] = self._coreIntegrityContent( rule )
            asConf[ 'integrity' ] = integrityRules
        if isArtifact:
            artifactRules = Logging( self._man ).getRules()
            for ruleName, rule in artifactRules.items():
                artifactRules[ ruleName ] = self._coreLoggingContent( rule )
            asConf[ 'artifact' ] = artifactRules
        if isExfil:
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
        if isResources:
            asConf[ 'resources' ] = self._man.getSubscriptions()
            # Translate the replicant entry to service.
            for resType, resources in asConf[ 'resources' ].items():
                if resType != 'replicant':
                    continue
                asConf[ 'resources' ][ 'service' ] = asConf[ 'resources' ][ 'replicant' ]
                asConf[ 'resources' ].pop( 'replicant' )
                break
        if not isinstance( toConfigFile, dict ):
            with open( toConfigFile, 'wb' ) as f:
                f.write( yaml.safe_dump( asConf, default_flow_style = False ).encode() )

    def push( self, fromConfigFile, isForce = False, isDryRun = False, isIgnoreInaccessible = False, isRules = False, isFPs = False, isOutputs = False, isIntegrity = False, isArtifact = False, isExfil = False, isResources = False ):
        '''Apply the configuratiion in a local config file to the effective configuration in the cloud.

        Args:
            fromConfigFile (str/dict): the path to the config file or dict of a config file content.
            isForce (boolean): if True will remove configurations in the cloud that are not present in the local file.
            isDryRun (boolean): if True will only simulate the effect of a push.
            isIgnoreInaccessible (boolean): if True, ignore inaccessible resources (locked) even when isForce is True.
            isRules (boolean): if True, push D&R rules.
            isFPs (boolean): if True, push False Positive rules.
            isOutputs (boolean): if True, push Outputs.
            isIntegrity (boolean): if True, push Integrity rules.
            isArtifact (boolean): if True, push Artifact rules.
            isExfil (boolean): if True, push Exfil rules.
            isResources (boolean): if True, push Resource subscriptions.

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

        if isResources:
            currentResources = self._man.getSubscriptions()
            for cat, confResources in asConf.get( 'resources', {} ).items():
                if cat == 'service':
                    # Alias Service to Replicant
                    cat = 'replicant'
                for resName in confResources:
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
                for cat, catResources in currentResources.items():
                    for resName in catResources:
                        internalCat = cat
                        if internalCat == 'replicant':
                            # Alias replicant to service
                            internalCat = 'service'
                        if resName not in asConf.get( 'resources', {} ).get( internalCat, [] ):
                            fullResName = '%s/%s' % ( cat, resName )
                            if not isDryRun:
                                self._man.unsubscribeFromResource( fullResName )
                            yield ( '-', 'resource', fullResName )

        if isRules:
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
                    try:
                        if previousNamespace is not None and ruleNamespace != previousNamespace:
                            # Looks like the rule changed namespace.
                            self._man.del_rule( ruleName, namespace = previousNamespace )
                        self._man.add_rule( ruleName, rule[ 'detect' ], rule[ 'respond' ], isReplace = True, namespace = ruleNamespace )
                    except Exception as e:
                        if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                            raise
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
                    # Ignore special service rules.
                    if ruleName.startswith( '__' ):
                        continue
                    if ruleName not in asConf.get( 'rules', {} ):
                        if not isDryRun:
                            try:
                                self._man.del_rule( ruleName, namespace = rule.get( 'namespace', 'general' ) )
                            except Exception as e:
                                if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                                    raise
                        yield ( '-', 'rule', ruleName )

        if isFPs:
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
                    try:
                        self._man.add_fp( ruleName, rule[ 'data' ], isReplace = True )
                    except Exception as e:
                        if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                            raise
                yield ( '+', 'fp', ruleName )

            # If we are not told to isForce, this is it.
            if isForce:
                currentRules = self._man.fps()

                # Now if isForce was specified, list existing rules and remove the ones
                # not in our list.
                for ruleName, rule in currentRules.items():
                    # Ignore special service rules.
                    if ruleName not in asConf.get( 'fps', {} ):
                        if not isDryRun:
                            try:
                                self._man.del_fp( ruleName )
                            except Exception as e:
                                if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                                    raise
                        yield ( '-', 'fp', ruleName )

        if isOutputs:
            # Get the current outputs, we will try not to push for no reason.
            currentOutputs = { k : self._coreOutputContent( v ) for k, v in self._man.outputs().items() }

            for outputName, output in asConf.get( 'outputs', {} ).items():
                if outputName in currentOutputs:
                    if self._isJsonEqual( output, currentOutputs[ outputName ] ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'output', outputName )
                        continue
                if not isDryRun:
                    try:
                        self._man.add_output( outputName, output[ 'module' ], output[ 'for' ], **{ k : v for k, v in output.items() if k not in ( 'module', 'for' ) } )
                    except Exception as e:
                        if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                            raise
                yield ( '+', 'output', outputName )

            if isForce:
                # Now if isForce was specified, list the existing outputs and remove the ones
                # not in our list.
                for outputName, output in self._man.outputs().items():
                    if output.get( 'is_delete_on_failure', 'false' ) == 'true':
                        # Delete on failure is associated with temporary
                        # outputs so we won't consider them.
                        continue
                    if outputName not in asConf.get( 'outputs', {} ):
                        if not isDryRun:
                            try:
                                self._man.del_output( outputName )
                            except Exception as e:
                                if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                                    raise
                        yield ( '-', 'output', outputName )

        if isIntegrity:
            integrityService = Integrity( self._man )
            currentIntegrityRules = { k : self._coreIntegrityContent( v ) for k, v in integrityService.getRules().items() }

            for ruleName, rule in asConf.get( 'integrity', {} ).items():
                if ruleName in currentIntegrityRules:
                    if self._isJsonEqual( rule, currentIntegrityRules[ ruleName ] ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'integrity', ruleName )
                        continue
                if not isDryRun:
                    try:
                        integrityService.addRule( ruleName,
                                                    patterns = rule[ 'patterns' ],
                                                    tags = rule.get( 'tags', [] ),
                                                    platforms = rule.get( 'platforms', [] ) )
                    except Exception as e:
                        if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                            raise
                yield ( '+', 'integrity', ruleName )

            if isForce:
                # Now if isForce was specified, list the existing rules and remove the ones
                # not in our list.
                for ruleName, rule in integrityService.getRules().items():
                    if ruleName not in asConf.get( 'integrity', {} ):
                        if not isDryRun:
                            try:
                                integrityService.removeRule( ruleName )
                            except Exception as e:
                                if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                                    raise
                        yield ( '-', 'integrity', ruleName )

        if isArtifact:
            artifactService = Logging( self._man )
            currentartifactRules = { k : self._coreLoggingContent( v ) for k, v in artifactService.getRules().items() }
            for ruleName, rule in asConf.get( 'artifact', {} ).items():
                if ruleName in currentartifactRules:
                    if self._isJsonEqual( rule, currentartifactRules[ ruleName ] ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'artifact', ruleName )
                        continue
                if not isDryRun:
                    try:
                        artifactService.addRule( ruleName,
                                                patterns = rule[ 'patterns' ],
                                                tags = rule.get( 'tags', [] ),
                                                platforms = rule.get( 'platforms', [] ),
                                                isDeleteAfter = rule.get( 'is_delete_after', False ),
                                                isIgnoreCert = rule.get( 'is_ignore_cert', False ) )
                    except Exception as e:
                        if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                            raise
                yield ( '+', 'artifact', ruleName )

            if isForce:
                # Now if isForce was specified, list the existing rules and remove the ones
                # not in our list.
                for ruleName, rule in artifactService.getRules().items():
                    if ruleName not in asConf.get( 'artifact', {} ):
                        if not isDryRun:
                            try:
                                artifactService.removeRule( ruleName )
                            except Exception as e:
                                if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                                    raise
                        yield ( '-', 'artifact', ruleName )

        if isExfil:
            exfilService = Exfil( self._man )
            currentExfilRules = exfilService.getRules()
            for ruleName, rule in asConf.get( 'exfil', {} ).get( 'watch', {} ).items():
                if ruleName in currentExfilRules.get( 'watch', {} ):
                    if self._isJsonEqual( rule, self._coreExfilContent( currentExfilRules[ 'watch' ][ ruleName ] ) ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'exfil-watch', ruleName )
                        continue
                if not isDryRun:
                    try:
                        exfilService.addWatchRule( ruleName,
                                                    event = rule[ 'event' ],
                                                    operator = rule[ 'operator' ],
                                                    value = rule[ 'value' ],
                                                    path = rule[ 'path' ],
                                                    tags = rule.get( 'tags', [] ),
                                                    platforms = rule.get( 'platforms', [] ) )
                    except Exception as e:
                        if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                            raise
                yield ( '+', 'exfil-watch', ruleName )

            for ruleName, rule in asConf.get( 'exfil', {} ).get( 'list', {} ).items():
                if ruleName in currentExfilRules.get( 'list', {} ):
                    if self._isJsonEqual( rule, self._coreExfilContent( currentExfilRules[ 'list' ][ ruleName ] ) ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'exfil-list', ruleName )
                        continue
                if not isDryRun:
                    try:
                        exfilService.addEventRule( ruleName,
                                                    events = rule[ 'events' ],
                                                    tags = rule.get( 'tags', [] ),
                                                    platforms = rule.get( 'platforms', [] ) )
                    except Exception as e:
                        if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                            raise
                yield ( '+', 'exfil-list', ruleName )

            if isForce:
                # Now if isForce was specified, list the existing rules and remove the ones
                # not in our list.
                for ruleName, rule in exfilService.getRules().get( 'watch', {} ).items():
                    if ruleName not in asConf.get( 'exfil', {} ).get( 'watch', {} ):
                        if not isDryRun:
                            try:
                                exfilService.removeWatchRule( ruleName )
                            except Exception as e:
                                if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                                    raise
                        yield ( '-', 'exfil-watch', ruleName )
                for ruleName, rule in exfilService.getRules().get( 'list', {} ).items():
                    if ruleName not in asConf[ 'exfil' ].get( 'list', {} ):
                        if not isDryRun:
                            try:
                                exfilService.removeEventRule( ruleName )
                            except Exception as e:
                                if not self._ignoreLockErrors( e, isIgnoreInaccessible ):
                                    raise
                        yield ( '-', 'exfil-list', ruleName )

    def _loadEffectiveConfig( self, configFile ):
        configFile = os.path.abspath( configFile )
        with open( configFile, 'rb' ) as f:
            asConf = yaml.safe_load( f.read().decode() )
        if asConf is None:
            asConf = {}
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

            for cat in self._configRoots:
                subCat = subConf.get( cat, None )
                if subCat is not None:
                    # Check if this config is dictionaries
                    # or lists. They need to be updated differntly.
                    if len( subCat ) != 0 and isinstance( list( subCat.values() )[ 0 ], ( list, tuple ) ):
                        for k, v in subCat.items():
                            for val in v:
                                if val in asConf.setdefault( cat, {} ).setdefault( k, [] ):
                                    continue
                                asConf[ cat ][ k ].append( val )
                    else:
                        asConf.setdefault( cat, {} ).update( subCat )

        return asConf

def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie configs' )
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
    parser.add_argument( '-i', '--ignore-inaccessible',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isIgnoreInaccessible',
                         help = 'if specified, in a push will ignore inaccessible (locked) resources even if --force is specified' )
    parser.add_argument( '--dry-run',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isDryRun',
                         help = 'if specified, in a push simulates the push without making any changes.' )
    parser.add_argument( '--rules',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isRules',
                         help = 'if specified, apply D&R rules from operations' )
    parser.add_argument( '--fp',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isFPs',
                         help = 'if specified, apply False Psitive rules from operations' )
    parser.add_argument( '--outputs',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isOutputs',
                         help = 'if specified, apply Outputs from operations' )
    parser.add_argument( '--integrity',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isIntegrity',
                         help = 'if specified, apply Integrity Service from operations' )
    parser.add_argument( '--artifact',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isArtifact',
                         help = 'if specified, apply Artifact Service from operations' )
    parser.add_argument( '--exfil',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isExfil',
                         help = 'if specified, apply Exfil Service from operations' )
    parser.add_argument( '--resources',
                         required = False,
                         default = False,
                         action = 'store_true',
                         dest = 'isResources',
                         help = 'if specified, apply resource subscriptions from operations' )
    parser.add_argument( '-c', '--config',
                         type = str,
                         default = 'lc_conf.yaml',
                         required = False,
                         dest = 'config',
                         help = 'path to the lc_conf.yaml file to use' )
    args = parser.parse_args( sourceArgs )

    if args.isDryRun:
        print( '!!! DRY RUN !!!' )

    if args.action not in ( 'fetch', 'push' ):
        print( "Action %s is not supported." % args.action )
        sys.exit( 1 )

    s = Configs( oid = args.oid, env = args.environment )

    if 'fetch' == args.action:
        s.fetch( args.config, isRules = args.isRules, isFPs = args.isFPs, isOutputs = args.isOutputs, isIntegrity = args.isIntegrity, isArtifact = args.isArtifact, isExfil = args.isExfil, isResources = args.isResources )
    elif 'push' == args.action:
        for modification, category, element in s.push( args.config, isForce = args.isForce, isIgnoreInaccessible = args.isIgnoreInaccessible, isDryRun = args.isDryRun, isRules = args.isRules, isFPs = args.isFPs, isOutputs = args.isOutputs, isIntegrity = args.isIntegrity, isArtifact = args.isArtifact, isExfil = args.isExfil, isResources = args.isResources ):
            print( '%s %s %s' % ( modification, category, element ) )

if __name__ == '__main__':
    main()