# MuseNeon safety

## Key handling

- The Neon personal API key is never typed in chat, never pasted into a
  file, and never appears in a log. It enters through Muse's secure flow
  only, as provider `neon`.
- The client fetches the key as a surrogate and applies it with
  `add_surrogate_to_request`. The surrogate value is never printed, never
  copied into a command, and never written to disk.
- The CI secret grep fails the build on a pasted key, surrogate value,
  database password, or connection URI with a password: `hsurr:` followed
  by 8 or more characters, `NEON_API_KEY=` followed by 8 or more
  characters, `Authorization: Bearer ` followed by 20 or more characters,
  or `postgresql://<user>:<password>@` with a real-looking password.
  Prose that only names a prefix, or a masked URI
  (`postgresql://<role>:****@<host>`), does not trip it.
- If a key is ever pasted in chat by mistake, revoke it in the Neon
  Console under Account settings, then API keys, and create a new one.
  Changing the key is the only reliable cleanup.

## Database passwords and connection strings

- The Neon API returns database passwords: `create-project` and
  `create-branch` return connection URIs with passwords, and
  `create-role` returns the generated role password once, at creation.
  It is never returned again on reads.
- The client strips all of them before printing: every `password` key is
  removed from output, every connection URI is printed with the password
  replaced by `****`, and the host, database, and role are printed as
  separate fields so the caller can verify the target without the
  password.
- The full connection URI (with password) is never printed, never written
  to a file, and never passed as a command argument. It is copied from
  the Neon console to the deployment host (Render environment variables)
  inside the browser, the same portal-to-host path the Discord bot token
  already uses. Nothing about the database password ever goes through
  chat.
- If a connection URI is ever pasted in chat by mistake, reset the role
  password in the Neon console (or delete the role and create a new one)
  and update the deployment host. Changing the password is the only
  reliable cleanup.

## Approval gate

- Reads (`list-projects`, `get-project`, `list-branches`,
  `list-databases`, `list-roles`, `get-connection-string`,
  `get-operation`, `list-regions`) need no approval.
- Every write (`create-project`, `delete-project`, `create-branch`,
  `create-database`, `create-role`) needs the user's explicit yes for
  that exact action, in chat, every time. Show the exact project,
  branch, database, or role name before asking. A yes for one project
  never covers another project, another branch, or another database.
- `delete-project` is destructive: it deletes every branch, database,
  and role in the project. Say so before asking, and name the project.
  A deleted project can be recovered from the Neon console, but do not
  promise recovery; treat the delete as final.
- Creating a role may drop existing connections to the active compute
  endpoint. Say so when it matters, and do not create roles against a
  live database without the user's yes.

## Scope

- A personal key acts as the account that created it and reaches every
  project on that account. Do not use a key from an account with
  projects the user did not mean to expose. For a single-project
  integration, use a project-scoped key instead.
- The client only calls `console.neon.tech`. No other host is allowed.
- v1 never runs SQL, never reads or writes table data, never touches
  Neon Auth, the Data API, functions, snapshots, or billing. Provisioning
  only.
