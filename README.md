# MuseNeon

Neon, inside Muse.ai.

MuseNeon is a Muse-native connector for Neon, the serverless Postgres
platform. It lets Muse create and manage Neon projects, branches,
databases, and roles, and hand back the connection string a Postgres
client needs, with your approval before anything is created or deleted.

## Status

v1 is built locally and not yet verified live. Research is done
(`docs/RESEARCH.md`): Neon's management API at
`console.neon.tech/api/v2` takes a Bearer <redacted> API key, available on
every plan including Free, so there is no prefix problem and no approval
gate. The client (`custom-connectors/custom.neon/bin/client.py`) is
written and locally tested: it compiles, `--help` exits 0, input
validation fails cleanly, and a missing credential fails with a clear
error. Live verification needs a Neon account and a connected API key,
which is the owner's step.

## What v1 covers

- list-projects, get-project, create-project, delete-project
- list-branches, create-branch
- list-databases, create-database
- list-roles, create-role
- get-connection-string (password masked in output)
- get-operation (poll async creates), list-regions

## What v1 deliberately does not do

There is **no `run-sql` operation**. Neon's management API has no
SQL-execution endpoint. SQL runs over the Postgres wire protocol with a
normal Postgres driver (psycopg), using the connection string from
`get-connection-string`, or in the Neon console SQL editor, or through
Neon's official MCP server (`https://mcp.neon.tech/mcp`), which has
`run_sql`. The connector provisions the database; it never touches the
data inside it.

## Secrets

The Neon API returns database passwords: `create-project` and
`create-branch` return connection URIs with passwords, and `create-role`
returns the generated role password once, at creation. The client strips
all of them before anything reaches stdout: passwords are removed,
connection URIs are printed with the password replaced by `****`, and the
host, database, and role are printed as separate fields. The full URI is
copied from the Neon console to the deployment host inside the browser,
never through chat. See `docs/SAFETY.md`.

## Approval gate

Reads need no approval. Every create and every delete needs the user's
explicit yes for that exact action, in chat, every time. Show the exact
project, branch, database, or role name before asking. A yes for one
project never covers another.

## Layout

- `skills/neon/` — the Muse skill (what Muse may do, and the rules).
- `custom-connectors/custom.neon/` — the connector doc and the client.
- `docs/` — architecture, safety, sources, research.
- `scripts/install.sh` — copies the skill and the connector into a workspace.
- `examples/` — redacted example calls.

## License

MIT. See `LICENSE`.
