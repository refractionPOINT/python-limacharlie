import limacharlie
import json
import gevent
import signal
import sys
import getpass

if __name__ == "__main__":
  def signal_handler():
      global sp
      print( 'You pressed Ctrl+C!' )
      sp.shutdown()
      sys.exit( 0 )

  gevent.signal( signal.SIGINT, signal_handler )

  def debugPrint( msg ):
      print msg

  sp = limacharlie.Spout( raw_input( 'Enter OID: ' ),
                          getpass.getpass( prompt = 'Enter secret API key: ' ),
                          'event' )

  while True:
      data = sp.queue.get()
      print( json.dumps( data, indent = 2 ) + "\n\n" )
