# MentorMan

## Whose data is "mine"

When Gopinath asks to fetch his own data (topics, sessions, skill graph, L1 profile,
L3 memories), it means this account — don't ask which one:

- email: `gbnathworkspace@gmail.com`
- `user_id`: `79922c67-6de1-41be-93f5-d7892e70ca9f`

Every other row in `users` is a test account.

## Querying the DB

Creds live in `unified-backend/.env` (`MONGODB_URI`, `DATABASE_NAME`). Run one-off
scripts with `unified-backend/.venv/Scripts/python.exe`, and set
`PYTHONIOENCODING=utf-8` — the Windows console is cp1252 and crashes on stored
unicode.

The `topics` collection is camelCase (`userId`, `topicId`, `lastActiveAt`); every
other collection is snake_case (`user_id`). Filtering topics on `user_id` silently
returns 0 rows instead of erroring.
