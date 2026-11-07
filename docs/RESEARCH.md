# Neon custom connector for Muse — Research

Date: 7 Nov 2026. Research only: no repo created yet, nothing posted, no
credential collected or used, nothing installed, no live Neon calls made.
All endpoint facts below were read from Neon's official OpenAPI 3.0 spec
(v2), downloaded 7 Nov 2026 from
`https://neon.com/api_spec/release/v2.json`, and cross-checked against
`https://neon.com/docs/reference/api/get-started`,
`https://neon.com/docs/reference/api/key-concepts`, and
`https://neon.com/docs/reference/api-reference`.

## 1. Verdict: recommended architecture

**Build a direct REST client in Python (stdlib only), shaped like the
MuseBuffer client, talking to `https://console.neon.tech/api/v2` with a
personal API key sent as `Authorization: Bearer <key>`. Do not bundle, fork,
or depend on a community MCP server.**

Why this shape wins for Muse:

- The MuseBuffer pattern already works for this exact auth shape: a single
  `bin/client.py` using Muse's sanctioned helper
  `add_surrogate_to_request` with `bearer_header` placement, which sets
  `Authorization: Bearer <surrogate>` on the request itself. Neon needs no
  prefix beyond `Bearer `, so the secure flow fits exactly, like Buffer.
  There is no Discord-style prefix problem here.
- The credential lives in the registered connection `custom.neon`, never in
  a file. The client never builds the header by hand and never prints the
  key.
- No extra process. The official Neon MCP server
  (`https://mcp.neon.tech/mcp`) exists and is maintained by Neon, and it
  offers `run_sql` and friends, but it is a long-lived remote service whose
  tool surface is generated from the whole API, including writes. A thin
  REST client with eleven named operations is reviewable in one sitting,
  and the operations, approval gate, and repo stay under our control. The
  MCP server is documented in the connector doc as the alternative route,
  exactly as the Buffer doc documents Buffer's MCP server.

What v1 deliberately is not: no SQL execution (see section 5), no Neon
Auth, no Data API, no functions, no snapshots, no VPC endpoints, no
consumption metrics. Provisioning only: projects, branches, databases,
roles, endpoints (read), operations (read), regions (read).

## 2. What Neon offers

- **Management API v2**, base `https://console.neon.tech/api/v2`. All v1
  operations go here. 194 endpoints across 20 resources in the spec; v1
  uses eleven operations from six resources.
- **Postgres wire protocol** (TCP) for SQL, using the connection URI from
  `GET /projects/{project_id}/connection_uri`. This is how the Basement
  Tycoon bot will run SQL (psycopg). Not part of this connector.
- **Neon serverless driver HTTP endpoint**: `POST https://<ep-host>/sql`
  with a `Neon-Connection-String` header. Not part of this connector (see
  section 5).
- **Neon Data API** (PostgREST-style REST access to a database, provisioned
  per branch). Not part of v1.
- **Official MCP server** (`https://mcp.neon.tech/mcp`, repo
  `neondatabase/mcp-server-neon`). Alternative route, not used by this
  connector.

## 3. Auth: API key, Bearer, no prefix problem

Three API key types exist, all sent the same way:

| Key type | Scope | Best for |
|---|---|---|
| **Personal API key** | All organization projects where the user is a member | Personal development, scripts. This is the route for v1. |
| **Organization API key** | All projects within an organization | Team automation, CI/CD |
| **Project-scoped API key** | Single project only | Limited-access integrations |

Create a key in the Neon Console under **Account settings > API keys**.
Every request carries `Authorization: Bearer <key>`. The credential is
registered as provider `neon`, auth scheme `api_key`, host
`console.neon.tech`, placement `bearer_header`. A key acts as the account
that created it; a personal key reaches every project on that account,
so the connector can see everything the Neon account can see.

Note the base URL: it is `console.neon.tech/api/v2`, not `api.neon.tech`.
The `api.neon.tech` host appears in older material and is not the
management API base.

## 4. Verified v1 endpoints

Base: `https://console.neon.tech/api/v2`. Error body on failure:
`{"message": ..., "code": ..., "request_id": ...}`. `POST`, `PATCH`,
`DELETE`, `PUT` are non-idempotent: do not retry a failed write blindly;
inspect current state first. `GET` is safe to retry. `503` is always safe
to retry; `423 Locked` (a conflicting operation is still running) is safe
to retry after polling.

### Projects

| Operation | Method and path | Request | Response |
|---|---|---|---|
| `list-projects` | `GET /projects` | Query: `limit` 1-400, `cursor`, `search` (partial name or id), `org_id` | `{projects: [{id, name, region_id, pg_version, created_at, ...}], pagination: {cursor}}` |
| `get-project` | `GET /projects/{project_id}` | — | `{project: {id, name, region_id, pg_version, proxy_host, store_passwords, created_at, updated_at, ...}}` |
| `create-project` | `POST /projects` | `{project: {name, region_id?, pg_version?, branch?: {name?, database_name?, role_name?}, org_id?}}` | 201: `{project, connection_uris, roles, databases, operations, branch, endpoints}`. **Contains passwords**: the client strips them before printing. See section 6. |
| `delete-project` | `DELETE /projects/{project_id}` | — | `{project}`. Deleted projects can be recovered with `POST /projects/{project_id}/recover` (not in v1). |

Create-project defaults, from the spec: branch name `main` if omitted,
database name `neondb` if omitted, role name `{database_name}_owner` if
omitted. `pg_version` accepts 14, 15, 16, 17, 18; 19 is rolling out. If
`region_id` is omitted the API picks the default region. Project names are
1-256 characters. Creation is asynchronous: the response carries an
`operations` array; wait until the operations are `finished` before
connecting to the database.

### Branches

| Operation | Method and path | Request | Response |
|---|---|---|---|
| `list-branches` | `GET /projects/{project_id}/branches` | Query: `limit`, `cursor` | `{branches: [{id, project_id, parent_id, name, current_state, primary, default, created_at, ...}], pagination}` |
| `create-branch` | `POST /projects/{project_id}/branches` | `{branch: {name?, parent_id?, parent_lsn?, parent_timestamp?}, endpoints?: [...]}` | 201: `{branch, endpoints, operations, roles, databases, connection_uris?}`. **Contains passwords**: stripped before printing. |

`parent_id` omitted means branch from the project's default branch.
`parent_timestamp` is RFC 3339, for point-in-time branching. If
`endpoints` is omitted the branch is created **without any compute
endpoint** and cannot serve queries until one is added
(`POST /projects/{project_id}/endpoints`, not in v1). The default branch
created with a project gets a read-write endpoint automatically.

### Databases

| Operation | Method and path | Request | Response |
|---|---|---|---|
| `list-databases` | `GET /projects/{project_id}/branches/{branch_id}/databases` | — | `{databases: [{id, branch_id, name, owner_name, created_at, updated_at}]}` |
| `create-database` | `POST /projects/{project_id}/branches/{branch_id}/databases` | `{database: {name, owner_name}}` (both required) | 201: `{database, operations}` |

### Roles

| Operation | Method and path | Request | Response |
|---|---|---|---|
| `list-roles` | `GET /projects/{project_id}/branches/{branch_id}/roles` | — | `{roles: [{branch_id, name, protected, created_at, updated_at}]}` |
| `create-role` | `POST /projects/{project_id}/branches/{branch_id}/roles` | `{role: {name, no_login?}}` (`name` required, max 63 bytes) | 201: `{role, operations}`. **The role password is generated server-side and returned in the response only at creation** (and on reset). The client never prints it. See section 6. |

### Connection string

| Operation | Method and path | Request | Response |
|---|---|---|---|
| `get-connection-string` | `GET /projects/{project_id}/connection_uri` | Query: `database_name` (required), `role_name` (required), `branch_id` (default: project's default branch), `endpoint_id` (default: the branch's read-write endpoint), `pooled` (adds `-pooler` to the URI when `true`) | `{uri: "postgresql://<role>:<password>@<host>/<db>?sslmode=require"}`. **The URI contains the role password**: the client prints it masked. See section 6. |

### Operations (polling) and regions (read)

| Operation | Method and path | Notes |
|---|---|---|
| `get-operation` | `GET /projects/{project_id}/operations/{operation_id}` | `{operation: {id, project_id, branch_id?, endpoint_id?, action, status, error?, failures_count, created_at, updated_at, total_duration_ms}}`. Status: `scheduling`, `running`, `finished`, `failed`, `cancelling`, `cancelled`, `skipped`. The client polls this after `create-project` and `create-branch` until every returned operation is `finished` (or one fails). |
| `list-regions` | `GET /regions` | `{regions: [{region_id, name, default, geo_lat, geo_long}]}`. Query `org_id` for org-scoped availability. Added to v1 because `create-project` needs a `region_id` and the caller should be able to list the real choices instead of guessing. |

### Rate limits and pagination

- 700 requests per minute (~11/second), 40 requests per second burst
  limit per route, 10 per second for organization API key creation.
  Exceeding them returns HTTP 429. Retry with exponential backoff.
- Cursor pagination on list endpoints: `limit` and `cursor` query
  parameters; the next `cursor` comes in the `pagination` object of the
  previous response.

### Constraints that shape the client

- You cannot delete a project's root or default branch.
- You cannot delete a branch that has child branches; delete children first.
- Creating a new role may drop existing connections to the active compute
  endpoint.
- A branch can have only one `read_write` endpoint but multiple
  `read_only` endpoints.
- Overlapping operations on a project return `423 Locked`. Poll for
  completion first, then retry.

## 5. How SQL runs: NOT through this connector

**The management API has no run-SQL endpoint.** This was checked three
ways: the full OpenAPI spec (131 paths, no query/SQL-execution operation),
Neon's docs, and the official MCP server's tool list (its `run_sql` runs
over the database connection, not the management API). SQL against a Neon
database runs over one of these paths instead:

1. **Postgres wire protocol (TCP)** with a normal Postgres driver
   (psycopg in Python), using the connection URI from
   `get-connection-string`. This is what the Basement Tycoon bot will do.
   The bot connects directly; the connector only provisions the database
   and hands back the (masked) connection string.
2. **Neon serverless driver HTTP endpoint**: `POST
   https://<ep-host>/sql` with a `Neon-Connection-String` header. The
   `<ep-host>` is per-branch (e.g. `ep-xxx.us-east-2.aws.neon.tech`), so
   it cannot be pre-registered in the secure flow's `api_hosts`, and the
   credential it needs is the database password, not the API key. Not in
   v1, and not addable without a per-branch host registration.
3. **Neon Data API** (PostgREST-style REST access, provisioned per
   branch). Separate surface, out of v1.
4. **Official Neon MCP server** (`https://mcp.neon.tech/mcp`), whose
   `run_sql` / `run_sql_transaction` tools run SQL over the database
   connection. That is the alternative route for interactive SQL, not this
   connector.

Consequence for the connector: there is deliberately **no `run-sql`
operation in v1**. The skill says so plainly, and the connector doc
repeats it. Anyone who needs to run SQL uses the bot's psycopg connection,
the Neon console SQL editor, or the MCP server.

## 6. Secrets: what the API returns and what the client prints

Three v1 responses carry secrets, and the client strips them before
anything reaches stdout:

- `create-project` returns `connection_uris` (full URIs with passwords)
  and `roles` (with passwords at creation).
- `create-branch` can return `connection_uris` and `roles` the same way.
- `create-role` returns the generated role password once, in the response.
  It is never returned again on reads; the only later routes to it are
  `GET .../roles/{role_name}/reveal_password` (not in v1) and the
  connection URI.
- `get-connection-string` returns a URI with the password embedded.

Client rules (implemented in `bin/client.py`, `_strip_secrets`):

- Every `password` key is removed from printed output and replaced with
  the note `<issued once, not shown>`.
- Every `uri` / `connection_uri` value is printed with the password
  replaced by `****`, and the host, database, role, and `sslmode` are
  printed as separate fields so the caller can verify the target without
  the password.
- The full URI (with password) is never printed, never written to a file,
  and never passed as a command argument. It is copied from the Neon
  console to the Render dashboard inside the browser, the same
  portal-to-Render path the Discord bot token already uses. Nothing about
  the database password ever goes through chat.

## 7. Free tier facts (relevant to the connector)

Neon Free, verified Nov 2026 against Neon's own free-plan comparison and
pricing pages:

- 100 projects per organization, 1 GB of Postgres storage per project
  (20 GB total across the account), 100 CU-hours of compute per project
  per month, 5 GB egress per project.
- Compute autoscales 0.25 to 2 CU and scales to zero after 5 minutes
  idle, then wakes automatically on the next query (a few hundred
  milliseconds). No manual resume, unlike Supabase's 7-day pause.
- A free account can do everything in v1 through the API: projects,
  branches, databases, roles, endpoints. There is no API-only paid gate
  on any v1 operation.
- The Basement Tycoon database will be kilobytes with a few dozen queries
  a day, far inside every free limit. The binding constraint on the free
  tier is the 100 CU-hours per project per month, and scale-to-zero keeps
  this bot well under it.

## 8. Why this connector exists

The Basement Tycoon Discord bot (local repo
`~/workspace/basement-tycoon`, Python discord.py, currently SQLite) is
moving its database to Neon Postgres. The connector lets Muse create and
manage that Neon database: create the project, keep the default branch,
create the `basement_tycoon` database and a dedicated role, and hand back
the connection string the bot will use as `DATABASE_URL` on Render. The
bot itself then connects over the Postgres wire with psycopg; the
connector never touches the game data.

## 9. Out of scope in v1

Neon Auth, Data API, functions, snapshots, VPC endpoints, consumption
metrics, organizations, API key management, endpoint create/update/delete,
branch delete, database delete, role delete, role password reset/reveal,
project update, project transfer/recover. Each is a candidate for a later
version, with its own allowlist entry and its own user approval. SQL
execution is out of v1 by design (section 5), not by omission.

## 10. Sources

- Neon API OpenAPI 3.0 spec (v2), downloaded 7 Nov 2026:
  `https://neon.com/api_spec/release/v2.json` — the endpoint inventory,
  request/response schemas, and error shape above.
- Neon API get started, `https://neon.com/docs/reference/api/get-started`
  — base URL, key types, Bearer <redacted>
- Neon API key concepts,
  `https://neon.com/docs/reference/api/key-concepts` — async operations,
  rate limits (700/min, 40/sec burst), cursor pagination, constraints
  (423, branch deletion, role creation dropping connections).
- Neon API reference, `https://neon.com/docs/reference/api-reference` —
  194 endpoints across 20 resources, endpoint index.
- Neon vs Supabase free tier, `https://neon.com/guides/neon-vs-supabase-free-plan`
  — Free: 100 projects, 1 GB storage per project, 100 CU-hours per
  project, 5 GB egress, scale-to-zero after 5 minutes, auto-wake.
- Neon MCP server, `https://mcp.neon.tech/mcp` (repo
  `neondatabase/mcp-server-neon`) — alternative route with `run_sql`;
  documented, not used.
- Neon serverless driver HTTP query protocol — `POST
  https://<ep-host>/sql` with `Neon-Connection-String` header; per-branch
  host, database password as credential.
