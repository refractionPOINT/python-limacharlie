from limacharlie import Manager
import json

from .utils import POST
from .utils import DELETE
from .utils import GET
from .utils import PUT
from .utils import PATCH

class Billing( object ):
    def __init__( self, manager ):
        self._manager = manager

    def getOrgStatus( self ):
        return self._manager._apiCall( 'orgs/%s/status' % ( self._manager._oid, ), GET, altRoot = 'https://billing.limacharlie.io/' )

    def getOrgDetails( self ):
        return self._manager._apiCall( 'orgs/%s/details' % ( self._manager._oid, ), GET, altRoot = 'https://billing.limacharlie.io/' )
