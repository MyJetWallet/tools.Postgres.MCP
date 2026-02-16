# PostgreSQL MCP Server Setup Guide

Practical guide for connecting AI agents to PostgreSQL analytics data using ready-to-use MCP servers.

---

## TL;DR Recommendation

**Use:** `crystaldba/postgres-mcp` (Python, Docker-ready, read-only by default)

```bash
# Quick start
docker run -i --rm \
  -e DATABASE_URI="postgresql://readonly_user:password@your-host:5432/fintech_db" \
  crystaldba/postgres-mcp
```

**Why this one:**

- Read-only by default (safe for production)
- Simple connection string configuration
- Active maintenance
- MIT license
- Docker + pip installation options

---

## Part 1: Database Preparation

### Step 1: Create Analytics Views

Create views that aggregate your operational data. AI will query these views, not base tables.

```sql
-- ============================================
-- DAILY ACTIVE USERS
-- ============================================
CREATE OR REPLACE VIEW v_daily_active_users AS
SELECT
    date_trunc('day', last_activity)::date AS day,
    COUNT(DISTINCT user_id) AS active_users,
    COUNT(DISTINCT CASE WHEN created_at::date = date_trunc('day', last_activity)::date THEN user_id END) AS new_users
FROM user_sessions
WHERE last_activity > CURRENT_DATE - INTERVAL '90 days'
GROUP BY 1
ORDER BY 1 DESC;

-- ============================================
-- CARDS CREATED
-- ============================================
CREATE OR REPLACE VIEW v_cards_created AS
SELECT
    date_trunc('day', created_at)::date AS day,
    card_type,
    COUNT(*) AS cards_created,
    COUNT(DISTINCT user_id) AS unique_users
FROM cards
WHERE created_at > CURRENT_DATE - INTERVAL '90 days'
GROUP BY 1, 2
ORDER BY 1 DESC;

-- ============================================
-- USER REGISTRATIONS
-- ============================================
CREATE OR REPLACE VIEW v_user_registrations AS
SELECT
    date_trunc('day', registered_at)::date AS day,
    registration_source,
    COUNT(*) AS registrations,
    COUNT(*) FILTER (WHERE kyc_completed) AS kyc_completed,
    ROUND(COUNT(*) FILTER (WHERE kyc_completed)::numeric / NULLIF(COUNT(*), 0) * 100, 1) AS kyc_rate_pct
FROM users
WHERE registered_at > CURRENT_DATE - INTERVAL '90 days'
GROUP BY 1, 2
ORDER BY 1 DESC;

-- ============================================
-- TRANSACTION SUMMARY (no PII)
-- ============================================
CREATE OR REPLACE VIEW v_transaction_summary AS
SELECT
    date_trunc('day', created_at)::date AS day,
    transaction_type,
    currency,
    COUNT(*) AS tx_count,
    SUM(amount) AS total_volume,
    AVG(amount)::numeric(12,2) AS avg_amount
FROM transactions
WHERE created_at > CURRENT_DATE - INTERVAL '90 days'
  AND status = 'completed'
GROUP BY 1, 2, 3
ORDER BY 1 DESC;
```

### Step 2: Create Read-Only User

```sql
-- Create read-only role
CREATE ROLE mcp_readonly;

-- Grant access ONLY to analytics views
GRANT CONNECT ON DATABASE fintech_db TO mcp_readonly;
GRANT USAGE ON SCHEMA public TO mcp_readonly;

GRANT SELECT ON v_daily_active_users TO mcp_readonly;
GRANT SELECT ON v_cards_created TO mcp_readonly;
GRANT SELECT ON v_user_registrations TO mcp_readonly;
GRANT SELECT ON v_transaction_summary TO mcp_readonly;

-- Allow schema discovery (needed by MCP servers)
GRANT SELECT ON information_schema.tables TO mcp_readonly;
GRANT SELECT ON information_schema.columns TO mcp_readonly;

-- BLOCK access to base tables
REVOKE ALL ON users FROM mcp_readonly;
REVOKE ALL ON transactions FROM mcp_readonly;
REVOKE ALL ON cards FROM mcp_readonly;

-- Create login user
CREATE USER mcp_agent WITH PASSWORD 'your-secure-password';
GRANT mcp_readonly TO mcp_agent;

-- Safety limits
ALTER ROLE mcp_agent SET statement_timeout = '30s';
```

**Connection string:**

```
postgresql://mcp_agent:your-secure-password@your-postgres-host:5432/fintech_db
```

---

## Part 2: MCP Server Selection

### Comparison of Ready-to-Use Options

| Server                                    | Read-Only      | View Filtering | Docker | Best For             |
| ----------------------------------------- | -------------- | -------------- | ------ | -------------------- |
| **crystaldba/postgres-mcp**               | ✅ Default     | DB-level       | ✅     | Production analytics |
| **MCP-PostgreSQL-Ops**                    | ✅ Always      | DB-level       | ✅     | Ops monitoring       |
| **@modelcontextprotocol/server-postgres** | ✅ Enforced    | None           | ✅     | Simple queries       |
| **HenkDz/postgresql-mcp-server**          | ❌ Full access | DB-level       | ✅     | DB management        |

### Recommended: crystaldba/postgres-mcp

**Why:**

- Read-only by default (restricted mode)
- Performance analysis tools included
- Simple `DATABASE_URI` configuration
- Python-based (matches your stack)
- MIT license
- Active maintenance

**Installation:**

```bash
# Option 1: pip/pipx
pipx install postgres-mcp

# Option 2: Docker (recommended for deployment)
docker pull crystaldba/postgres-mcp
```

**Run:**

```bash
# Local testing
postgres-mcp "postgresql://mcp_agent:password@localhost:5432/fintech_db"

# Docker
docker run -i --rm \
  -e DATABASE_URI="postgresql://mcp_agent:password@host.docker.internal:5432/fintech_db" \
  crystaldba/postgres-mcp
```

### Alternative: MCP-PostgreSQL-Ops

If you need monitoring/ops tools in addition to queries:

```bash
# Install
pip install mcp-postgresql-ops

# Configure via .env
POSTGRES_HOST=your-host
POSTGRES_PORT=5432
POSTGRES_USER=mcp_agent
POSTGRES_PASSWORD=your-password
POSTGRES_DB=fintech_db

# Run
mcp-postgresql-ops
```

---

## Part 3: Deployment

### Option A: Azure Container Apps (Recommended)

```bash
# 1. Create resource group and environment
az group create --name rg-mcp --location eastus
az containerapp env create --name mcp-env --resource-group rg-mcp

# 2. Deploy MCP server
az containerapp create \
  --name postgres-mcp \
  --resource-group rg-mcp \
  --environment mcp-env \
  --image crystaldba/postgres-mcp:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --secrets db-uri="postgresql://mcp_agent:password@your-postgres:5432/fintech_db" \
  --env-vars DATABASE_URI=secretref:db-uri

# 3. Get endpoint URL
az containerapp show --name postgres-mcp --resource-group rg-mcp --query properties.configuration.ingress.fqdn -o tsv
```

### Option B: Deploy on AKS (Same Cluster as PostgreSQL)

```yaml
# postgres-mcp-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres-mcp
  namespace: analytics
spec:
  replicas: 2
  selector:
    matchLabels:
      app: postgres-mcp
  template:
    metadata:
      labels:
        app: postgres-mcp
    spec:
      containers:
        - name: postgres-mcp
          image: crystaldba/postgres-mcp:latest
          env:
            - name: DATABASE_URI
              valueFrom:
                secretKeyRef:
                  name: postgres-mcp-secrets
                  key: database-uri
          ports:
            - containerPort: 8000
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-mcp
  namespace: analytics
spec:
  selector:
    app: postgres-mcp
  ports:
    - port: 8000
      targetPort: 8000
  type: ClusterIP
---
apiVersion: v1
kind: Secret
metadata:
  name: postgres-mcp-secrets
  namespace: analytics
type: Opaque
stringData:
  database-uri: "postgresql://mcp_agent:password@postgres-service:5432/fintech_db"
```

```bash
kubectl apply -f postgres-mcp-deployment.yaml
```

### Option C: Docker Compose (Local/Dev)

```yaml
# docker-compose.yml
version: "3.8"
services:
  postgres-mcp:
    image: crystaldba/postgres-mcp:latest
    environment:
      DATABASE_URI: "postgresql://mcp_agent:password@host.docker.internal:5432/fintech_db"
    ports:
      - "8000:8000"
    restart: unless-stopped
```

---

## Part 4: Restricting to Specific Views

MCP servers query whatever the PostgreSQL user can access. **Restriction happens at the database level**, not the MCP server.

### Method 1: User Permissions (Recommended)

The read-only user from Part 1 can only SELECT from the 4 analytics views. Any other table query will fail with permission denied.

```sql
-- Verify permissions
SELECT grantee, table_name, privilege_type
FROM information_schema.table_privileges
WHERE grantee = 'mcp_readonly';
```

### Method 2: Schema Isolation

Put analytics views in a separate schema:

```sql
-- Create analytics schema
CREATE SCHEMA analytics;

-- Move views to analytics schema
ALTER VIEW v_daily_active_users SET SCHEMA analytics;
ALTER VIEW v_cards_created SET SCHEMA analytics;
ALTER VIEW v_user_registrations SET SCHEMA analytics;
ALTER VIEW v_transaction_summary SET SCHEMA analytics;

-- Grant access only to analytics schema
REVOKE ALL ON SCHEMA public FROM mcp_readonly;
GRANT USAGE ON SCHEMA analytics TO mcp_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO mcp_readonly;

-- Update search path for MCP user
ALTER ROLE mcp_agent SET search_path = analytics;
```

Connection string now only sees `analytics` schema:

```
postgresql://mcp_agent:password@host:5432/fintech_db?options=-c%20search_path%3Danalytics
```

### Method 3: Row-Level Security (Multi-Tenant)

If you need tenant isolation:

```sql
-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Create policy
CREATE POLICY tenant_filter ON users
  USING (tenant_id = current_setting('app.tenant_id')::uuid);

-- Set tenant context in MCP server or via connection
SET app.tenant_id = 'tenant-uuid-here';
```

---

## Part 5: pg_ai_query Extension Assessment

### What It Is

PostgreSQL extension that adds natural language SQL generation directly inside the database:

```sql
-- Example usage
SELECT generate_query('show me daily active users for last week');
-- Returns: SELECT * FROM v_daily_active_users WHERE day > CURRENT_DATE - 7
```

### Verdict: Not Recommended for Your Case

| Factor                  | pg_ai_query             | MCP Server             |
| ----------------------- | ----------------------- | ---------------------- |
| Azure DB for PostgreSQL | ❌ Not supported        | ✅ Works               |
| Docker/AKS PostgreSQL   | ⚠️ Requires compilation | ✅ Separate container  |
| Multi-database          | ❌ PostgreSQL only      | ✅ Any database        |
| Agent integration       | ❌ SQL function only    | ✅ Native MCP protocol |
| Maintenance             | ⚠️ Early stage (v0.1.0) | ✅ Mature pattern      |
| Azure AI Foundry        | ❌ No integration       | ✅ Native MCP support  |

### When pg_ai_query Makes Sense

- Single PostgreSQL database
- Not using Azure managed PostgreSQL
- Want natural language directly in SQL
- No multi-agent orchestration needed

### Alternative: azure_ai Extension

If using Azure Database for PostgreSQL Flexible Server, Microsoft provides the `azure_ai` extension:

```sql
CREATE EXTENSION azure_ai;
-- Integrates with Azure OpenAI directly
```

But this still doesn't integrate with Azure AI Foundry agents as cleanly as MCP.

---

## Part 6: Connect to Azure AI Foundry

Once MCP server is deployed, register it in Azure AI Foundry:

### Via Portal

1. Azure AI Foundry → Your Project → Agents
2. Create or edit agent
3. Add Tool → MCP
4. Server URL: `https://your-mcp-endpoint.azurecontainerapps.io`
5. Server Label: `analytics-db`

### Via SDK

```python
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

client = AIProjectClient(
    credential=DefaultAzureCredential(),
    project_endpoint="https://your-project.api.azureml.ms"
)

agent = client.agents.create(
    name="analytics-assistant",
    model="gpt-4.1",
    instructions="You help Operations team query analytics data...",
    tools=[{
        "type": "mcp",
        "server_url": "https://your-mcp-endpoint.azurecontainerapps.io",
        "server_label": "analytics-db"
    }]
)
```

---

## Quick Reference

### Connection String Format

```
postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

Examples:

```bash
# Local
postgresql://mcp_agent:password@localhost:5432/fintech_db

# Docker (Mac/Windows)
postgresql://mcp_agent:password@host.docker.internal:5432/fintech_db

# AKS internal service
postgresql://mcp_agent:password@postgres-service.default.svc.cluster.local:5432/fintech_db

# Azure PostgreSQL
postgresql://mcp_agent:password@yourserver.postgres.database.azure.com:5432/fintech_db?sslmode=require
```

### Environment Variables

```bash
# crystaldba/postgres-mcp
DATABASE_URI="postgresql://user:pass@host:5432/db"

# MCP-PostgreSQL-Ops
POSTGRES_HOST=host
POSTGRES_PORT=5432
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=database

# HenkDz/postgresql-mcp-server
POSTGRES_CONNECTION_STRING="postgresql://user:pass@host:5432/db"
```

### Test MCP Server

```bash
# Test connection
curl -X POST https://your-mcp-endpoint/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

---

## Summary

| Step | Action                                                    |
| ---- | --------------------------------------------------------- |
| 1    | Create analytics views in PostgreSQL                      |
| 2    | Create read-only user with access only to views           |
| 3    | Deploy `crystaldba/postgres-mcp` on Container Apps or AKS |
| 4    | Set `DATABASE_URI` to connection string                   |
| 5    | Register MCP endpoint in Azure AI Foundry                 |
| 6    | Test agent queries                                        |

**Total setup time:** ~2-3 hours (not including view design)
