# Postgres MCP Pro - DevOps Guide

This document covers local development setup, deployment options, and operational requirements for Postgres MCP Pro.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Deployment Options](#deployment-options)
4. [PostgreSQL Configuration](#postgresql-configuration)
5. [Environment Variables](#environment-variables)
6. [MCP Client Configuration](#mcp-client-configuration)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required

| Component      | Version            | Why Needed                                                                                         |
| -------------- | ------------------ | -------------------------------------------------------------------------------------------------- |
| **Python**     | 3.12+              | Runtime. Uses modern async features, type hints, and `match` statements. Lower versions will fail. |
| **PostgreSQL** | 13+ (15-17 tested) | Target database. MCP server analyzes and optimizes PostgreSQL databases.                           |
| **uv**         | 0.6.9+             | Package manager. Faster than pip, handles lockfiles, runs commands in venv automatically.          |

### Optional

| Component                        | Why Needed                                                                                                                  |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Docker**                       | Containerized deployment. Eliminates Python environment issues.                                                             |
| **pg_stat_statements extension** | Required for `get_top_queries` and `analyze_workload_indexes` tools. Without it, these tools return errors.                 |
| **hypopg extension**             | Required for index tuning simulation. Without it, `analyze_*_indexes` and `explain_query` hypothetical features won't work. |
| **OpenAI API Key**               | Only for experimental "LLM-based index optimization" feature. NOT needed for MCP connection or standard index tuning.       |

---

## Local Development Setup

### 1. Install uv (Package Manager)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify installation
uv --version
```

**Why uv?** It's 10-100x faster than pip, manages Python versions, and the project uses `uv.lock` for reproducible builds.

### 2. Clone and Install Dependencies

```bash
git clone https://github.com/crystaldba/postgres-mcp.git
cd postgres-mcp

# Install all dependencies (including dev)
uv sync

# This creates .venv/ and installs everything from uv.lock
```

### 3. Set Up PostgreSQL (Local)

**Option A: Docker (Recommended for development)**

```bash
# PostgreSQL with required extensions pre-installed
docker run -d \
  --name postgres-mcp-dev \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=devdb \
  -p 5432:5432 \
  postgres:17

# Connect and create extensions
docker exec -it postgres-mcp-dev psql -U postgres -d devdb -c "
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS hypopg;
"
```

**Option B: Existing PostgreSQL**

```sql
-- Run as superuser or user with CREATE EXTENSION privilege
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS hypopg;

-- Verify
SELECT extname FROM pg_extension WHERE extname IN ('pg_stat_statements', 'hypopg');
```

**Note on pg_stat_statements:** On self-managed PostgreSQL, you must add it to `shared_preload_libraries` in `postgresql.conf` and restart:

```
shared_preload_libraries = 'pg_stat_statements'
```

### 4. Run the Server Locally

```bash
# Set database connection
export DATABASE_URI="postgresql://postgres:postgres@localhost:5432/devdb"

# Run with stdio transport (for MCP clients like Claude Desktop)
uv run postgres-mcp --access-mode=unrestricted

# Run with SSE transport (for shared server / web clients)
uv run postgres-mcp --transport=sse --sse-host=0.0.0.0 --sse-port=8000
```

### 5. Run Tests

```bash
# Build test database with extensions
docker build -f tests/Dockerfile.postgres-hypopg -t test-postgres-hypopg .
docker run -d --name test-pg -p 5433:5432 -e POSTGRES_PASSWORD=postgres test-postgres-hypopg

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/sql/test_safe_sql.py -v

# Run with logging
uv run pytest --log-cli-level=INFO

# Cleanup
docker rm -f test-pg
```

### 6. Code Quality Checks

```bash
# Lint (checks for errors, style issues)
uv run ruff check .

# Format check (does not modify files)
uv run ruff format --check .

# Auto-fix lint issues
uv run ruff check --fix .

# Auto-format
uv run ruff format .

# Type checking
uv run pyright
```

---

## Deployment Options

### Option 1: Docker (Recommended for Production)

**Why Docker?**

- Eliminates Python version/dependency conflicts
- Consistent behavior across environments
- Auto-handles localhost remapping for database connections
- Multi-arch support (amd64, arm64)

**Build Image**

```bash
docker build -t postgres-mcp:latest .
```

**Run with stdio Transport (MCP Client Integration)**

```bash
docker run -it --rm \
  -e DATABASE_URI="postgresql://user:password@host:5432/dbname" \
  postgres-mcp:latest \
  --access-mode=restricted
```

**Run with SSE Transport (Shared Server)**

```bash
docker run -d \
  --name postgres-mcp-server \
  --restart unless-stopped \
  -p 8000:8000 \
  -e DATABASE_URI="postgresql://user:password@host:5432/dbname" \
  postgres-mcp:latest \
  --transport=sse \
  --access-mode=restricted
```

**Docker Compose Example**

```yaml
# docker-compose.yml
version: "3.8"

services:
  postgres-mcp:
    image: crystaldba/postgres-mcp:latest
    # Or build locally:
    # build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URI: "postgresql://user:password@db-host:5432/dbname"
      # OPENAI_API_KEY: "sk-..."  # Only if using LLM optimization
    command: ["--transport=sse", "--access-mode=restricted"]
    restart: unless-stopped
    # For local PostgreSQL on host machine:
    # extra_hosts:
    #   - "host.docker.internal:host-gateway"
```

### Option 2: Direct Python (pipx or uv)

**Why Direct Python?**

- Lower overhead (no container)
- Simpler for single-user local development
- Direct access to logs and debugging

**Install via pipx (Isolated Environment)**

```bash
pipx install postgres-mcp

# Run
DATABASE_URI="postgresql://user:pass@localhost:5432/db" postgres-mcp --access-mode=unrestricted
```

**Install via uv (Project-based)**

```bash
uv pip install postgres-mcp

# Or run without installing
uvx postgres-mcp --help
```

### Option 3: From Source

```bash
git clone https://github.com/crystaldba/postgres-mcp.git
cd postgres-mcp
uv sync
uv run postgres-mcp "postgresql://user:pass@localhost:5432/db"
```

---

## PostgreSQL Configuration

### Extension Requirements by Feature

| Feature                                              | pg_stat_statements | hypopg      |
| ---------------------------------------------------- | ------------------ | ----------- |
| `list_schemas`, `list_objects`, `get_object_details` | ❌                 | ❌          |
| `execute_sql`                                        | ❌                 | ❌          |
| `analyze_db_health`                                  | ❌                 | ❌          |
| `get_top_queries`                                    | ✅ Required        | ❌          |
| `analyze_workload_indexes`                           | ✅ Required        | ✅ Required |
| `analyze_query_indexes`                              | ❌                 | ✅ Required |
| `explain_query` (with hypothetical indexes)          | ❌                 | ✅ Required |

### Installing Extensions

**AWS RDS / Azure Database / Google Cloud SQL:**
Extensions are available, just create them:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS hypopg;
```

**Self-managed PostgreSQL:**

1. Edit `postgresql.conf`:

   ```
   shared_preload_libraries = 'pg_stat_statements'
   ```

2. Restart PostgreSQL

3. Create extensions:
   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
   CREATE EXTENSION IF NOT EXISTS hypopg;
   ```

**Verify Installation:**

```sql
SELECT extname, extversion FROM pg_extension
WHERE extname IN ('pg_stat_statements', 'hypopg');
```

### Connection String Format

```
postgresql://[user]:[password]@[host]:[port]/[database]?[options]
```

**Examples:**

```bash
# Local
postgresql://postgres:mypassword@localhost:5432/mydb

# With SSL
postgresql://user:pass@db.example.com:5432/prod?sslmode=require

# AWS RDS
postgresql://admin:secret@mydb.abc123.us-east-1.rds.amazonaws.com:5432/appdb

# Connection pooler (PgBouncer)
postgresql://user:pass@pgbouncer:6432/mydb?application_name=postgres-mcp
```

---

## Environment Variables

| Variable         | Required | Description                                                                            |
| ---------------- | -------- | -------------------------------------------------------------------------------------- |
| `DATABASE_URI`   | Yes\*    | PostgreSQL connection string. Can also be passed as CLI argument.                      |
| `OPENAI_API_KEY` | No       | Only for experimental LLM-based index optimization. Not needed for standard operation. |

\*Required unless passed as command-line argument.

---

## MCP Client Configuration

### Claude Desktop

**Config Location:**

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%/Claude/claude_desktop_config.json`

**Docker Configuration:**

```json
{
  "mcpServers": {
    "postgres": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "DATABASE_URI",
        "crystaldba/postgres-mcp",
        "--access-mode=unrestricted"
      ],
      "env": {
        "DATABASE_URI": "postgresql://user:password@localhost:5432/dbname"
      }
    }
  }
}
```

**Direct Python (uv) Configuration:**

```json
{
  "mcpServers": {
    "postgres": {
      "command": "uv",
      "args": ["run", "postgres-mcp", "--access-mode=unrestricted"],
      "env": {
        "DATABASE_URI": "postgresql://user:password@localhost:5432/dbname"
      }
    }
  }
}
```

### Cursor / Windsurf (SSE Transport)

For SSE transport, first start the server:

```bash
docker run -d -p 8000:8000 \
  -e DATABASE_URI="postgresql://..." \
  crystaldba/postgres-mcp \
  --transport=sse --access-mode=restricted
```

Then configure the client:

**Cursor (`mcp.json`):**

```json
{
  "mcpServers": {
    "postgres": {
      "type": "sse",
      "url": "http://localhost:8000/sse"
    }
  }
}
```

**Windsurf (`mcp_config.json`):**

```json
{
  "mcpServers": {
    "postgres": {
      "type": "sse",
      "serverUrl": "http://localhost:8000/sse"
    }
  }
}
```

---

## Access Modes

| Mode           | Use Case                        | Behavior                                                                                                  |
| -------------- | ------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `unrestricted` | Development, testing            | Full read/write. LLM can execute any SQL including DDL, DML.                                              |
| `restricted`   | Production, shared environments | Read-only transactions enforced. SQL parsed to reject COMMIT/ROLLBACK escape attempts. 30s query timeout. |

**Security Notes:**

- **Restricted mode** parses SQL using `pglast` before execution
- Read-only is enforced at transaction level (`SET TRANSACTION READ ONLY`)
- Cannot be bypassed from within the transaction
- Always use `restricted` mode for production databases

---

## Troubleshooting

### Connection Issues

**Error: "Cannot connect to database"**

```bash
# Test connection directly
psql "postgresql://user:pass@host:5432/db"

# Check if PostgreSQL is running
pg_isready -h localhost -p 5432
```

**Docker: Cannot reach localhost database**

The Docker entrypoint auto-remaps `localhost`:

- macOS/Windows → `host.docker.internal`
- Linux → `172.17.0.1`

If still failing, explicitly use host IP:

```bash
# Get host IP (Linux)
ip route | grep docker0 | awk '{print $9}'

# Use in connection string
DATABASE_URI="postgresql://user:pass@172.17.0.1:5432/db"
```

### Extension Issues

**Error: "pg_stat_statements not found"**

```sql
-- Check if extension exists
SELECT * FROM pg_available_extensions WHERE name = 'pg_stat_statements';

-- If available but not created
CREATE EXTENSION pg_stat_statements;

-- If not available, check shared_preload_libraries
SHOW shared_preload_libraries;
```

**Error: "hypopg not found"**

```bash
# On Debian/Ubuntu
sudo apt-get install postgresql-17-hypopg

# On macOS with Homebrew
brew install hypopg
```

### Windows-Specific Issues

**Event Loop Error:**

The server automatically handles this in `__init__.py`:

```python
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

If you see `ProactorEventLoop` errors, ensure you're using the package entry point (`postgres-mcp`) not running `server.py` directly.

### Performance Issues

**Slow index analysis:**

- The Anytime Algorithm searches many combinations
- Default time budget is configurable in `analyze_workload_indexes`
- For faster results, use `analyze_query_indexes` with specific queries instead of workload analysis

**Connection pool exhaustion:**

- Default pool size is reasonable for single-client use
- For SSE transport with multiple clients, consider increasing pool size in `sql_driver.py`

---

## Health Checks

For container orchestration (Kubernetes, Docker Swarm), the SSE transport exposes an HTTP endpoint:

```bash
# Check if server is responding
curl http://localhost:8000/sse

# Should return SSE stream headers
```

For stdio transport, health is implicit - if the process is running and accepting stdin, it's healthy.

---

## Logs

Logs go to stderr with Python's logging module (Serilog-style format):

```bash
# Docker: View logs
docker logs postgres-mcp-server

# Increase verbosity
uv run postgres-mcp --access-mode=unrestricted 2>&1 | tee mcp.log
```

Log levels are controlled via Python logging config. For debugging, modify `server.py`:

```python
logging.basicConfig(level=logging.DEBUG)
```
