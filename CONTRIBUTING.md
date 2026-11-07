# Contributing to MuseNeon

## Rules

- Per-step commits: one commit per file or per coherent step, with a short
  message naming the step. Do not squash the history.
- GitHub pushes need the maintainer's approval first. Nothing is pushed
  without a separate go.
- Never commit a key, a token, a database password, a connection URI with
  a password, or a surrogate value. The CI secret grep fails the build on
  one; keep secrets in the secure flow only, and copy connection strings
  console-to-host inside the browser, never through chat or a file.
- Work on the `main` branch. There is no develop branch.
- Keep the approval gate: every new write operation needs its own
  allowlist entry in the skill and its own user approval at runtime.
- Never add a `run-sql` operation to this connector without a separate
  design decision: the management API has no SQL endpoint, and SQL
  execution needs its own approval and safety review.

## Checks before a commit

- `python3 -m py_compile custom-connectors/custom.neon/bin/client.py`
- `python3 custom-connectors/custom.neon/bin/client.py --help` exits 0.
- Run the secret grep the CI runs (see `.github/workflows/ci.yml`).

## Releases

Releases are automatic: a push to `main` that changes anything except
workflows, README, LICENSE, and assets creates a patch tag (v0.1.0, then
v0.1.1, and so on). Add `[release:minor]` or `[release:major]` to a commit
message to bump the version, or `[skip-release]` to skip tagging. The
release workflow builds the zip and attaches it to the tag.
