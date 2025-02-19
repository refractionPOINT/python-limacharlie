import os
import sys

# Get the directory of the current conftest.py file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Calculate the project root (adjust the number of ".." if needed)
project_root = os.path.abspath(os.path.join(current_dir, '../../'))

# Insert the project root at the beginning of sys.path
if project_root not in sys.path:
    sys.path.insert(0, project_root)


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