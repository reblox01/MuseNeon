# MuseNeon sources

Primary sources used for the research and the client, all read 7 Nov 2026.

- Neon API OpenAPI 3.0 spec (v2),
  `https://neon.com/api_spec/release/v2.json` — the endpoint inventory,
  request/response schemas, and error shape. 131 paths in the downloaded
  spec; v1 uses eleven operations from six resources.
- Neon API get started,
  `https://neon.com/docs/reference/api/get-started` — base URL
  `https://console.neon.tech/api/v2`, key types (personal, organization,
  project-scoped), Bearer authentication, first `GET /projects` call.
- Neon API key concepts,
  `https://neon.com/docs/reference/api/key-concepts` — async operations
  and the `operations` array, rate limits (700/min, 40/sec burst per
  route), cursor pagination, constraints (423 Locked, branch deletion,
  role creation dropping connections).
- Neon API reference, `https://neon.com/docs/reference/api-reference` —
  194 endpoints across 20 resources, endpoint index.
- Neon vs Supabase free tier,
  `https://neon.com/guides/neon-vs-supabase-free-plan` — Free: 100
  projects, 1 GB storage per project (20 GB account total), 100
  CU-hours per project per month, 5 GB egress, scale-to-zero after 5
  minutes, auto-wake within a few hundred milliseconds.
- Neon MCP server, `https://mcp.neon.tech/mcp` (repo
  `neondatabase/mcp-server-neon`) — the official alternative route with
  `run_sql` / `run_sql_transaction`; documented, not used by this
  connector.
- Neon serverless driver HTTP query protocol — `POST
  https://<ep-host>/sql` with a `Neon-Connection-String` header; the host
  is per-branch and the credential is the database password, not the API
  key, so it cannot go through this connector's secure flow.
