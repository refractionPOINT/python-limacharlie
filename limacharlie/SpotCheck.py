from .Manager import Manager

# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

if _IS_PYTHON_2:
    from urllib2 import urlopen
    from Queue import Queue
else:
    from urllib.request import urlopen
    from queue import Queue

import threading
import time
import uuid
import traceback
import json
import base64
import sys

class SpotCheck( object ):
    '''Representation of the process of looking for various Indicators of Compromise on the fleet.'''

    def __init__( self, oid, secret_api_key, cb_check, cb_on_start_check = None, cb_on_check_done = None, cb_on_offline = None, cb_on_error = None, n_concurrent = 1, n_sec_between_online_checks = 60, extra_params = {}, is_windows = True, is_linux = True, is_macos = True, is_chrome = True, tags = None ):
        '''Perform a check for specific characteristics on all hosts matching some parameters.

        Args:
            oid (uuid str): the Organization ID, if None, global credentials will be used.
            secret_api_key (str): the secret API key, if None, global credentials will be used.
            cb_check (func(Sensor)): callback function for every matching sensor, implements main check logic, returns True when check is finalized.
            cb_on_check_done (func(Sensor)): callback when a sensor is done with a check.
            cb_on_start_check (func(Sensor)): callback when a sensor is starting evaluation.
            cb_on_offline (func(Sensor)): callback when a sensor is offline so checking is delayed.
            cb_on_error (func(Sensor, stackTrace)): callback when an error occurs while checking a sensor.
            n_concurrent (int): number of sensors that should be checked concurrently, defaults to 1.
            n_sec_between_online_checks (int): number of seconds to wait between attempts to check a sensor that is offline, default to 60.
            is_windows (boolean): if True checks apply to Windows sensors, defaults to True.
            is_linux (boolean): if True checks apply to Linux sensors, defaults to True.
            is_macos (boolean): if True checks apply to MacOS sensors, defaults to True.
            is_chrome (boolean): if True checks apply to Chrome sensors, defaults to True.
            tags (str): comma-seperated list of tags, sensors must have: either one tag with the "+" prefix, not include all tags with "-" prefix, or the sensor has all tags specified without prefix.
        '''
        self._cbCheck = cb_check
        self._cbOnCheckDone = cb_on_check_done
        self._cbOnStartCheck = cb_on_start_check
        self._cbOnOffline = cb_on_offline
        self._cbOnError = cb_on_error
        self._nConcurrent = n_concurrent
        self._nSecBetweenOnlineChecks = n_sec_between_online_checks

        self._isWindows = is_windows
        self._isLinux = is_linux
        self._isMacos = is_macos
        self._isChrome = is_chrome

        self._tags = []
        self._positiveTags = []
        self._negativeTags = []
        if tags is not None:
            for tag in tags:
                if tag.startswith( '+' ):
                    self._positiveTags.append( tag[1:] )
                elif tag.startswith( '-' ):
                    self._negativeTags.append( tag[1:] )
                else:
                    self._tags.append( tag )

        self._threads = []
        self._stopEvent = threading.Event()

        self._sensorsLeftToCheck = Queue()
        self._lock = threading.Lock()
        self._pendingReCheck = 0

        self._lc = Manager( oid, secret_api_key, inv_id = 'spotcheck-%s' % str( uuid.uuid4() )[ : 4 ], is_interactive = True, extra_params = extra_params )

    def start( self ):
        '''Start the SpotCheck process, returns immediately.
        '''
        # We start by listing all the sensors in the org using paging.
        for sensor in self._lc.sensors():
            self._sensorsLeftToCheck.put( sensor )

        # Now that we have a list of sensors, we'll spawn n_concurrent spot checks,
        for _ in range( self._nConcurrent ):
            t = threading.Thread( target = self._performSpotChecks )
            self._threads.append( t )
            t.start()

        # Done, the threads will do the checks.

    def stop( self ):
        '''Stop the SpotCheck process, returns once activity has stopped.
        '''
        self._stopEvent.set()
        self.wait()

    def wait( self, timeout = None ):
        '''Wait for SpotCheck to be complete, or timeout occurs.

        Args:
            timeout (float): if specified, number of seconds to wait for SpotCheck to complete.

        Returns:
            True if SpotCheck is finished, False if a timeout was specified and reached before the SpotCheck is done.
        '''
        all_done = True
        for t in self._threads:
            t.join( timeout = timeout )
            all_done = all_done & (not t.is_alive())

        return all_done

    def _performSpotChecks( self ):
        while not self._stopEvent.wait( timeout = 0 ):
            try:
                sensor = self._sensorsLeftToCheck.get_nowait()
            except:
                # Check to see if some sensors are pending a re-check
                # after being offline.
                with self._lock:
                    # If there are no more sensors to check, we can exit.
                    if 0 == self._pendingReCheck and 0 == self._sensorsLeftToCheck.qsize():
                        return
                time.sleep( 2 )
                continue

            # Check to see if the platform matches
            if self._isWindows is False or self._isLinux is False or self._isMacos is False or self._isChrome is False:
                platform = sensor.getInfo()[ 'plat' ]
                arch = sensor.getInfo()[ 'arch' ]
                if platform == 'windows' and not self._isWindows:
                    continue
                if platform == 'linux' and not self._isLinux:
                    continue
                if platform == 'macos' and not self._isMacos:
                    continue
                if arch == 'chrome' and not self._isChrome:
                    continue

            # If tags were set, check the sensor have them.
            if len( self._tags ) != 0 or len( self._positiveTags ) != 0 or len( self._negativeTags ) != 0:
                sensorTags = sensor.getTags()
                isTagsMatch = False
                for tag in self._positiveTags:
                    if tag in sensorTags:
                        isTagsMatch = True
                        break
                isNegativeMatch = False
                for tag in self._negativeTags:
                    if tag in sensorTags:
                        isNegativeMatch = True
                        break
                if isNegativeMatch:
                    continue
                # If no + tags are specified, we match
                # if all normal tags are there OR if no
                # normal tags are specified.
                if ( not isTagsMatch ) and ( len( self._positiveTags ) == 0 or len( self._tags ) != 0 ):
                    if all( [ ( x in sensorTags ) for x in self._tags ] ):
                        isTagsMatch = True
                if not isTagsMatch:
                    continue

            # Check to see if the sensor is online.
            if not sensor.isOnline():
                if self._cbOnOffline is not None:
                    self._cbOnOffline( sensor )

                # Re-add it to sensors to check, after the timeout.
                def _doReCheck( s ):
                    if self._stopEvent.wait( timeout = self._nSecBetweenOnlineChecks ):
                        return
                    with self._lock:
                        self._sensorsLeftToCheck.put( s )
                        self._pendingReCheck -= 1
                with self._lock:
                    self._pendingReCheck += 1
                t = threading.Thread( target = _doReCheck, args = ( sensor, ) )
                self._threads.append( t )
                t.start()
                continue

            if self._cbOnStartCheck is not None:
                self._cbOnStartCheck( sensor )

            # By this point we have a sensor and it's likely online.
            try:
                result = self._cbCheck( sensor )
            except:
                # On errors, we notify the callback but assume any retry
                # is likely to also fail so we won't retry.
                if self._cbOnError is not None:
                    self._cbOnError( sensor, traceback.format_exc() )
                result = True
            if not result:
                # We assume the sensor was somehow offline.
                if self._cbOnOffline is not None:
                    self._cbOnOffline( sensor )
                # Re-add it to sensors to check, after the timeout.
                time.sleep( self._nSecBetweenOnlineChecks )
                self._sensorsLeftToCheck.put( sensor )
                continue

            # This means the check was done successfully.
            if self._cbOnCheckDone is not None:
                self._cbOnCheckDone( sensor )

def main( sourceArgs = None ):
    import argparse
    import getpass

    parser = argparse.ArgumentParser( prog = 'limacharlie spotcheck' )
    parser.add_argument( '-o', '--oid',
                         type = lambda x: str( uuid.UUID( x ) ),
                         required = False,
                         dest = 'oid',
                         help = 'the OID to authenticate as, if not specified global creds are used.' )
    parser.add_argument( '-t', '--tag',
                         type = str,
                         required = False,
                         dest = 'tag',
                         default = None,
                         help = 'tag sensors where a match is found with this tag.' )
    parser.add_argument( '-tt', '--tag-ttl',
                         type = int,
                         required = False,
                         dest = 'tag_ttl',
                         default = 60 * 60 * 24 * 7,
                         help = 'ttl of the tag to set.' )
    parser.add_argument( '-n', '--n-concurrent',
                         type = int,
                         required = False,
                         default = 1,
                         dest = 'nConcurrent',
                         help = 'number of agents to spot-check concurrently.' )
    parser.add_argument( '--no-windows',
                         action = 'store_false',
                         default = True,
                         required = False,
                         dest = 'is_windows',
                         help = 'do NOT apply to Windows agents.' )
    parser.add_argument( '--no-linux',
                         action = 'store_false',
                         default = True,
                         required = False,
                         dest = 'is_linux',
                         help = 'do NOT apply to Linux agents.' )
    parser.add_argument( '--no-macos',
                         action = 'store_false',
                         default = True,
                         required = False,
                         dest = 'is_macos',
                         help = 'do NOT apply to MacOS agents.' )
    parser.add_argument( '--no-chrome',
                         action = 'store_false',
                         default = True,
                         required = False,
                         dest = 'is_chrome',
                         help = 'do NOT apply to Chrome agents.' )
    parser.add_argument( '--tags',
                         type = lambda x: [ _.strip().lower() for _ in x.split( ',' ) if _.strip() != '' ],
                         required = False,
                         default = None,
                         dest = 'tags',
                         help = 'comma-seperated list of tags, sensors must have: either one tag with the "+" prefix, not include all tags with "-" prefix, or the sensor has all tags specified without prefix.' )
    parser.add_argument( '--extra-params',
                         type = lambda x: json.loads( x ),
                         required = False,
                         default = {},
                         dest = 'extra_params',
                         help = 'extra parameters to pass to the manager.' )
    parser.add_argument( '-f', '--file',
                         action = 'append',
                         required = False,
                         default = [],
                         dest = 'files',
                         help = 'file to look for.' )
    parser.add_argument( '-fp', '--file-pattern',
                         action = 'append',
                         nargs = 3,
                         required = False,
                         default = [],
                         dest = 'filepatterns',
                         help = 'takes 3 arguments, first is a directory, second is a file pattern like "*.exe", third is the depth of recursion in the directory.' )
    parser.add_argument( '-fh', '--file-hash',
                         action = 'append',
                         nargs = 4,
                         required = False,
                         default = [],
                         dest = 'filehashes',
                         help = 'takes 3 arguments, first is a directory, second is a file pattern like "*.exe", third is the depth of recursion in the directory and the fourth is the sha256 hash to look for.' )
    parser.add_argument( '-rk', '--registry-key',
                         action = 'append',
                         required = False,
                         default = [],
                         dest = 'registrykeys',
                         help = 'registry key to look for.' )
    parser.add_argument( '-rv', '--registry-value',
                         action = 'append',
                         nargs = 2,
                         required = False,
                         default = [],
                         dest = 'registryvalues',
                         help = 'takes 2 arguments, first is a registry key, second is the value to look for in the key.' )
    parser.add_argument( '-y', '--yara',
                         action = 'append',
                         required = False,
                         default = [],
                         dest = 'yarasystem',
                         help = 'yara signature file path to scan system-wide with (expensive).' )
    parser.add_argument( '-yf', '--yara-file',
                         action = 'append',
                         nargs = 4,
                         required = False,
                         default = [],
                         dest = 'yarafiles',
                         help = 'takes 4 arguments, first is a file path to yara signature, second is a directory, third is a file pattern (like "*.exe"), fourth is directory recursion depth.' )
    parser.add_argument( '-yp', '--yara-process',
                         action = 'append',
                         nargs = 2,
                         required = False,
                         default = [],
                         dest = 'yaraprocesses',
                         help = 'takes 2 arguments, first is a file path to yara signature, second is a process executable path pattern to scan memory and files.' )
    parser.add_argument( '-r', '--run',
                         action = 'append',
                         required = False,
                         default = [],
                         dest = 'runs',
                         help = 'a command to run against each sensor.' )
    parser.add_argument( '-l', '--log-get',
                         action = 'append',
                         required = False,
                         default = [],
                         dest = 'logs',
                         help = 'logs to look for.' )
    parser.add_argument( '--is-ignore-certs',
                         action = 'store_true',
                         default = False,
                         required = False,
                         dest = 'is_ignore_certs',
                         help = 'ignore SSL cert errors for logs and payloads.' )

    args = parser.parse_args( sourceArgs )

    # Get creds if we need them.
    if args.oid is not None:
        secretApiKey = getpass.getpass( prompt = 'Enter secret API key: ' )
    else:
        secretApiKey = None

    def _genericSpotCheck( sensor ):
        for file in args.files:
            response = sensor.simpleRequest( 'file_info "%s"' % file.replace( '\\', '\\\\' ), timeout = 30 )
            if not response:
                raise Exception( 'timeout' )

            if 0 != response[ 'event' ].get( 'ERROR', 0 ):
                # File probably not found.
                continue

            # File was found.
            fileInfo = response[ 'event' ]

            # Try to ge the hash.
            response = sensor.simpleRequest( 'file_hash "%s"' % file.replace( '\\', '\\\\' ), timeout = 30 )
            if not response:
                raise Exception( 'timeout' )

            fileHash = None
            if 0 == response[ 'event' ].get( 'ERROR', 0 ):
                # We got a hash.
                fileHash = response[ 'event' ]

            _reportHit( sensor, { 'file_info' : fileInfo, 'file_hash' : fileHash } )

        for directory, filePattern, depth in args.filepatterns:
            response = sensor.simpleRequest( 'dir_list "%s" "%s" -d %s' % ( directory.replace( "\\", "\\\\" ), filePattern, depth ), timeout = 30 )
            if not response:
                raise Exception( 'timeout' )

            for entry in response[ 'event' ][ 'DIRECTORY_LIST' ]:
                _reportHit( sensor, { 'file_info' : entry } )

        for directory, filePattern, depth, hash in args.filehashes:
            if 64 != len( hash ):
                raise Exception( 'hash not valid sha256' )
            try:
                hash.decode( 'hex' )
            except:
                try:
                    bytes.fromhex( hash )
                except:
                    raise Exception( 'hash contains invalid characters' )
            response = sensor.simpleRequest( 'dir_find_hash "%s" "%s" %s --depth %s' % ( directory.replace( "\\", "\\\\" ), filePattern, hash, depth ), timeout = 3600 )
            if not response:
                raise Exception( 'timeout' )

            for entry in response[ 'event' ][ 'DIRECTORY_LIST' ]:
                _reportHit( sensor, { 'file_hash' : entry } )

        for regKey in args.registrykeys:
            response = sensor.simpleRequest( 'reg_list "%s"' % ( regKey.replace( '\\', '\\\\' ), ), timeout = 30 )
            if not response:
                raise Exception( 'timeout' )

            if 0 != response[ 'event' ][ 'ERROR' ]:
                # Registry probably not found.
                continue

            _reportHit( sensor, { 'reg_key' : response[ 'event' ] } )

        for regKey, regVal in args.registryvalues:
            response = sensor.simpleRequest( 'reg_list "%s"' % ( regKey.replace( '\\', '\\\\' ), ), timeout = 30 )
            if not response:
                raise Exception( 'timeout' )

            if 0 != response[ 'event' ][ 'ERROR' ]:
                # Registry probably not found.
                continue

            for valEntry in response[ 'event' ][ 'REGISTRY_VALUE' ]:
                if valEntry.get( 'NAME', '' ).lower() == regVal.lower():
                    _reportHit( sensor, { 'reg_key' : response[ 'event' ][ 'ROOT' ], 'reg_value' : valEntry } )

        for yaraSigFile in args.yarasystem:
            with open( yaraSigFile, 'rb' ) as f:
                yaraSig = base64.b64encode( f.read() ).decode()
            future = sensor.request( 'yara_scan %s --is-no-validation' % ( yaraSig, ) )
            _handleYaraTasking( sensor, future )

        for yaraSigFile, directory, filePattern, depth in args.yarafiles:
            with open( yaraSigFile, 'rb' ) as f:
                yaraSig = base64.b64encode( f.read() ).decode()
            response = sensor.simpleRequest( 'dir_list "%s" "%s" -d %s' % ( directory.replace( "\\", "\\\\" ), filePattern, depth ), timeout = 30 )
            if not response:
                raise Exception( 'timeout' )
            for fileEntry in response[ 'event' ][ 'DIRECTORY_LIST' ]:
                filePath = fileEntry.get( 'FILE_PATH', None )
                if filePath is None:
                    continue
                future = sensor.request( 'yara_scan %s --is-no-validation -f "%s"' % ( yaraSig, filePath.replace( "\\", "\\\\" ) ) )
                _handleYaraTasking( sensor, future )

        for yaraSigFile, procPattern in args.yaraprocesses:
            with open( yaraSigFile, 'rb' ) as f:
                yaraSig = base64.b64encode( f.read() ).decode()
            future = sensor.request( 'yara_scan %s --is-no-validation -e %s' % ( yaraSig, procPattern.replace( '\\', '\\\\' ) ) )
            _handleYaraTasking( sensor, future )

        for run in args.runs:
            response = sensor.simpleRequest( run )
            if not response:
                raise Exception( 'timeout' )

            _reportHit( sensor, response[ 'event' ] )

        for log in args.logs:
            cert = ''
            if args.is_ignore_certs:
                cert = '--is-ignore-cert'
            response = sensor.simpleRequest( 'log_get --file "%s" %s' % ( log.replace( '\\', '\\\\' ), cert ), timeout = 30 )
            if not response:
                raise Exception( 'timeout' )

            retCode = response[ 'event' ].get( 'ERROR', None )
            if 200 != retCode:
                raise Exception( 'failed: %s' % ( retCode, ) )

            _reportHit( sensor, response[ 'event' ] )

        return True

    def _handleYaraTasking( sensor, future ):
        isDone = False
        while True:
            responses = future.getNewResponses( timeout = 3600 )
            if not responses:
                raise Exception( 'timeout' )
            for response in responses:
                if 'done' == response[ 'event' ].get( 'ERROR_MESSAGE', None ):
                    isDone = True
                    continue
                if 0 == response[ 'event' ].get( 'ERROR', 0 ):
                    # We got a hit, we don't care about individual hits right now.
                    _reportHit( sensor, { 'yara' : response[ 'event' ] } )
                else:
                    # Ignore if we failed to scan file.
                    pass

            if isDone:
                break

    def _reportHit( sensor, mtd ):
        print( "! (%s / %s): %s" % ( sensor, sensor.hostname(), json.dumps( mtd  ) ) )
        sys.stdout.flush()
        if args.tag is not None:
            sensor.tag( args.tag, args.tag_ttl )

    def _onError( sensor, error ):
        print( "X (%s / %s): %s" % ( sensor, sensor.hostname(), error ) )
        sys.stdout.flush()

    def _onOffline( sensor ):
        print( "? (%s / %s)" % ( sensor, sensor.hostname() ) )
        sys.stdout.flush()

    def _onDone( sensor ):
        print( ". (%s / %s)" % ( sensor, sensor.hostname() ) )
        sys.stdout.flush()

    def _onStartCheck( sensor ):
        print( "> (%s / %s)" % ( sensor, sensor.hostname() ) )
        sys.stdout.flush()

    checker = SpotCheck( args.oid,
                         secretApiKey,
                         _genericSpotCheck,
                         n_concurrent = args.nConcurrent,
                         cb_on_start_check = _onStartCheck,
                         cb_on_check_done = _onDone,
                         cb_on_offline = _onOffline,
                         cb_on_error = _onError,
                         is_windows = args.is_windows,
                         is_linux = args.is_linux,
                         is_macos = args.is_macos,
                         is_chrome = args.is_chrome,
                         tags = args.tags,
                         extra_params = args.extra_params )
    checker.start()
    checker.wait( 60 * 60 * 24 * 30 * 365 )

if __name__ == "__main__":
    main()
