def pytest_addoption( parser ):
    parser.addoption( "--oid", action = "store", required = True )
    parser.addoption( "--key", action = "store", required = True )

def pytest_generate_tests( metafunc ):
    option_value = metafunc.config.option.oid
    if "oid" in metafunc.fixturenames and option_value is not None:
        metafunc.parametrize( "oid", [ option_value ] )
    option_value = metafunc.config.option.key
    if "key" in metafunc.fixturenames and option_value is not None:
        metafunc.parametrize( "key", [ option_value ] )