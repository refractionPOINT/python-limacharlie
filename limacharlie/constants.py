import os

# Path to the configuration file. Can be overriden for tests.
CONFIG_FILE_PATH = os.path.expanduser( '~/.limacharlie' )

# OAuth-related constants
OAUTH_CALLBACK_TIMEOUT = 300  # 5 minutes
OAUTH_TOKEN_REFRESH_BUFFER = 300  # 5 minutes before expiry
