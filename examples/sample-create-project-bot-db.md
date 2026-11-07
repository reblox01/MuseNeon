# Example: create the Basement Tycoon database

Command (exact project name and region shown to the user first, and run
only after their explicit yes for this exact project):

```
python3 bin/client.py create-project \
  --name basement-tycoon \
  --region-id aws-eu-central-1 \
  --database-name basement_tycoon \
  --role-name bot
```

The client polls the returned operations until they are `finished`
before returning. Example output (ids and host redacted; passwords are
never printed):

```json
{
  "project": {
    "id": "project-id",
    "name": "basement-tycoon",
    "region_id": "aws-eu-central-1",
    "pg_version": 17,
    "proxy_host": "eu-central-1.aws.neon.tech",
    "created_at": "2026-11-07T18:30:00Z"
  },
  "connection_uris": [
    {
      "uri": "postgresql://bot:****@ep-host.eu-central-1.aws.neon.tech/basement_tycoon?sslmode=require",
      "database_name": "basement_tycoon",
      "role_name": "bot"
    }
  ],
  "roles": [
    {
      "name": "bot",
      "password": "<issued once, not shown>"
    }
  ],
  "operations": [
    {
      "id": "operation-id",
      "action": "create_project",
      "status": "finished"
    }
  ]
}
```

Then get the masked connection string for the bot:

```
python3 bin/client.py get-connection-string \
  --project-id <project id> \
  --database-name basement_tycoon \
  --role-name bot
```

The full URI (with password) is copied from the Neon console to the
Render dashboard inside the browser, never through chat. The bot
connects over the Postgres wire with psycopg; this connector never runs
SQL. If the create fails, check state with `list-projects` before
retrying, or the retry may create a duplicate project.
