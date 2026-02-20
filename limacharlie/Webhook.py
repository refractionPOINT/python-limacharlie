import hmac
import hashlib

class Webhook( object ):
    '''Helper class for various activities related to webhooks from limacharlie.io.'''

    def __init__( self, secret_key ):
        '''Create a Webhook object.

        Args:
            secret_key (str): shared secret used in the webhook Output configuration in limacharlie.io.
        '''

        self._secretKey = secret_key

    def isSignatureValid( self, dataFromHook, signature ):
        '''Validate the signature from a webhook.

        Args:
            dataFromHook (str): string found in the "data" element from the webhook.
            signature (str): signature from the "Lc-Signature" header of the webhook.

        Returns:
            a boolean where True means the webhook data and signature are valid.
        '''
        expected = hmac.new( self._secretKey, msg = dataFromHook, digestmod = hashlib.sha256 ).hexdigest()

        return hmac.compare_digest( str( expected ), str( signature ) )