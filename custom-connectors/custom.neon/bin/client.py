#!/usr/bin/env python3
"""MuseNeon client: Neon management API v2 with a personal API key.

The key is never in this file, in a command argument, or in a log: the
client applies it through Muse's sanctioned helper
``add_surrogate_to_request`` (bearer_header placement), which sets
``Authorization: Bearer <surrogate>`` on the request itself. Neon needs
no prefix beyond ``Bearer ``, so the secure flow's bearer placement fits
exactly, like Buffer.

Secrets the API returns are stripped before anything reaches stdout:
role passwords are removed, and connection URIs are printed with the
password replaced by ``****``. The full URI is copied from the Neon
console to the deployment host inside the browser, never through chat.

There is deliberately no run-sql operation: the management API has no
SQL-execution endpoint. SQL runs over the Postgres wire protocol with a
normal Postgres driver, using the connection string from
``get-connection-string``.

Usage:
  client.py list-projects [--limit N] [--cursor <cursor>] [--search <text>]
  client.py get-project --project-id <id>
  client.py create-project --name <name> [--region-id <region>] [--pg-version N] [--database-name <db>] [--role-name <role>] [--branch-name <branch>]
  client.py delete-project --project-id <id>
  client.py list-branches --project-id <id> [--limit N] [--cursor <cursor>]
  client.py create-branch --project-id <id> [--name <name>] [--parent-id <branch-id>] [--parent-timestamp <RFC 3339>]
  client.py list-databases --project-id <id> --branch-id <branch-id>
  client.py create-database --project-id <id> --branch-id <branch-id> --name <name> --owner-name <role>
  client.py list-roles --project-id <id> --branch-id <branch-id>
  client.py create-role --project-id <id> --branch-id <branch-id> --name <name>
  client.py get-connection-string --project-id <id> --database-name <db> --role-name <role> [--branch-id <branch-id>] [--pooled]
  client.py get-operation --project-id <id> --operation-id <id>
  client.py list-regions
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import (
    DynamicCredentialError,
    add_surrogate_to_request,
    ensure_allowed_url,
)

PROVIDER = "custom.neon"
BASE = "https://console.neon.tech/api/v2"
ALLOWED_HOSTS = ["console.neon.tech"]
USER_AGENT = "MuseNeon/0.1 (https://github.com/reblox01/MuseNeon)"
TIMEOUT = 30
POLL_TIMEOUT_SECONDS = 120
POLL_INTERVAL_SECONDS = 2
PG_VERSIONS = (14, 15, 16, 17, 18, 19)


class NeonError(RuntimeError):
    """A transport or API failure. The operation was not replayed."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise NeonError("Neon endpoint redirected; verify the endpoint before continuing")


def _check_id(value, name):
    if not isinstance(value, str) or not value.strip():
        raise NeonError(f"{name} must be a non-empty id, got {value!r}")
    return value.strip()


def _check_name(value, name, max_length=256):
    if not isinstance(value, str) or not value.strip():
        raise NeonError(f"{name} must not be empty")
    value = value.strip()
    if len(value) > max_length:
        raise NeonError(f"{name} must be at most {max_length} characters, got {len(value)}")
    return value


def _check_limit(value):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise NeonError(f"limit must be a number from 1 to 400, got {value!r}") from None
    if limit < 1 or limit > 400:
        raise NeonError(f"limit must be from 1 to 400, got {limit}")
    return limit


def _check_pg_version(value):
    try:
        version = int(value)
    except (TypeError, ValueError):
        raise NeonError(f"pg-version must be one of {list(PG_VERSIONS)}, got {value!r}") from None
    if version not in PG_VERSIONS:
        raise NeonError(f"pg-version must be one of {list(PG_VERSIONS)}, got {version}")
    return version


def _mask_uri(uri):
    """Split a Postgres URI into a masked URI plus safe components.

    The password is never returned. The masked URI keeps the shape
    (``postgresql://<role>:****@<host>/<db>?sslmode=require``) so the
    caller can verify the target.
    """
    if not isinstance(uri, str) or "://" not in uri:
        return {"uri": "****"}
    parts = urllib.parse.urlsplit(uri)
    user = urllib.parse.unquote(parts.username or "")
    host = parts.hostname or ""
    port = parts.port
    database = urllib.parse.unquote(parts.path.lstrip("/"))
    query = urllib.parse.parse_qs(parts.query)
    sslmode = query.get("sslmode", [None])[0]
    masked = f"{parts.scheme}://{user}"
    if parts.password is not None:
        masked += ":****"
    masked += f"@{host}"
    if port:
        masked += f":{port}"
    masked += f"/{database}"
    if sslmode:
        masked += f"?sslmode={sslmode}"
    return {
        "uri": masked,
        "host": host,
        "port": port,
        "database": database,
        "role": user,
        "sslmode": sslmode,
    }


def _strip_secrets(value):
    """Recursively remove passwords and mask connection URIs.

    - Any ``password`` key becomes ``<issued once, not shown>``.
    - Any ``uri`` key is replaced by the masked form from ``_mask_uri``.
    Everything else passes through unchanged.
    """
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key == "password":
                cleaned[key] = "<issued once, not shown>"
            elif key in ("uri", "connection_uri"):
                cleaned[key] = _mask_uri(item)["uri"]
            else:
                cleaned[key] = _strip_secrets(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_secrets(item) for item in value]
    return value


class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(NoRedirect())

    def _request(self, method, path, body=None, params=None):
        url = BASE + path
        if params:
            query = {k: v for k, v in params.items() if v is not None}
            if query:
                url += "?" + urllib.parse.urlencode(query)
        ensure_allowed_url(url, ALLOWED_HOSTS)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        add_surrogate_to_request(req, PROVIDER, allowed_hosts=ALLOWED_HOSTS)
        try:
            return self._open(req)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                retry_after = error.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else 1.0
                except ValueError:
                    wait = 1.0
                wait = min(max(wait, 0.0), 60.0)
                time.sleep(wait)
                try:
                    return self._open(req)
                except urllib.error.HTTPError as retry_error:
                    raise NeonError(
                        f"Neon returned HTTP {retry_error.code} after waiting out "
                        "the rate limit; the operation was not replayed"
                    ) from None
            raise self._http_error(error) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise NeonError(
                "Neon request did not complete; check any write before retrying"
            ) from None

    def _http_error(self, error):
        try:
            raw = error.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        message = payload.get("message") or f"HTTP {error.code}"
        code = payload.get("code")
        detail = f"Neon returned HTTP {error.code}: {message}"
        if code:
            detail += f" (code {code})"
        if error.code == 423:
            detail += "; another operation on this project is still running, poll get-operation and retry after it finishes"
        if error.code == 401:
            detail += "; the API key is wrong, revoked, or lacks access, reconnect it through the secure flow"
        return NeonError(detail)

    def _open(self, req):
        with self.opener.open(req, timeout=TIMEOUT) as response:
            raw = response.read()
            if not raw:
                return {}
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise NeonError("Neon returned a response that was not JSON") from exc
            return _strip_secrets(payload)

    def _poll_operations(self, project_id, operations):
        """Wait until every returned operation is finished.

        Raises NeonError if any operation fails or the wait times out.
        Returns the final operation records.
        """
        pending = [op.get("id") for op in operations or [] if op.get("id")]
        if not pending:
            return []
        deadline = time.time() + POLL_TIMEOUT_SECONDS
        results = {}
        while pending:
            if time.time() > deadline:
                raise NeonError(
                    f"Neon operations did not finish within {POLL_TIMEOUT_SECONDS}s: "
                    + ", ".join(pending)
                    + "; check them with get-operation before retrying"
                )
            for operation_id in list(pending):
                record = self.get_operation(project_id, operation_id)
                status = record.get("status")
                if status in ("finished", "failed", "cancelled", "skipped"):
                    results[operation_id] = record
                    pending.remove(operation_id)
                    if status == "failed":
                        raise NeonError(
                            f"Neon operation {record.get('action', operation_id)} failed: "
                            f"{record.get('error') or 'no error text returned'}"
                        )
            if pending:
                time.sleep(POLL_INTERVAL_SECONDS)
        return [results[op_id] for op_id in results]

    # -- projects ------------------------------------------------------
    def list_projects(self, limit=10, cursor=None, search=None):
        params = {"limit": _check_limit(limit), "cursor": cursor, "search": search}
        return self._request("GET", "/projects", params=params)

    def get_project(self, project_id):
        _check_id(project_id, "project-id")
        return self._request("GET", f"/projects/{project_id}")["project"]

    def create_project(self, name, region_id=None, pg_version=None,
                       database_name=None, role_name=None, branch_name=None):
        project = {"name": _check_name(name, "name")}
        if region_id:
            project["region_id"] = _check_id(region_id, "region-id")
        if pg_version is not None:
            project["pg_version"] = _check_pg_version(pg_version)
        branch = {}
        if database_name:
            branch["database_name"] = _check_name(database_name, "database-name")
        if role_name:
            branch["role_name"] = _check_name(role_name, "role-name")
        if branch_name:
            branch["name"] = _check_name(branch_name, "branch-name")
        if branch:
            project["branch"] = branch
        result = self._request("POST", "/projects", body={"project": project})
        operations = result.get("operations") or []
        if operations:
            self._poll_operations(result["project"]["id"], operations)
        return result

    def delete_project(self, project_id):
        _check_id(project_id, "project-id")
        return self._request("DELETE", f"/projects/{project_id}")

    # -- branches ------------------------------------------------------
    def list_branches(self, project_id, limit=10, cursor=None):
        _check_id(project_id, "project-id")
        params = {"limit": _check_limit(limit), "cursor": cursor}
        return self._request("GET", f"/projects/{project_id}/branches", params=params)

    def create_branch(self, project_id, name=None, parent_id=None, parent_timestamp=None):
        _check_id(project_id, "project-id")
        branch = {}
        if name:
            branch["name"] = _check_name(name, "name")
        if parent_id:
            branch["parent_id"] = _check_id(parent_id, "parent-id")
        if parent_timestamp:
            branch["parent_timestamp"] = parent_timestamp.strip()
        result = self._request(
            "POST", f"/projects/{project_id}/branches", body={"branch": branch}
        )
        operations = result.get("operations") or []
        if operations:
            self._poll_operations(project_id, operations)
        return result

    # -- databases -----------------------------------------------------
    def list_databases(self, project_id, branch_id):
        _check_id(project_id, "project-id")
        _check_id(branch_id, "branch-id")
        return self._request(
            "GET", f"/projects/{project_id}/branches/{branch_id}/databases"
        )

    def create_database(self, project_id, branch_id, name, owner_name):
        _check_id(project_id, "project-id")
        _check_id(branch_id, "branch-id")
        body = {"database": {
            "name": _check_name(name, "name"),
            "owner_name": _check_name(owner_name, "owner-name"),
        }}
        return self._request(
            "POST", f"/projects/{project_id}/branches/{branch_id}/databases", body=body
        )

    # -- roles ---------------------------------------------------------
    def list_roles(self, project_id, branch_id):
        _check_id(project_id, "project-id")
        _check_id(branch_id, "branch-id")
        return self._request(
            "GET", f"/projects/{project_id}/branches/{branch_id}/roles"
        )

    def create_role(self, project_id, branch_id, name):
        _check_id(project_id, "project-id")
        _check_id(branch_id, "branch-id")
        if len(name.encode("utf-8")) > 63:
            raise NeonError("role name must be at most 63 bytes")
        body = {"role": {"name": _check_name(name, "name", max_length=63)}}
        return self._request(
            "POST", f"/projects/{project_id}/branches/{branch_id}/roles", body=body
        )

    # -- connection string ---------------------------------------------
    def get_connection_string(self, project_id, database_name, role_name,
                              branch_id=None, pooled=False):
        _check_id(project_id, "project-id")
        _check_name(database_name, "database-name")
        _check_name(role_name, "role-name")
        params = {
            "database_name": database_name,
            "role_name": role_name,
            "branch_id": branch_id,
            "pooled": "true" if pooled else None,
        }
        result = self._request(
            "GET", f"/projects/{project_id}/connection_uri", params=params
        )
        masked = _mask_uri(result.get("uri", ""))
        masked["pooled"] = bool(pooled)
        masked["branch_id"] = branch_id
        return masked

    # -- operations and regions ----------------------------------------
    def get_operation(self, project_id, operation_id):
        _check_id(project_id, "project-id")
        _check_id(operation_id, "operation-id")
        return self._request(
            "GET", f"/projects/{project_id}/operations/{operation_id}"
        )["operation"]

    def list_regions(self):
        return self._request("GET", "/regions")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="client.py",
        description="MuseNeon: Neon management API v2 with a personal API key.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-projects", help="Projects the key can see.")
    p.add_argument("--limit", type=int, default=10, help="How many projects, 1 to 400 (default 10).")
    p.add_argument("--cursor", help="Pagination cursor from a previous response.")
    p.add_argument("--search", help="Filter by partial project name or id.")

    p = sub.add_parser("get-project", help="One project by id.")
    p.add_argument("--project-id", required=True, help="Project id.")

    p = sub.add_parser("create-project", help="Create a project. Polls operations to finished.")
    p.add_argument("--name", required=True, help="Project name, 1 to 256 characters.")
    p.add_argument("--region-id", help="Region id, for example aws-eu-central-1. Omit for the default region.")
    p.add_argument("--pg-version", type=int, help="Postgres major version, 14 to 19.")
    p.add_argument("--database-name", help="Initial database name (default neondb).")
    p.add_argument("--role-name", help="Initial role name (default <database-name>_owner).")
    p.add_argument("--branch-name", help="Initial branch name (default main).")

    p = sub.add_parser("delete-project", help="Delete a project and everything in it. Destructive.")
    p.add_argument("--project-id", required=True, help="Project id.")

    p = sub.add_parser("list-branches", help="Branches in one project.")
    p.add_argument("--project-id", required=True, help="Project id.")
    p.add_argument("--limit", type=int, default=10, help="How many branches, 1 to 400 (default 10).")
    p.add_argument("--cursor", help="Pagination cursor from a previous response.")

    p = sub.add_parser("create-branch", help="Create a branch in a project. Polls operations to finished.")
    p.add_argument("--project-id", required=True, help="Project id.")
    p.add_argument("--name", help="Branch name.")
    p.add_argument("--parent-id", help="Parent branch id. Omit to branch from the default branch.")
    p.add_argument("--parent-timestamp", help="RFC 3339 timestamp for point-in-time branching.")

    p = sub.add_parser("list-databases", help="Databases on one branch.")
    p.add_argument("--project-id", required=True, help="Project id.")
    p.add_argument("--branch-id", required=True, help="Branch id.")

    p = sub.add_parser("create-database", help="Create a database on a branch.")
    p.add_argument("--project-id", required=True, help="Project id.")
    p.add_argument("--branch-id", required=True, help="Branch id.")
    p.add_argument("--name", required=True, help="Database name.")
    p.add_argument("--owner-name", required=True, help="Role that owns the database.")

    p = sub.add_parser("list-roles", help="Roles on one branch.")
    p.add_argument("--project-id", required=True, help="Project id.")
    p.add_argument("--branch-id", required=True, help="Branch id.")

    p = sub.add_parser("create-role", help="Create a role on a branch. The password is generated server-side, returned once, and never printed.")
    p.add_argument("--project-id", required=True, help="Project id.")
    p.add_argument("--branch-id", required=True, help="Branch id.")
    p.add_argument("--name", required=True, help="Role name, at most 63 bytes.")

    p = sub.add_parser("get-connection-string", help="Connection URI for one database as one role. The password is masked in the output.")
    p.add_argument("--project-id", required=True, help="Project id.")
    p.add_argument("--database-name", required=True, help="Database name.")
    p.add_argument("--role-name", required=True, help="Role name.")
    p.add_argument("--branch-id", help="Branch id. Omit for the default branch.")
    p.add_argument("--pooled", action="store_true", help="Return the pooled (-pooler) URI.")

    p = sub.add_parser("get-operation", help="One async operation by id.")
    p.add_argument("--project-id", required=True, help="Project id.")
    p.add_argument("--operation-id", required=True, help="Operation id.")

    sub.add_parser("list-regions", help="Regions a project can be created in.")

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = Client()
    try:
        if args.command == "list-projects":
            result = client.list_projects(args.limit, args.cursor, args.search)
        elif args.command == "get-project":
            result = client.get_project(args.project_id)
        elif args.command == "create-project":
            result = client.create_project(
                args.name, args.region_id, args.pg_version,
                args.database_name, args.role_name, args.branch_name,
            )
        elif args.command == "delete-project":
            result = client.delete_project(args.project_id)
        elif args.command == "list-branches":
            result = client.list_branches(args.project_id, args.limit, args.cursor)
        elif args.command == "create-branch":
            result = client.create_branch(
                args.project_id, args.name, args.parent_id, args.parent_timestamp
            )
        elif args.command == "list-databases":
            result = client.list_databases(args.project_id, args.branch_id)
        elif args.command == "create-database":
            result = client.create_database(
                args.project_id, args.branch_id, args.name, args.owner_name
            )
        elif args.command == "list-roles":
            result = client.list_roles(args.project_id, args.branch_id)
        elif args.command == "create-role":
            result = client.create_role(args.project_id, args.branch_id, args.name)
        elif args.command == "get-connection-string":
            result = client.get_connection_string(
                args.project_id, args.database_name, args.role_name,
                args.branch_id, args.pooled,
            )
        elif args.command == "get-operation":
            result = client.get_operation(args.project_id, args.operation_id)
        elif args.command == "list-regions":
            result = client.list_regions()
        else:  # pragma: no cover - argparse enforces the command
            raise NeonError(f"unknown command {args.command}")
    except (NeonError, DynamicCredentialError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
