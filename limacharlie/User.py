import sys
from . import Manager
from .utils import LcApiException


class User(object):
    def __init__(self, manager):
        self._manager = manager

    def invite(self, email):
        """
        Invite user with the provided email address to the organization.

        NOTE: This API operates in user context which means it needs to be called with user scoped API key.

        Args:
            email (str): Email of the user to invite.
        """
        try:
            data = self._manager.inviteUser(email=email)
        except LcApiException as e:
            if e.code == 401:
                print("API returned 401. Make sure you are using a valid and user scoped API key.")
                print("For information on how to obtain / generate user scoped API key, see https://docs.limacharlie.io/apidocs/introduction#getting-a-jwt")
                print("Original error: %s" % (str(e)))
                sys.exit( 1 )
            else:
                raise e

        exists = data.get("exists", False)
        if exists:
            print("User with email %s already exists / has already been invited." % (email))
        else:
            print("User with email %s has been invited." % (email))

def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie user' )
    # TODO: We should correctly use argparse subparsers everywhere or use something like click library...
    subparsers = parser.add_subparsers(title='action', dest='action', required=True)
    parserInviteAction = subparsers.add_parser('invite', help='Invite a user to the organization')
    parserInviteAction.add_argument( '--email',
                         required = True,
                         action = 'store',
                         help = 'email of the user to invite.' )
    args = parser.parse_args( sourceArgs )

    manager = Manager()
    user = User( manager=manager )

    if args.action == 'invite':
        user.invite( email=args.email )


if __name__ == '__main__':
    main()