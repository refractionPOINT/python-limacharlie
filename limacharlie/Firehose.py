from gevent.server import StreamServer
from gevent.queue import Queue

# Detect if this is Python 2 or 3
import sys
_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True

if _IS_PYTHON_2:
    from urllib2 import urlopen
else:
    from urllib.request import urlopen

import sys
import ssl
import json
import os
import tempfile
import socket
import traceback

from .utils import LcApiException

class Firehose( object ):
    '''Listener object to receive data (Events, Detects or Audit) from a limacharlie.io Organization in push mode.'''

    def __init__( self, manager, listen_on, data_type, public_dest = None, name = None, ssl_cert = None, ssl_key = None, is_parse = True, max_buffer = 1024, inv_id = None, tag = None, cat = None, sid = None, is_delete_on_failure = False, on_dropped = None ):
        '''Create a listener and optionally register it with limacharlie.io automatically.

        If name is None, the Firehose will assume the Output is already created
        and will skip it's initialization and teardown.

        If public_dest is None and name is not None, initialization of the Output
        will use the dynamically detected public IP address of this host and port
        specified in listen_on.

        Args:
            manager (limacharlie.Manager obj): a Manager to use for interaction with limacharlie.io.
            listen_on (str): the interface and port to listen on for data from the cloud, ex: "1.2.3.4:443", "0.0.0.0:443", ":443".
            data_typer (str): the type of data received from the cloud as specified in Outputs (event, detect, audit).
            public_dest (str): the IP and port that limacharlie.io should use to connect to this object.
            name (str): name to use to register as an Output on limacharlie.io.
            ssl_cert (str): optional, path to file with (PEM) ssl cert to use to receive from the cloud, if not set generates self-signed certs.
            ssl_key (str): optional, path to the file with (PEM) ssl key to use to receive from the cloud, if not set generates self-signed certs.
            is_parse (bool): if set to True (default) the data will be parsed as JSON to native Python.
            max_buffer (int): the maximum number of messages to buffer in the queue.
            inv_id (str): only receive events marked with this investigation ID.
            tag (str): only receive Events from Sensors with this Tag.
            cat (str): only receive Detections of this Category.
            sid (str): only receive Detections and Events from this Sensor.
            is_delete_on_failure (bool): if set to True, delete the Firehose output on failure (in LC cloud).
            on_dropped (func): callback called with a data item when the item will otherwise be dropped.
        '''

        self._manager = manager
        self._keepRunning = True
        self._listen_on = listen_on.split( ':' )
        if 1 < len( self._listen_on ):
            self._listen_on_port = int( self._listen_on[ 1 ] )
            self._listen_on = self._listen_on[ 0 ]
        else:
            self._listen_on = self._listen_on[ 0 ]
            self._listen_on_port = 443
        if '' == self._listen_on:
            self._listen_on = '0.0.0.0'
        self._data_type = data_type
        self._public_dest = public_dest if public_dest != '' else None
        self._name = name
        self._output_name = None
        self._is_parse = is_parse
        self._max_buffer = max_buffer
        self._dropped = 0
        self._on_dropped = on_dropped
        self._is_delete_on_failure = is_delete_on_failure

        self._ssl_cert = ssl_cert
        self._ssl_key = ssl_key
        if self._ssl_cert is not None and not os.path.isfile( self._ssl_cert ):
            raise LcApiException( 'No cert file at path: %s' % self._ssl_cert )
        if self._ssl_key is not None and not os.path.isfile( self._ssl_key ):
            raise LcApiException( 'No key file at path: %s' % self._ssl_key )

        if self._data_type not in ( 'event', 'detect', 'audit' ):
            raise LcApiException( 'Invalid data type: %s' % self._data_type )

        # Setup internal structures.
        self.queue = Queue( maxsize = self._max_buffer )

        if self._ssl_cert is None or self._ssl_key is None:
            # Generate certs.
            _, tmpKey = tempfile.mkstemp()
            _, tmpCert = tempfile.mkstemp()
            if 0 != os.system( 'openssl req -x509 -days 36500 -newkey rsa:4096 -keyout %s -out %s -nodes -sha256 -subj "/C=US/ST=CA/L=Mountain View/O=refractionPOINT/CN=limacharlie_firehose" > /dev/null 2>&1' % ( tmpKey, tmpCert ) ):
                raise LcApiException( "Failed to generate self-signed certificate." )
        else:
            # Use the keys provided.
            tmpKey = self._ssl_key
            tmpCert = self._ssl_cert

        # Start the server.
        self._sslCtx = ssl.SSLContext( ssl.PROTOCOL_TLSv1_2 )
        self._sslCtx.load_cert_chain( certfile = tmpCert, keyfile = tmpKey )
        self._sslCtx.set_ciphers( 'ECDHE-RSA-AES128-GCM-SHA256' )
        self._server = StreamServer( ( self._listen_on, self._listen_on_port ), self._handleNewClient )
        self._server.start()
        self._manager._printDebug( 'Listening for connections.' )

        # If the name is specified we assume the user wants us to register
        # the firehose directly using the API.
        # If the name is not present, we assume the user has registered it
        # manually somehow.
        if self._name is not None:
            self._manager._printDebug( 'Registration required.' )
            self._output_name = 'tmp_live_%s' % self._name

            # Check if the output already exists.
            outputs = self._manager.outputs()
            if self._output_name not in outputs:
                # It's not there, register it.
                effectiveDest = self._public_dest
                if effectiveDest is None:
                    effectiveDest = '%s:%s' % ( self._getPublicIp(), self._listen_on_port )
                if ( self._ssl_cert is not None ) and ( self._ssl_key is not None ):
                    isStrict = 'true'
                else:
                    isStrict = 'false'
                kwOutputArgs = {
                    'dest_host': effectiveDest,
                    'is_tls': 'true',
                    'is_strict_tls': isStrict,
                    'is_no_header': 'true',
                }
                if inv_id is not None:
                    kwOutputArgs[ 'inv_id' ] = inv_id
                if tag is not None:
                    kwOutputArgs[ 'tag' ] = tag
                if cat is not None:
                    kwOutputArgs[ 'cat' ] = cat
                if sid is not None:
                    kwOutputArgs[ 'sid' ] = sid
                if self._is_delete_on_failure:
                    kwOutputArgs[ 'is_delete_on_failure' ] = 'true'
                self._manager.add_output( self._output_name,
                                          'syslog',
                                          self._data_type,
                                          **kwOutputArgs )
                self._manager._printDebug( 'Registration done.' )
            else:
                self._manager._printDebug( 'Registration already done.' )
        else:
            self._manager._printDebug( 'Registration not required.' )

    def shutdown( self ):
        '''Stop receiving data and potentially unregister the Output (if created here).'''

        if not self._keepRunning:
            return

        self._keepRunning = False
        try:
            if self._name is not None:
                self._manager._printDebug( 'Unregistering.' )
                self._manager.del_output( self._output_name )
        finally:
            self._server.close()
            self._manager._printDebug( 'Closed.' )

    def getDropped( self ):
        '''Get the number of messages dropped because queue was full.'''
        return self._dropped

    def resetDroppedCounter( self ):
        '''Reset the counter of dropped messages.'''
        self._dropped = 0

    def _getPublicIp( self ):
        return json.load( urlopen( 'http://jsonip.com' ) )[ 'ip' ]

    def _handleNewClient( self, sock, address ):
        self._manager._printDebug( 'new firehose connection: %s' % ( address, ) )

        sock.setsockopt( socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1 )
        sock.setsockopt( socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5 )
        sock.setsockopt( socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10 )
        sock.setsockopt( socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 2 )

        try:
            sock = self._sslCtx.wrap_socket( sock,
                                             server_side = True,
                                             do_handshake_on_connect = True,
                                             suppress_ragged_eofs = True )
        except:
            print( traceback.format_exc() )
            self._manager._printDebug( 'firehose connection closed: %s' % ( address, ) )
            return

        curData = []
        while self._keepRunning:
            try:
                data = sock.recv( 1024 * 512 )
                if not data: break

                chunks = [ c for c in data.split( b'\n' ) ]

                # This is a pure continuation.
                if 1 == len( chunks ):
                    curData.append( chunks[ 0 ] )
                    continue

                # Every chunk is an event boundary.
                for c in chunks:
                    curData.append( c )
                    buff = b''.join( curData )
                    curData = []
                    if 0 == len( buff ):
                        continue
                    try:
                        if self._is_parse:
                            self.queue.put_nowait( json.loads( buff ) )
                        else:
                            self.queue.put_nowait( buff )
                    except:
                        self._dropped += 1
                        if self._on_dropped is not None:
                            if self._is_parse:
                                self._on_dropped( json.loads( buff ) )
                            else:
                                self._on_dropped( buff )
                    buff = None
            except:
                self._manager._printDebug( 'error decoding data: %s' % ( traceback.format_exc(), ) )
                break

        self._manager._printDebug( 'firehose connection closed: %s' % ( address, ) )
        sock.close()

def _signal_handler():
    global fh
    _printToStderr( 'You pressed Ctrl+C!' )
    if fh is not None:
        fh.shutdown()
    sys.exit( 0 )

def _printToStderr( msg ):
    sys.stderr.write( msg + '\n' )

if __name__ == "__main__":
    import argparse
    import getpass
    import uuid
    import gevent
    import signal
    import limacharlie

    fh = None
    gevent.signal( signal.SIGINT, _signal_handler )

    parser = argparse.ArgumentParser( prog = 'limacharlie.io firehose' )
    parser.add_argument( 'listen_interface',
                         type = str,
                         help = 'the local interface to listen on for firehose connections, like "0.0.0.0:4444".' )
    parser.add_argument( 'data_type',
                         type = str,
                         help = 'the type of data to receive in firehose, one of "event", "detect" or "audit".' )
    parser.add_argument( '-o', '--oid',
                         type = lambda x: str( uuid.UUID( x ) ),
                         required = False,
                         dest = 'oid',
                         help = 'the OID to authenticate as, if not specified global creds are used.' )
    parser.add_argument( '-p', '--public-destination',
                         type = str,
                         dest = 'public_dest',
                         default = None,
                         help = 'where to tell limacharlie.io to connect to for firehose output, default is public ip and same port as listen_interface.' )
    parser.add_argument( '-n', '--name',
                         type = str,
                         dest = 'name',
                         default = None,
                         help = 'unique name to use for this firehose, will be used to register a limacharlie.io Output if specified, otherwise assumes Output is already taken care of.' )
    parser.add_argument( '-i', '--investigation-id',
                         type = str,
                         dest = 'inv_id',
                         default = None,
                         help = 'firehose should only receive events marked with this investigation id.' )
    parser.add_argument( '-t', '--tag',
                         type = str,
                         dest = 'tag',
                         default = None,
                         help = 'firehose should only receive events from sensors tagged with this tag.' )
    parser.add_argument( '-c', '--category',
                         type = str,
                         dest = 'cat',
                         default = None,
                         help = 'firehose should only receive detections from this category.' )
    parser.add_argument( '-s', '--sid',
                         type = lambda x: str( uuid.UUID( x ) ),
                         dest = 'sid',
                         default = None,
                         help = 'firehose should only receive detections and events from this sensor.' )
    args = parser.parse_args()
    if args.oid is not None:
        secretApiKey = getpass.getpass( prompt = 'Enter secret API key: ' )
    else:
        secretApiKey = None

    _printToStderr( "Registering..." )
    man = limacharlie.Manager( oid = args.oid, secret_api_key = secretApiKey )
    fh = limacharlie.Firehose( man, args.listen_interface, args.data_type,
                               public_dest = args.public_dest,
                               name = args.name,
                               inv_id = args.inv_id,
                               tag = args.tag,
                               cat = args.cat,
                               sid = args.sid )

    _printToStderr( "Starting to listen..." )
    while True:
        data = fh.queue.get()
        print( json.dumps( data, indent = 2 ) )

    _printToStderr( "Exiting." )