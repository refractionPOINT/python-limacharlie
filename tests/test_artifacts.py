import limacharlie
import uuid
import os
import time

def test_artifact_lifecycle( oid, key ):
    lc = limacharlie.Manager( oid, key )

    assert( lc.testAuth( [
        'org.get',
        'insight.evt.get',
        'insight.list',
        'ingestkey.ctrl',
    ] ) )

    # Create a new ingestion key.
    keyName = "test_ingestion_%s" % ( uuid.uuid4(), )

    keyVal = lc.setIngestionKey( keyName )
    assert( keyVal.get( 'key', False ) )
    keyVal = keyVal[ 'key' ]

    source = "test-%s" % ( uuid.uuid4(), )

    try:
        artifactService = limacharlie.Artifacts( lc, keyVal )

        # Create 3 test artifacts locally.
        assert( 0 == os.system( "echo 'test file 1' > test1.txt" ) )
        assert( 0 == os.system( "echo 'test file 2' > test2.txt" ) )
        assert( 0 == os.system( "echo 'test file 3' > test3.txt" ) )

        # Upload 3 test artifacts.
        uploadTime = int( time.time() )

        for filePath in ( 'test1.txt', 'test2.txt', 'test3.txt' ):
            resp = artifactService.upload( filePath,
                                           source = source,
                                           hint = 'txt',
                                           originalPath = filePath,
                                           nDaysRetention = 2 )
            assert( resp )

        # Give it a few seconds to make sure the new artifacts
        # have made it through ingestion.
        time.sleep( 10 )

        # Iterate over them to make sure we see them.
        nArtifacts = 0
        for artifactInfo, artifactTmpFile in artifactService.listArtifacts( type = 'txt',
                                                                            source = source,
                                                                            after = uploadTime - 60,
                                                                            before = int( time.time() ) + 60,
                                                                            withData = True ):
            try:
                nArtifacts += 1
                assert( artifactInfo )
                artifactData = open( artifactTmpFile, 'rb' ).read().decode()
                assert( artifactData.startswith( 'test file ' ) )
            finally:
                os.remove( artifactTmpFile )

        assert( 3 == nArtifacts )

    finally:
        lc.delIngestionKey( keyName )