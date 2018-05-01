from gevent import monkey; monkey.patch_all()
from gevent.server import StreamServer
from gevent.queue import Queue
import ssl
import json
import os
import tempfile
import socket
import traceback

from .utils import *

class Firehose( object ):
    def __init__( self, manager, listen_on, data_type, public_dest = None, name = None, inv_id = None, tag = None, cat = None ):
        self._manager = manager
        self._listen_on = listen_on.split( ':' )
        if 1 < len( self._listen_on ):
            self._listen_on_port = int( self._listen_on[ 1 ] )
            self._listen_on = self._listen_on[ 0 ]
        else:
            self._listen_on_port = 443
        self._data_type = data_type
        self._public_dest = public_dest
        self._name = name
        self._output_name = None

        if self._data_type not in ( 'event', 'detect', 'audit' ):
            raise LcApiException( 'Invalid data type: %s' % self._data_type )

        if 'event' == self._data_type and inv_id is None and tag is None:
            raise LcApiException( 'Firehose for events must specify a tag or inv_id filter.' ) 

        # If the name is specified we assume the user wants us to register
        # the firehose directly using the API.
        # If the name is not present, we assume the user has registered it
        # manually somehow.
        if self._name is not None:
            self._manager._printDebug( 'Registration required.' )
            self._output_name = 'py_lc_fh_%s' % self._name

            # Check if the output already exists.
            outputs = self._manager.outputs()
            if self._output_name not in outputs:
                # It's not there, register it.
                effectiveDest = self._public_dest
                if effectiveDest is None:
                    effectiveDest = '%s:%s' % ( self._listen_on, self._listen_on_port )
                kwOutputArgs = {
                    'dest_host': effectiveDest,
                    'is_tls': 'true', 
                    'is_no_header': 'true',
                }
                if inv_id is not None:
                    kwOutputArgs[ 'inv_id' ] = inv_id
                if tag is not None:
                    kwOutputArgs[ 'tag' ] = tag
                if cat is not None:
                    kwOutputArgs[ 'cat' ] = cat
                self._manager.add_output( self._output_name, 
                                          'syslog', 
                                          self._data_type, 
                                          **kwOutputArgs )
                self._manager._printDebug( 'Registration done.' )
            else:
                self._manager._printDebug( 'Registration already done.' )
        else:
            self._manager._printDebug( 'Registration not required.' )

        # Setup internal structures.
        self.queue = Queue( maxsize = 1024 )

        # Generate certs.
        _, tmpKey = tempfile.mkstemp()
        _, tmpCert = tempfile.mkstemp()
        if 0 != os.system( 'openssl req -x509 -days 36500 -newkey rsa:4096 -keyout %s -out %s -nodes -sha256 -subj "/C=US/ST=CA/L=Mountain View/O=refractionPOINT/CN=limacharlie_firehose" > /dev/null 2>&1' % ( tmpKey, tmpCert ) ):
            raise LcApiException( "Failed to generate self-signed certificate." )

        # Start the server.
        self._sslCtx = ssl.SSLContext( ssl.PROTOCOL_TLSv1_2 )
        self._sslCtx.load_cert_chain( certfile = tmpCert, keyfile = tmpKey )
        self._sslCtx.set_ciphers( 'ECDHE-RSA-AES128-GCM-SHA256' )
        self._server = StreamServer( ( self._listen_on, self._listen_on_port ), self._handleNewClient )
        self._server.start()
        self._manager._printDebug( 'Listening for connections.' )

    def shutdown( self ):
        if self._name is not None:
            self._manager._printDebug( 'Unregistering.' )
            self._manager.del_output( self._output_name )
        self._server.close()
        self._manager._printDebug( 'Closed.' )

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
        while True:
            data = sock.recv( 8192 )
            if not data: break
            if '\n' in data:
                chunks = data.split( '\n' )
                curData.append( chunks[ 0 ] )
                self.queue.put_nowait( json.loads( ''.join( curData ) ) )
                for c in chunks[ 1 : -1 ]:
                    self.queue.put_nowait( json.loads( c ) )
                curData = [ chunks[ -1 ] ]
            else:
                curData.append( data )

        self._manager._printDebug( 'firehose connection closed: %s' % ( address, ) )