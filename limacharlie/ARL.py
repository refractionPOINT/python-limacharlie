from arl import AuthenticatedResourceLocator as arl

class ARL( object ):
    def __init__( self, resource ):
        self.resource = resource

    def get_arl(self, resource):

        with arl( resource ) as res:
            for fileName, fileData in res:            
                print("File name: %s\nFile contents:\n%s\n\n" % (fileName, fileData))


def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie get-arl' )
    parser.add_argument( '-a', '--arl',
                         type = str,
                         required = True,
                         dest = 'arl',
                         help = 'the ARL to query')
    
    args = parser.parse_args( sourceArgs )

    arls = ARL( resource = args.arl )

    print( "Querying ARL at %s" % ( args.arl ) )

    _ = arls.get_arl(
        args.arl
    )
