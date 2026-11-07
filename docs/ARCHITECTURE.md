# MuseNeon architecture

## Data model

Neon's model is short: an account holds projects, a project holds
branches, a branch holds databases and roles, and a compute endpoint
serves a branch. The client follows that model down: `list-projects`
finds the projects, `list-branches` finds the branches in one project,
`list-databases` and `list-roles` find the databases and roles on one
branch, and `get-connection-string` returns the URI a Postgres client
uses to reach one database as one role.

## Transport

One endpoint: `https://console.neon.tech/api/v2`. Every operation is a
REST call with a JSON body (for POST) and a JSON response. Errors arrive
as `{"message": ..., "code": ..., "request_id": ...}` with the HTTP
status. The client treats any non-2xx as a failure and reports the
message and code; it never retries a failed write blindly, because
`POST`, `PATCH`, `DELETE`, and `PUT` are non-idempotent in Neon's own
words.

## Auth

Personal API key, Bearer. The client fetches the key as a surrogate from
Muse's secure store and applies it with the sanctioned helper
`add_surrogate_to_request` (bearer_header placement), which sets
`Authorization: Bearer <surrogate>` on the request itself. The client
never builds the header by hand and never prints the key. Neon needs no
prefix beyond `Bearer `, so the secure flow fits exactly, like Buffer.

The credential is registered as provider `neon`, auth scheme `api_key`,
host `console.neon.tech`, placement `bearer_header`. The key acts as the
account that created it and reaches every project on that account; there
is no per-project scoping on a personal key. A project-scoped key exists
for single-project integrations and is the right choice when the
connector should only ever see one project.

## Async operations

Creating a project or a branch is asynchronous. The response carries an
`operations` array with one entry per background job. The client polls
`GET /projects/{project_id}/operations/{operation_id}` for each one
until every operation is `finished`, waiting up to 120 seconds, and
reports a failure with the operation's `error` text instead of
pretending the create succeeded. Operation status values: `scheduling`,
`running`, `finished`, `failed`, `cancelling`, `cancelled`, `skipped`.

If a second write lands while an operation is still running, Neon
answers `423 Locked`. The client does not retry a 423 on its own; the
caller polls `get-operation` and retries after the first job finishes.

## Secrets in responses

Three v1 responses carry secrets: `create-project` and `create-branch`
return connection URIs (full URIs with passwords) and roles (with
passwords at creation), and `create-role` returns the generated role
password once. `get-connection-string` returns a URI with the password
embedded. The client strips all of them in `_strip_secrets` before
anything reaches stdout: every `password` key is removed, every `uri`
value is printed with the password replaced by `****`, and the host,
database, and role are printed as separate fields. The full URI is never
printed, never written to a file, and never passed as a command
argument. See `docs/SAFETY.md`.

## Operations

| Operation | REST | Notes |
|---|---|---|
| `list-projects` | `GET /projects?limit&cursor&search` | Cursor pagination, limit 1-400, default 10. |
| `get-project` | `GET /projects/{project_id}` | Full project record. |
| `create-project` | `POST /projects` | Body `{project: {name, region_id?, pg_version?, branch?: {name?, database_name?, role_name?}}}`. Defaults: branch `main`, database `neondb`, role `{database_name}_owner`. Polls operations to `finished`. |
| `delete-project` | `DELETE /projects/{project_id}` | Deletes every branch and database in the project. Recoverable in the console via `POST .../recover` (not in v1). |
| `list-branches` | `GET /projects/{project_id}/branches` | Cursor pagination. |
| `create-branch` | `POST /projects/{project_id}/branches` | Body `{branch: {name?, parent_id?, parent_timestamp?, parent_lsn?}}`. Without `endpoints` the branch has no compute endpoint. Polls operations to `finished`. |
| `list-databases` | `GET /projects/{project_id}/branches/{branch_id}/databases` | |
| `create-database` | `POST /projects/{project_id}/branches/{branch_id}/databases` | Body `{database: {name, owner_name}}`, both required. |
| `list-roles` | `GET /projects/{project_id}/branches/{branch_id}/roles` | |
| `create-role` | `POST /projects/{project_id}/branches/{branch_id}/roles` | Body `{role: {name, no_login?}}`. The password is generated server-side, returned once, and never printed. |
| `get-connection-string` | `GET /projects/{project_id}/connection_uri?database_name&role_name&branch_id?&pooled?` | `database_name` and `role_name` required. Prints the URI masked. |
| `get-operation` | `GET /projects/{project_id}/operations/{operation_id}` | Poll target for async creates. |
| `list-regions` | `GET /regions` | Regions the account can create projects in, with a `default` flag. |

## What the connector does not do

SQL execution. The management API has no run-SQL endpoint. SQL runs over
the Postgres wire protocol with a normal Postgres driver (psycopg),
using the connection string from `get-connection-string`, or in the Neon
console SQL editor, or through Neon's official MCP server
(`https://mcp.neon.tech/mcp`), which has `run_sql`. The connector
provisions the database; it never touches the data inside it.
