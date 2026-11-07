# MuseNeon connector (`custom.neon`)

Neon, inside Muse.ai. This connector lets Muse create and manage Neon
serverless Postgres projects, branches, databases, and roles, and get
the connection string a Postgres client needs, using Neon's management
API v2 at `https://console.neon.tech/api/v2`.

## Auth

Personal API key only.

1. Create a free Neon account at neon.tech if you do not have one.
2. In the Neon Console, go to Account settings, then API keys, and
   create a personal API key. For a single-project integration, create a
   project-scoped key instead.
3. Connect the key through Muse's secure flow as provider `neon`, auth
   scheme `api_key`, host `console.neon.tech`, placement `bearer_header`.
   The key is never typed in chat, never pasted into a file, and never
   appears in a log.
4. Verify with `list-projects`. It returns the projects the key can see.

The key acts as the account that created it and reaches every project
on that account. There is no per-project scoping on a personal key, so
the connector can see everything your Neon account can see. Neon's own
MCP server (`https://mcp.neon.tech/mcp`) is a separate route to the same
platform, with `run_sql` and friends; this connector uses the direct
REST client instead, so the operations, the approval gate, and the repo
stay under our control.

## Client

`bin/client.py`, Python stdlib only. It sends one REST call per
operation to `https://console.neon.tech/api/v2` and applies the key with
Muse's sanctioned helper (`add_surrogate_to_request`, bearer_header
placement), which sets `Authorization: Bearer <surrogate>` itself. The
client never builds the header by hand and never prints the key.

Run from the connector folder:

```
python3 bin/client.py list-projects [--limit N] [--cursor <cursor>] [--search <text>]
python3 bin/client.py get-project --project-id <id>
python3 bin/client.py create-project --name <name> [--region-id <region>] [--pg-version N] [--database-name <db>] [--role-name <role>] [--branch-name <branch>]
python3 bin/client.py delete-project --project-id <id>
python3 bin/client.py list-branches --project-id <id> [--limit N] [--cursor <cursor>]
python3 bin/client.py create-branch --project-id <id> [--name <name>] [--parent-id <branch-id>] [--parent-timestamp <RFC 3339>]
python3 bin/client.py list-databases --project-id <id> --branch-id <branch-id>
python3 bin/client.py create-database --project-id <id> --branch-id <branch-id> --name <name> --owner-name <role>
python3 bin/client.py list-roles --project-id <id> --branch-id <branch-id>
python3 bin/client.py create-role --project-id <id> --branch-id <branch-id> --name <name>
python3 bin/client.py get-connection-string --project-id <id> --database-name <db> --role-name <role> [--branch-id <branch-id>] [--pooled]
python3 bin/client.py get-operation --project-id <id> --operation-id <id>
python3 bin/client.py list-regions
```

`create-project` defaults to branch `main`, database `neondb`, role
`<database-name>_owner`, and the API's default region when no region is
given. `pg-version` accepts 14 to 19. Creating a project or a branch is
asynchronous: the client polls the returned operations until they are
`finished` (up to 120 seconds) before returning. A branch created
without endpoints has no compute endpoint and cannot serve queries; the
default branch created with a project gets a read-write endpoint
automatically.

## Passwords and connection strings

The Neon API returns database passwords. `create-project` and
`create-branch` return connection URIs with passwords, and
`create-role` returns the generated role password once, at creation.
The client strips all of them before anything reaches stdout: every
`password` field is removed, every connection URI is printed with the
password replaced by `****`, and the host, database, and role are
printed as separate fields. `get-connection-string` prints the URI
masked the same way.

The full URI (with password) is never printed, never written to a file,
and never passed as a command argument. Copy it from the Neon console
to the deployment host inside the browser, the same portal-to-host path
the Discord bot token already uses. Nothing about the database password
ever goes through chat.

## No SQL execution

There is deliberately no `run-sql` operation. Neon's management API has
no SQL-execution endpoint. SQL runs over the Postgres wire protocol with
a normal Postgres driver (psycopg), using the connection string from
`get-connection-string`, or in the Neon console SQL editor, or through
Neon's official MCP server. This connector provisions the database; it
never touches the data inside it.

## Approval gate

Reads need no approval. Every `create-project`, `delete-project`,
`create-branch`, `create-database`, and `create-role` needs the user's
explicit yes for that exact action, in chat, every time. Show the exact
project, branch, database, or role name before asking. The skill
enforces this; the client does not bypass it.

## Errors

- HTTP 429 means a rate window is exhausted. The client waits for
  `Retry-After` (clamped 0 to 60 seconds) once, then reports the
  failure. Neon allows 700 requests per minute, 40 per second burst
  per route.
- HTTP 423 Locked means another operation on the project is still
  running. Poll `get-operation` and retry after it finishes; do not
  retry a write blindly.
- HTTP 401 means the key is wrong, revoked, or the account lost access.
  Reconnect the key through the secure flow; do not paste a new key in
  chat.
- HTTP 404 on a project, branch, database, or role means the id or name
  is wrong or the object was deleted. Check the id with the matching
  list operation before retrying.
- A failed async operation is reported with the operation's `error`
  text. The create did not complete; check state with the matching list
  operation before retrying, or the retry may create a duplicate.
- On a network error or timeout, the request may have reached Neon even
  though the response did not come back. Check current state before
  retrying any write.

## Rate limits

700 requests per minute (~11 per second), 40 requests per second burst
limit per route. The client honors `Retry-After` on 429 and never
retries blindly.
