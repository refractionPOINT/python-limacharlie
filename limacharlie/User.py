import os
import sys

from . import Manager
from .utils import LcApiException


class User(object):
    def __init__(self, manager):
        self._manager = manager

    def invite(self, email):
        """
        Invite user with the provided email address to LimaCharlie.

        NOTE: This API operates in user context which means it needs to be called with user scoped API key.

        Args:
            email (str): Email of the user to invite.
        """
        print("Inviting user with email %s." % (email))

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

    def inviteMulti(self, emails):
        """
        Invite multiple users with the provided email addresses to LimaCharlie.

        Args:
            emails (list of str): List of emails of the users to invite.
        """
        for email in emails:
            self.invite(email=email)


def parseEmailsFromCsvString(emails):
    """
    Parse a comma separated string of emails into a list of emails.

    Args:
        emails (str): Comma separated string of emails (e.g. test1@example.com,test2@example.com).
    """
    emails = [email.strip() for email in emails.split(",")]
    return emails


def parseEmailsFromFile(file_path):
    """
    Parse a file containing emails into a list of emails.

    Args:
        file_path (str): Path to the file containing emails.
    """
    with open(file_path, "r") as f:
        # Support both \n and \r\n line endings
        emails = f.readlines()
        emails = [email.strip() for email in emails]
        emails = [email for email in emails if email]

    print("Found %d emails in the file." % (len(emails)))
    return emails


def main( sourceArgs = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie users' )
    # TODO: We should correctly use argparse subparsers everywhere or use something like click library...
    subparsers = parser.add_subparsers(title='action', dest='action', required=True)
    parserInviteAction = subparsers.add_parser('invite', help='Invite a user to the organization')
    parserInviteAction.add_argument( '--email',
                         required = False,
                         action = 'store',
                         help = 'email (e.g. test@example.com) or a comma separated list of emails (e.g. test1@example.com, test2@example.com) of the users to invite.' )
    parserInviteAction.add_argument( '--file',
                         required = False,
                         action = 'store',
                         help = 'text file which contains new line delimited list of emails of the users to invite.' )
    args = parser.parse_args( sourceArgs )

    if args.action == 'invite':
        if not args.email and not args.file:
            raise ValueError("Please provide either --email or --file option.")

        if args.email and args.file:
            raise ValueError("--email and --file are mutually exclusive, please provide only one.")
        
        if args.email:
            emails = parseEmailsFromCsvString(emails=args.email)
        elif args.file:
            emails = parseEmailsFromFile(file_path=os.path.abspath(args.file))

        manager = Manager()
        user = User( manager=manager )

        if len(emails) == 1:
            user.invite( email=emails[0] )
        else:
            user.inviteMulti( emails=emails )


if __name__ == '__main__':
    main()