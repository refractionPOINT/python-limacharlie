import json
import cmd
from . import Manager
import uuid
from functools import wraps
import sys
from . import GLOBAL_OID
import traceback
import yaml
from gevent.lock import BoundedSemaphore
import gevent
from .utils import parallelExec

def _eprint( msg ):
    sys.stderr.write( msg )
    sys.stderr.write( "\n" )

def _report_errors( func ):
    @wraps( func )
    def silenceit( *args, **kwargs ):
        try:
            return func( *args, **kwargs )
        except:
            _eprint( traceback.format_exc() )
            return None
    return( silenceit )

class Shell ( cmd.Cmd ):
    intro = 'Welcome to LimaCharlie shell.\nOID: %s\nType help or ? to list commands.\n' % ( GLOBAL_OID, )
    prompt = '() '

    def __init__( self ):
        cmd.Cmd.__init__( self )
        self.sensors = {}
        self.inv_id = 'shell-%s' % ( str( uuid.uuid4() )[ -12: ] )
        self.updatePrompt()
        self.man = Manager( inv_id = self.inv_id, is_interactive = True )
        self.outputMutex = BoundedSemaphore()
        gevent.spawn_later( 0, self.outputFromSpout )

    def outputFromSpout( self ):
        while True:
            d = self.man._spout.queue.get()
            routing = d.get( 'routing', {} )
            event = d.get( 'event', {} )
            if routing.get( 'event_type', None ) == 'CLOUD_NOTIFICATION':
                d = {
                    'sid' : routing.get( 'sid', None ),
                    'task' : event.get( 'NOTIFICATION_ID', None ),
                    'received' : True,
                }
            else:
                d = {
                    'event' : event,
                    'sid' : routing.get( 'sid', None )
                }
            self.printOut( d )

    def updatePrompt( self ):
        if len(self.sensors) == 0:
            self.prompt = '() '
            return
        if len(self.sensors) == 1:
            self.prompt = '(%s) ' % ( self.sensors.values()[ 0 ].hostname() )
            return
        self.prompt = '(%s sensors) ' % ( len( self.sensors ), )

    def printOut( self, data, isBackground = False ):
        with self.outputMutex:
            print( yaml.safe_dump( data, default_flow_style = False ) )

    def emptyline( self ):
        pass

    def do_quit( self, s ):
        '''Exit the shell.'''
        return True

    def do_exit( self, s ):
        '''Exit the shell.'''
        return True

    @_report_errors
    def do_ctx( self, s ):
        '''Get the current context.'''
        sensors = [ { 'sid' : sensor.sid, 'hostname' : sensor.hostname() } for sensor in self.sensors.values() ]
        data = { 'sensors' : sensors, 'investigation_id' : self.inv_id }
        self.printOut( data )

    @_report_errors
    def do_add_sid( self, s ):
        '''Add this sensor by SID to the context.'''
        try:
            s = str( uuid.UUID( s ) )
        except:
            _eprint( 'Invalid SID format, should be a UUID.' )
            return
        if s in self.sensors:
            self.printOut( 'already set' )
            return
        self.sensors[ s ] = self.man.sensor( s )
        self.updatePrompt()

    @_report_errors
    def do_add_host( self, s ):
        '''Add this sensor by hostname to the context.'''
        sensors = [ { 'sid' : d[ 0 ], 'hostname' : d[ 1 ] } for d in self.man.getSensorsWithHostname( s ) ]
        self.printOut( { 'matching' : sensors } )
        sensors = [ self.man.sensor( sensor[ 'sid' ] ) for sensor in sensors ]
        for sensor in sensors:
            if sensor.sid in self.sensors:
                continue
            self.sensors[ sensor.sid ] = sensor
        self.updatePrompt()

    @_report_errors
    def do_task( self, s ):
        '''Send a task to the sensors set in current context.'''
        def _task( d ):
            sensor, task = d
            try:
                return ( sensor, sensor.task( task ) )
            except Exception as e:
                return ( sensor, e )
        resps = parallelExec( _task, ( ( sensor, s ) for sensor in self.sensors.values() ) )
        for resp in resps:
            sensor, resp = resp
            if isinstance( resp, dict ) and len( resp ) == 0:
                continue
            if isinstance( resp, Exception ):
                resp = str( resp )
            self.printOut( { 
                'error' : resp,
                'sid' : sensor.sid,
            } )

def main( sourceArgs = None ):
    app = Shell()
    app.cmdloop()


if __name__ == '__main__':
    main()