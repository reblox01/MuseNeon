# Example: list projects

Command:

```
python3 bin/client.py list-projects --limit 10
```

Example output (ids redacted, real shape from Neon's API reference):

```json
{
  "projects": [
    {
      "id": "project-id",
      "name": "basement-tycoon",
      "region_id": "aws-eu-central-1",
      "pg_version": 17,
      "created_at": "2026-11-07T18:30:00Z"
    }
  ],
  "pagination": {
    "cursor": null
  }
}
```

Pass `--cursor <cursor>` from a previous response to page, and `--search
<text>` to filter by partial project name or id. Run this first after
connecting, to verify the key works.
