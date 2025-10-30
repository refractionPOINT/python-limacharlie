import os

# Path to the configuration file. Can be overriden for tests.
CONFIG_FILE_PATH = os.path.expanduser( '~/.limacharlie' )

# OAuth-related constants
OAUTH_CALLBACK_TIMEOUT = 300  # 5 minutes
OAUTH_TOKEN_REFRESH_BUFFER = 300  # 5 minutes before expiry

# Ephemeral credentials mode - when set, disables all credential persistence to disk.
# This also ignores named environments stored in ~/.limacharlie (like 'production', 'staging').
# Credentials must be provided through environment variables (LC_OID, LC_API_KEY, LC_UID)
# or OAuth flows. Targeted to support dynamic multitenant environments where credentials
# are managed entirely in memory without any disk persistence.
EPHEMERAL_CREDS_ENV_VAR = 'LC_EPHEMERAL_CREDS'

# Firebase configuration
# This API key is NOT a secret - it's a public identifier for Firebase projects
# Firebase API keys are designed to be embedded in public clients and are 
# protected by Firebase Security Rules and domain restrictions.
# See: https://firebase.google.com/docs/projects/api-keys#api-keys-for-firebase-are-different
FIREBASE_API_KEY = 'AIzaSyB5VyO6qS-XlnVD3zOIuEVNBD5JFn22_1w'
