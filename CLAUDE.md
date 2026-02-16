# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Postgres MCP Pro** is an open-source Model Context Protocol (MCP) server for PostgreSQL database analysis, tuning, and optimization. It provides AI agents with tools for index tuning (using Microsoft's Anytime Algorithm), query plan analysis, database health checks, and safe SQL execution.

**Key Technical Choices:**

- Industrial-strength index tuning via greedy search with `hypopg` simulation
- Deterministic health checks (adapted from PgHero) vs LLM-generated analysis
- Read-only enforcement via SQL parsing (pglast) in restricted mode
- Async throughout using psycopg3 with libpq

## Development Commands

```bash
# Install dependencies
uv sync

# Run server locally (requires DATABASE_URI env var)
DATABASE_URI="postgresql://user:pass@localhost:5432/db" uv run postgres-mcp

# Run with SSE transport (shared server mode)
uv run postgres-mcp --transport=sse --sse-host=0.0.0.0 --sse-port=8000

# Lint and format
uv run ruff check .
uv run ruff format --check .

# Type checking
uv run pyright

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/test_access_mode.py -v

# Run with verbose logging
uv run pytest --log-cli-level=INFO

# Build package
uv build
```

## CLI Arguments

```
postgres-mcp [database_url]
  --access-mode {unrestricted,restricted}  # Default: unrestricted
  --transport {stdio,sse}                  # Default: stdio
  --sse-host <host>                        # Default: localhost
  --sse-port <port>                        # Default: 8000
```

**Environment Variables:**

- `DATABASE_URI`: PostgreSQL connection string (required, or pass as CLI arg)
- `OPENAI_API_KEY`: Required for LLM-based index optimization feature

## Architecture

```
src/postgres_mcp/
├── __init__.py           # Entry point (handles Windows event loop)
├── server.py             # FastMCP server, tool definitions, CLI parsing
├── sql/
│   ├── sql_driver.py     # DbConnPool, SqlDriver, obfuscate_password()
│   ├── safe_sql.py       # SafeSqlDriver (restricted mode enforcement)
│   ├── bind_params.py    # SQL parameter binding from table statistics
│   └── extension_utils.py
├── index/
│   ├── dta_calc.py       # DatabaseTuningAdvisor (Anytime Algorithm)
│   ├── llm_opt.py        # LLM-based optimization (experimental)
│   └── index_opt_base.py # IndexRecommendation dataclass
├── database_health/
│   └── database_health.py  # Orchestrates health check modules
├── explain/
│   └── explain_plan.py   # EXPLAIN ANALYZE with hypothetical indexes
└── top_queries/
    └── top_queries_calc.py  # pg_stat_statements analysis
```

**Key Patterns:**

- All tools use `@mcp.tool()` decorator in `server.py`
- Database operations go through `SqlDriver` (unrestricted) or `SafeSqlDriver` (restricted)
- SafeSqlDriver parses SQL with pglast to reject COMMIT/ROLLBACK, enforces read-only transactions, and applies 30s timeout
- Password obfuscation via `obfuscate_password()` in all error messages/logs

## MCP Tools Exposed

| Tool                       | Purpose                                           |
| -------------------------- | ------------------------------------------------- |
| `list_schemas`             | List database schemas                             |
| `list_objects`             | List tables, views, sequences, extensions         |
| `get_object_details`       | Column, constraint, index details                 |
| `execute_sql`              | Run SQL (read-only in restricted mode)            |
| `explain_query`            | EXPLAIN ANALYZE with hypothetical indexes         |
| `get_top_queries`          | Slow queries via pg_stat_statements               |
| `analyze_workload_indexes` | Index recommendations from workload               |
| `analyze_query_indexes`    | Index recommendations for specific queries        |
| `analyze_db_health`        | Health checks: index, vacuum, buffer, connections |

## Docker Deployment

```bash
# Build
docker build -t postgres-mcp:latest .

# Run stdio transport
docker run -it --rm \
  -e DATABASE_URI="postgresql://user:pass@host:port/db" \
  postgres-mcp:latest --access-mode=unrestricted

# Run SSE transport
docker run -d -p 8000:8000 \
  -e DATABASE_URI="postgresql://user:pass@host:port/db" \
  postgres-mcp:latest --transport=sse --access-mode=unrestricted
```

**Docker entrypoint features:**

- Auto-remaps `localhost` → `host.docker.internal` (macOS/Windows) or `172.17.0.1` (Linux)
- Auto-adds `--sse-host=0.0.0.0` when SSE transport detected

## PostgreSQL Extensions (Optional but Recommended)

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- Query performance tracking
CREATE EXTENSION IF NOT EXISTS hypopg;              -- Hypothetical index simulation
```

Required for index tuning and top queries features.

## Testing

**Test Database with Extensions:**

```bash
docker build -f tests/Dockerfile.postgres-hypopg -t test-postgres-hypopg .
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres test-postgres-hypopg
```

**Test Structure:**

- `tests/unit/` - Isolated component tests
- `tests/integration/` - End-to-end with real PostgreSQL
- `tests/conftest.py` - Shared fixtures

## Release Process

```bash
# 1. Update version in pyproject.toml
# 2. Sync lockfile
uv sync
# 3. Commit and push to main
# 4. Create release (via justfile)
just release 0.3.1 "Release notes here"
# Or pre-release
just prerelease 0.3.1 1 "RC notes"
```

## Key Dependencies

- `mcp[cli]>=1.5.0` - MCP server framework (FastMCP)
- `psycopg[binary]>=3.2.6` - PostgreSQL async driver
- `pglast==7.2.0` - SQL parsing for restricted mode (exact version pinned)
- `instructor>=1.7.9` - LLM structured outputs for index optimization
- `hypopg` extension - Hypothetical index cost estimation
