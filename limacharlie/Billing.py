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

    def getOrgInvoiceURL( self, year, month, format = None ):
        year = str( int( year ) )
        month = str( int( month ) ).zfill( 2 )
        params = {}
        if format:
            params[ 'format' ] = format
        return self._manager._apiCall( 'orgs/%s/invoice_url/%s/%s' % ( self._manager._oid, year, month ), GET, altRoot = 'https://billing.limacharlie.io/', queryParams = params )

    def getAvailablePlans( self ):
        return self._manager._apiCall( 'user/self/plans', GET, altRoot = 'https://billing.limacharlie.io/' )

    def getUserAuthRequirements( self ):
        return self._manager._apiCall( 'user/self/auth', GET, altRoot = 'https://billing.limacharlie.io/' )

    def getSkuDefinitions( self ):
        return self._manager._apiCall( 'orgs/%s/sku-definitions' % ( self._manager._oid, ), GET, altRoot = 'https://billing.limacharlie.io/' )
