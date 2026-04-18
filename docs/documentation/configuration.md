# Configuration Documentation

## Purpose
This document explains the configuration surface of the Syntx Memory MCP Server, including environment variables, configuration files, default values, and override mechanisms. It covers how to customize server behavior, database settings, and external service integrations.

## Overview
The server uses environment variables loaded from `.env` files or system environment for all configuration. No configuration files are currently supported. Configuration is loaded once at startup and cannot be changed at runtime without restart.

## Environment Variables

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_HOST` | `127.0.0.1` | Server bind address for HTTP/SSE transports |
| `MCP_PORT` | `9100` | Server port for HTTP/SSE transports |
| `MCP_TRANSPORT` | `http` | Transport protocol: `http`, `stdio`, or other FastMCP transports |

**Example:**
```bash
export MCP_HOST=0.0.0.0
export MCP_PORT=8080
export MCP_TRANSPORT=http
```

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LADYBUG_DB_PATH` | `./data/syntx_memory.lbug` | Path to Ladybug database file |

**Example:**
```bash
export LADYBUG_DB_PATH=/var/data/syntx_memory.lbug
```

### Embeddings and Ollama Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_CODE_EMBED_MODEL` | `hf.co/jinaai/jina-embeddings-v4-text-code-GGUF:Q5_K_M` | Code-oriented embedding model used for code files and Jina code-linking |
| `OLLAMA_TEXT_EMBED_MODEL` | `hf.co/nomic-ai/nomic-embed-text-v1.5-GGUF:F16` | Text-oriented embedding model used for memory, tasks, decisions, and notes |
| `OLLAMA_EMBED_DIM` | `768` | Embedding vector dimensions used by the schema bootstrap and validation checks |
| `MEM_GRAPH_EMBED_CACHE_SIZE` | `512` | In-process LRU cache size for generated embeddings |

**Example:**
```bash
export OLLAMA_CODE_EMBED_MODEL=hf.co/jinaai/jina-embeddings-v4-text-code-GGUF:Q5_K_M
export OLLAMA_TEXT_EMBED_MODEL=hf.co/nomic-ai/nomic-embed-text-v1.5-GGUF:F16
export OLLAMA_EMBED_DIM=768
```

### Jina Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `JINA_URL` | _unset_ | Base Jina URL, for example `https://jina.example.com` |
| `JINA_USERNAME` | _unset_ | Optional Jina username or email for Basic auth |
| `JINA_TOKEN` | _unset_ | Jina API token or bearer token |
| `JINA_PROJECT_KEY` | _unset_ | Default project key used when no JQL is provided |
| `JINA_MATCH_THRESHOLD` | `0.72` | Default semantic score threshold for Jina-to-code matching |
| `JINA_MAX_RESULTS` | `25` | Maximum number of issues returned by Jina read tools |
| `JINA_EMBEDDER_TTL_SECONDS` | `300` | Idle timeout before the in-process code index is released |

The Jina tools are read-only. If these values are not configured, the server still starts normally and the Jina tools return a configuration error only when called.

### File Explorer

| Variable | Default | Description |
|----------|---------|-------------|
| `MEM_GRAPH_FILE_TREE_ROOT` | current working directory | Default root path for the `/file-tree` explorer when no project repo path or explicit root is provided |

## Configuration Loading

### Environment Variable Loading
Configuration is loaded using `python-dotenv` with the following priority:
1. System environment variables
2. `.env` file in current working directory
3. `.env` file in project root

**Code Reference:**
```python
# src/mem-graph/server.py
from dotenv import load_dotenv
load_dotenv()
```

### Validation and Defaults
Configuration values are validated and defaulted in the server startup code:

```python
# src/mem-graph/server.py:41-45
_HOST = os.getenv("MCP_HOST", "127.0.0.1")
_PORT = int(os.getenv("MCP_PORT", "9100"))
```

## Configuration Files

### .env File Format
The server supports `.env` files with standard key=value syntax:

```bash
# Server settings
MCP_HOST=127.0.0.1
MCP_PORT=9100
MCP_TRANSPORT=http

# Database settings
LADYBUG_DB_PATH=./data/syntx_memory.lbug

# Ollama settings
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_EMBED_DIM=1536
```

### Example .env Configuration
```bash
# Production configuration
MCP_HOST=0.0.0.0
MCP_PORT=8080
MCP_TRANSPORT=http
LADYBUG_DB_PATH=/opt/syntx/data/memory.lbug
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_EMBED_DIM=1536
```

## Override Mechanisms

### Runtime Environment Variables
Variables can be overridden at runtime using shell environment:

```bash
# Override port for testing
MCP_PORT=9090 python -m mem-graph.server
```

### Docker Environment
When running in Docker, use environment variables in docker-compose.yml:

```yaml
services:
  syntx-memory:
    image: syntx-memory:latest
    environment:
      - MCP_HOST=0.0.0.0
      - MCP_PORT=9100
      - LADYBUG_DB_PATH=/data/memory.lbug
      - OLLAMA_EMBED_DIM=1536
    volumes:
      - ./data:/data
```

### Development vs Production
Different configurations for different environments:

**Development (.env.dev):**
```bash
MCP_HOST=127.0.0.1
MCP_PORT=9100
LADYBUG_DB_PATH=./dev_data/memory.lbug
OLLAMA_EMBED_DIM=768
```

**Production (.env.prod):**
```bash
MCP_HOST=0.0.0.0
MCP_PORT=8080
LADYBUG_DB_PATH=/var/lib/syntx/memory.lbug
OLLAMA_EMBED_DIM=1536
```

## Configuration Validation

### Startup Validation
The server performs validation during initialization:

1. **Ollama Availability**: Checks if Ollama service is running and pulls required models
2. **Database Path**: Ensures database directory is writable
3. **Embedding Dimensions**: Validates against schema requirements (should be 1536)

**Code Reference:**
```python
# src/mem-graph/db.py:init_db()
await _probe_ollama()
```

### Runtime Validation
No runtime configuration changes are supported. All configuration is static after startup.

## Security Considerations

### Sensitive Configuration
Currently, no sensitive configuration is handled. All variables are non-sensitive:
- Server binding addresses
- Database file paths
- Model names and dimensions

### File Permissions
Ensure proper permissions on configuration files:

```bash
# Secure .env file permissions
chmod 600 .env
```

### Database Security
Database files should be stored with appropriate permissions:

```bash
# Database directory permissions
mkdir -p /var/lib/syntx
chown syntx:syntx /var/lib/syntx
chmod 700 /var/lib/syntx
```

## Troubleshooting Configuration

### Common Issues

**Port Already in Use:**
```
Error: [Errno 48] Address already in use
```
**Solution:** Change `MCP_PORT` or stop conflicting service

**Database Permission Denied:**
```
PermissionError: [Errno 13] Permission denied
```
**Solution:** Ensure database directory is writable by server process

**Ollama Not Available:**
```
RuntimeError: Ollama service not available
```
**Solution:** Start Ollama service or check `OLLAMA_HOST` if configured

**Embedding Dimension Mismatch:**
```
ValueError: Embedding dimension mismatch
```
**Solution:** Set `OLLAMA_EMBED_DIM=1536` to match schema

### Debugging Configuration
Enable debug logging by setting environment variables:

```bash
export PYTHONPATH=src
python -c "import os; print('MCP_HOST:', os.getenv('MCP_HOST', 'not set'))"
```

## Migration and Updates

### Configuration Changes
When upgrading, check for new configuration variables in release notes.

### Backward Compatibility
Configuration is backward compatible. New variables use sensible defaults.

## References to Code
- Configuration loading: `src/mem-graph/server.py:41-45`
- Database initialization: `src/mem-graph/db.py:init_db()`
- Environment variable usage: Throughout `src/mem-graph/server.py`