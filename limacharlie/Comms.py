from .utils import LcApiException
from .utils import GET
from .utils import DELETE
from .utils import POST
from .utils import HEAD
from .utils import PATCH

from .Manager import Manager

import uuid
import sys

class Comms( object ):
    '''Representation of a limacharlie.io Comms.'''

    def __init__( self, manager ):
        self._manager = manager

    def createRoom( self, nickname = None ):
        '''Create a new Room.

        Args:
            nickname (str): optional nickname to give the new room.
        Returns:
            a Room object.
        '''
        req = {
            'oid': self._manager._oid,
        }
        if nickname is not None:
            req[ 'nickname' ] = str( nickname )
        data = self._manager._apiCall( 'comms/room', POST, req )
        return Room( self._manager, data[ 'rid' ] )

    def getRoom( self, rid ):
        '''Initialize an existing Room object.

        Args:
            rid (str): room id of the Room to initialize.
        Returns:
            a Room object.
        '''
        return Room( rid )

class Room( object ):
    '''Representation of a limacharlie.io Comms Room.'''

    def __init__( self, manager, rid ):
        self._manager = manager
        try:
            uuid.UUID( rid )
        except:
            raise LcApiException( 'Invalid sid, should be in UUID format.' )
        self.rid = str( rid )

    def getOverview( self ):
        '''Get overview information about the Room.

        Returns:
            room overview dict.
        '''
        return self._manager._apiCall( 'comms/room/%s' % self.rid, HEAD )

    def delete( self ):
        '''Delete a Room.'''
        return self._manager._apiCall( 'comms/room/%s' % self.rid, DELETE )

    def getDetails( self ):
        '''Get detailed information about the Room.

        Returns:
            room details dict.
        '''
        return self._manager._apiCall( 'comms/room/%s' % self.rid, GET )

    def merge( self, toMerge = [] ):
        '''Merge a set of Rooms into this Room.

        Args:
            toMerge (str list): list of room id to merge into this Room.
        '''
        req = {
            'rid': toMerge,
        }
        return self._manager._apiCall( 'comms/room/%s' % self.rid, PATCH, req )

    def update( self, nickname = None, priority = None, status = None ):
        '''Update room information.

        Args:
            nickname (str): optional nickname to set.
            priority (int): optional priority to set.
            status (str): optional status to set.
        '''
        req = {}
        if nickname is not None:
            req[ 'nickname' ] = nickname
        if priority is not None:
            req[ 'priority' ] = int( priority )
        if status is not None:
            req[ 'status' ] = str( status )
        return self._manager._apiCall( 'comms/room/%s' % self.rid, POST )

def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie comms' )
    subparsers = parser.add_subparsers( dest = 'object', help = 'object to work with' )

    objects = {
        'room' : subparsers.add_parser( 'room', help = 'working with rooms' ),
    }

    # room
    subparsers_room = objects[ 'room' ].add_subparsers( dest = 'action', help = 'action to take' )

    # room:create
    parser_room_create = subparsers_room.add_parser( 'create', help = 'create a room' )
    parser_room_create.add_argument( '--nickname', type = str, help = 'nickname of the room' )

    # room:get
    parser_room_get = subparsers_room.add_parser( 'get', help = 'get a room' )
    parser_room_get.add_argument( 'rid', type = str, help = 'room id' )

    args = parser.parse_args( sourceArgs )

    if args.object is None:
        parser.print_help()
        sys.exit( 1 )
    if args.action is None:
        objects[ args.object ].print_help()
        sys.exit( 1 )

    def createRoom():
        return Comms( Manager() ).createRoom( args.nickname )

    def getRoom():
        return Comms( Manager() ).getDetails( args.rid )

    result = {
        'room:create' : createRoom,
        'room:get' : getRoom,
    }[ '%s:%s' % ( args.object, args.action ) ]()

    print( result, indent = 2 )

if __name__ == '__main__':
    main()