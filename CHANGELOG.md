# Changelog

## 4.9.12 - February 21st, 2025

- Add `whoami` alias for `who` command.

- Fix a possible race condition when writting credentials to `~/.limacharlie` file on disk.

- Add a new global `--debug` option. When this option is set and CLI command throws
  an exception, traceback will be printed to standard error.

- Add new `limacharlie users invite` command for inviting user(s) to LimaCharlie.

  **Example usage**

  Invite a single user:
  
  ```bash
  $ limacharlie users invite --email=test1@example.com
  ```

  Invite multiple users:
  
  ```bash
  $ limacharlie users invite --email=test1@example.com,test@example.com
  ```

  Invite multiple users (new line delimited entries in a file):
  
  ```
  $ cat users_to_invite.txt
  tomaz+test1@example.com
  tomaz+test2@example.com
  tomaz+test3@example.com
  tomaz+test4@example.com

  $ limacharlie users invite --file=users_to_invite.txt
  ```

  The corresponing API operations operates in the context of the user which means you need to specify a user scoped API key + UID when using `limacharlie login`.

  For more information, see https://docs.limacharlie.io/apidocs/introduction#getting-a-jwt.
