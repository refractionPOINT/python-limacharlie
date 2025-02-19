import os
import sys

# Get the directory of the current conftest.py file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Calculate the project root (adjust the number of ".." if needed)
project_root = os.path.abspath(os.path.join(current_dir, '../../'))

# Insert the project root at the beginning of sys.path
if project_root not in sys.path:
    sys.path.insert(0, project_root)