# MuseNeon skill

Connect Muse to Neon, the serverless Postgres platform, using the
MuseNeon connector (`custom.neon`). Create and manage Neon projects,
branches, databases, and roles, and get the connection string a Postgres
client needs, with your approval before anything is created or deleted.

## Rules

- Personal API key only, created in the Neon Console under Account
  settings, then API keys. The key acts as the account that created it
  and reaches every project on that account. Never ask for the key in
  chat and never paste it anywhere; it goes through Muse's secure flow
  only. For a single-project integration, use a project-scoped key
  instead.
- Every create and every delete (`create-project`, `delete-project`,
  `create-branch`, `create-database`, `create-role`) needs the user's
  explicit yes for that exact action, in chat, every time. Show the
  exact project, branch, database, or role name before asking. Reads
  need no approval.
- `delete-project` is destructive: it deletes every branch, database,
  and role in the project. Say so before asking, and name the project.
  A yes for one project never covers another.
- Creating a role may drop existing connections to the active compute
  endpoint. Do not create roles against a live database without the
  user's yes.
- **There is no `run-sql` operation, by design.** Neon's management API
  has no SQL-execution endpoint. SQL runs over the Postgres wire protocol
  with a normal Postgres driver (psycopg), using the connection string
  from `get-connection-string`, or in the Neon console SQL editor, or
  through Neon's official MCP server. This connector provisions the
  database; it never touches the data inside it. Do not invent a SQL
  endpoint and do not route SQL through the serverless driver HTTP
  endpoint: its host is per-branch and its credential is the database
  password, not the API key.
- **Connection strings and role passwords are never printed in full.**
  The client prints connection URIs with the password replaced by
  `****`, and prints the host, database, and role as separate fields.
  A role password is returned by the API once, at creation, and the
  client never shows it. The full URI is copied from the Neon console
  to the deployment host inside the browser, never through chat. If a
  URI or password is ever pasted in chat by mistake, reset the role
  password in the Neon console and update the deployment host.
- Creating a project or a branch is asynchronous. The client polls the
  returned operations until they finish; do not run a dependent call
  (create a database, get a connection string) until the poll says
  `finished`. If an operation fails, report its `error` text and do not
  retry the create blindly.
- Respect Neon rate limits: 700 requests per minute, 40 per second
  burst per route. The client waits for `Retry-After` on 429 once, then
  reports the failure. Do not loop reads. A `423 Locked` means another
  operation on the project is still running: poll `get-operation` and
  retry after it finishes.
- A branch created without endpoints has no compute endpoint and cannot
  serve queries. The default branch created with a project gets a
  read-write endpoint automatically. If a new branch needs to serve
  queries, creating its endpoint is a separate step (not in v1).
- On `create-project`, the defaults are branch `main`, database
  `neondb`, role `{database_name}_owner`. Name the project, region, and
  Postgres version explicitly when the user cares; otherwise let the
  API pick the default region and the current Postgres version.

## Operations

All run through the connector client. See
`custom-connectors/custom.neon/CONNECTOR.md` for the exact commands.

| Operation | What it does |
|---|---|
| `list-projects` | Projects the key can see. Default 10, max 400; `--cursor` pages, `--search` filters by partial name or id. |
| `get-project` | One project by id. |
| `create-project` | Create a project. Needs `--name`; `--region-id`, `--pg-version`, `--database-name`, `--role-name`, `--branch-name` optional. Polls operations to `finished`. |
| `delete-project` | Delete a project by id, with everything in it. Destructive; needs the user's yes and the project named. |
| `list-branches` | Branches in one project. Needs `--project-id`. |
| `create-branch` | Create a branch in a project. Needs `--project-id`; `--name`, `--parent-id`, `--parent-timestamp` optional. Polls operations to `finished`. A branch with no endpoints cannot serve queries. |
| `list-databases` | Databases on one branch. Needs `--project-id` and `--branch-id`. |
| `create-database` | Create a database on a branch. Needs `--project-id`, `--branch-id`, `--name`, `--owner-name`. |
| `list-roles` | Roles on one branch. Needs `--project-id` and `--branch-id`. |
| `create-role` | Create a role on a branch. Needs `--project-id`, `--branch-id`, `--name`. The password is generated server-side, returned once, and never printed. |
| `get-connection-string` | Connection URI for one database as one role. Needs `--project-id`, `--database-name`, `--role-name`; `--branch-id` and `--pooled` optional. Prints the URI with the password masked. |
| `get-operation` | One async operation by id. Needs `--project-id` and `--operation-id`. |
| `list-regions` | Regions a project can be created in, with a `default` flag. |

## Out of scope in v1

SQL execution (by design, see above), Neon Auth, Data API, functions,
snapshots, VPC endpoints, consumption metrics, organizations, API key
management, endpoint create/update/delete, branch delete, database
delete, role delete, role password reset/reveal, project update,
project transfer/recover. Each is a candidate for a later version, with
its own allowlist entry and its own user approval.

## Related

- Connector doc: `custom-connectors/custom.neon/CONNECTOR.md`
- Safety, passwords, and the approval gate: `docs/SAFETY.md`
- Architecture and research: `docs/ARCHITECTURE.md`, `docs/RESEARCH.md`
