from .Manager import Manager

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
        return { k : v for k, v in rule.iteritems() if k in ( 'name', 'detect', 'respond' ) }

    def _coreOutputContent( self, output ):
        return { k : v for k, v in output.iteritems() if k != 'name' }

    def _recursiveOrderDict( self, d ):
        if isinstance( d, list ) or isinstance( d, tuple ):
            return sorted( d )
        if isinstance( d, dict ):
            return sorted( { k : self._recursiveOrderDict( v ) for k, v in d.items() }.items() )
        return d

    def _isJsonEqual( self, a, b ):
        r1 = self._recursiveOrderDict( a )
        r2 = self._recursiveOrderDict( b )

        if json.dumps( r1 ) != json.dumps( r2 ):
            return False

        return True

    def fetch( self, toConfigFile, isNoRules = False, isNoOutputs = False ):
        '''Retrieves the effective configuration in the cloud to a local config file.

        Args:
            toConfigFile (str): the path to the local config file.
        '''
        toConfigFile = os.path.abspath( toConfigFile )
        asConf = { 'version' : self._confVersion }
        if not isNoRules:
            rules = self._man.rules()
            for ruleName, rule in rules.items():
                rules[ ruleName ] = self._coreRuleContent( rule )
            asConf[ 'rules' ] = rules
        if not isNoOutputs:
            outputs = self._man.outputs()
            for outputName, output in outputs.items():
                outputs[ outputName ] = self._coreOutputContent( output )
            asConf[ 'outputs' ] = outputs
        with open( toConfigFile, 'wb' ) as f:
            f.write( yaml.safe_dump( asConf, default_flow_style = False ) )

    def push( self, fromConfigFile, isForce = False, isDryRun = False, isNoRules = False, isNoOutputs = False ):
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
            # Get the current rules, we will try not to push for no reason.
            currentRules = { k : self._coreRuleContent( v ) for k, v in self._man.rules().iteritems() }

            # Start by adding the rules with isReplace.
            for ruleName, rule in asConf.get( 'rules', {} ).iteritems():
                rule = self._coreRuleContent( rule )
                # Check to see if it is already in the current rules and in the right format.
                if ruleName in currentRules:
                    if ( self._isJsonEqual( rule[ 'detect' ], currentRules[ ruleName ][ 'detect' ] ) and
                        self._isJsonEqual( rule[ 'respond' ], currentRules[ ruleName ][ 'respond' ] ) ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'rule', ruleName )
                        continue

                if not isDryRun:
                    self._man.add_rule( ruleName, rule[ 'detect' ], rule[ 'respond' ], isReplace = True )
                yield ( '+', 'rule', ruleName )

            # If we are not told to isForce, this is it.
            if isForce:
                # Now if isForce was specified, list existing rules and remove the ones
                # not in our list.
                for ruleName, rule in self._man.rules().iteritems():
                    if ruleName not in asConf[ 'rules' ]:
                        if not isDryRun:
                            self._man.del_rule( ruleName )
                        yield ( '-', 'rule', ruleName )

        if not isNoOutputs:
            # Get the current outputs, we will try not to push for no reason.
            currentOutputs = { k : self._coreOutputContent( v ) for k, v in self._man.outputs().iteritems() }

            for outputName, output in asConf.get( 'outputs', {} ).iteritems():
                if outputName in currentOutputs:
                    if self._isJsonEqual( output, currentOutputs[ outputName ] ):
                        # Exact same, no point in pushing.
                        yield ( '=', 'output', outputName )
                        continue
                if not isDryRun:
                    self._man.add_output( outputName, output[ 'module' ], output[ 'for' ], **{ k : v for k, v in output.iteritems() if k not in ( 'module', 'for' ) } )
                yield ( '+', 'output', outputName )

            if isForce:
                # Now if isForce was specified, list the existing outputs and remove the ones
                # not in our list.
                for outputName, output in self._man.outputs().iteritems():
                    if outputName not in asConf[ 'outputs' ]:
                        if not isDryRun:
                            self._man.del_output( outputName )
                        yield ( '-', 'output', outputName )

    def _loadEffectiveConfig( self, configFile ):
        configFile = os.path.abspath( configFile )
        with open( configFile, 'rb' ) as f:
            asConf = yaml.load( f.read() )
        if 'version' not in asConf:
            raise LcConfigException( 'Version not found.' )
        if self._confVersion < asConf[ 'version' ]:
            raise LcConfigException( 'Version not supported.' )

        includes = asConf.get( 'include', [] )
        if isinstance( includes, ( str, unicode ) ):
            includes = [ includes ]
        for include in includes:
            if not isinstance( include, ( str, unicode ) ):
                raise LcConfigException( 'Include should be a string, not %s' % ( str( type( include ) ), ) )
            # Config files are always evaluated relative to the current one.
            contextPath = os.path.dirname( configFile )
            currentPath = os.getcwd()
            os.chdir( contextPath )

            subConf = self._loadEffectiveConfig( include )

            # Revert the previous CWD.
            os.chdir( currentPath )

            for cat in ( 'rules', ):
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

    if args.apiKey is not None:
        secretKey = args.apiKey.strip()
        if '-' == secretKey:
            print( "Using API Key from STDIN" )
            secretKey = raw_input().strip()
        else:
            secretKey = os.path.abspath( secretKey )
            print( "Using API Key in: %s" % secretKey )
            with open( secretKey, 'rb' ) as f:
                secretKey = f.read().strip()
    else:
        secretKey = None

    if args.action not in ( 'fetch', 'push' ):
        print( "Action %s is not supported." % args.action )
        sys.exit( 1 )

    s = Sync( args.oid, secretKey )

    if 'fetch' == args.action:
        s.fetch( args.config, isNoRules = args.isNoRules, isNoOutputs = args.isNoOutputs )
    elif 'push' == args.action:
        for modification, category, element in s.push( args.config, isForce = args.isForce, isDryRun = args.isDryRun, isNoRules = args.isNoRules, isNoOutputs = args.isNoOutputs ):
            print( '%s %s %s' % ( modification, category, element ) )