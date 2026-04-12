# Deployment Documentation

## Purpose
This document explains how to deploy and run the Syntx Memory MCP Server in local development, staging, and production environments. It covers prerequisites, installation steps, run commands, and upgrade notes.

## Overview
The server is a Python package that can be installed and run in various environments. It requires Ollama for embeddings and a Ladybug database for storage. Deployment supports local development, containerized staging, and production setups.

## Prerequisites
### System Requirements
- Python 3.14+
- At least 4GB RAM (8GB recommended)
- 10GB disk space for database and embeddings

### Dependencies
- Ollama service running locally or remotely
- Required Ollama models: nomic-embed-text, llama3.2 (for summarization)

### Network Requirements
- Outbound internet access for Ollama model downloads (initial setup)
- Port 9100 available for HTTP/SSE (configurable)

## Local Development Setup
### Installation
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd syntx-memory-mcp
   ```

2. Install dependencies:
   ```bash
   pip install -e .
   ```

3. Start Ollama service:
   ```bash
   ollama serve
   ```

4. Pull required models:
   ```bash
   ollama pull nomic-embed-text
   ollama pull llama3.2
   ```

### Configuration
Create a `.env` file in the project root:
```bash
MCP_HOST=127.0.0.1
MCP_PORT=9100
MCP_TRANSPORT=http
LADYBUG_DB_PATH=./data/syntx_memory.lbug
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_EMBED_DIM=1536
```

### Running the Server
Start the server:
```bash
python -m syntx_mcp.server
```

The server will be available at `http://127.0.0.1:9100`

To run the audit agent (example):
In another terminal:
```bash
# The agent is invoked via MCP tools, not directly
# Use an MCP client to call audit_package
```

### Testing
Run the test suite:
```bash
pytest
```

## Staging Deployment
### Docker Setup
Create a `Dockerfile`:
```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY src/ src/
EXPOSE 9100
CMD ["python", "-m", "syntx_mcp.server"]
```

Build and run:
```bash
docker build -t syntx-memory .
docker run -p 9100:9100 -v ./data:/data -e OLLAMA_EMBED_DIM=1536 syntx-memory
```

### Docker Compose
Create `docker-compose.yml`:
```yaml
version: '3.8'
services:
  syntx-memory:
    build: .
    ports:
      - "9100:9100"
    volumes:
      - ./data:/data
    environment:
      - MCP_HOST=0.0.0.0
      - LADYBUG_DB_PATH=/data/memory.lbug
      - OLLAMA_EMBED_DIM=1536
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
volumes:
  ollama-data:
```

Run:
```bash
docker-compose up -d
```

## Production Deployment
### Systemd Service
Create `/etc/systemd/system/syntx-memory.service`:
```ini
[Unit]
Description=Syntx Memory MCP Server
After=network.target
[Service]
User=syntx
Group=syntx
WorkingDirectory=/opt/syntx-memory
Environment=PATH=/opt/syntx-memory/venv/bin
ExecStart=/opt/syntx-memory/venv/bin/python -m syntx_mcp.server
Restart=always
[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable syntx-memory
sudo systemctl start syntx-memory
```

### Nginx Reverse Proxy
Configure Nginx for production:
```nginx
server {
    listen 80;
    server_name memory.example.com;
    location / {
        proxy_pass http://127.0.0.1:9100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Database Backup
Regular backups of the Ladybug database:
```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d)
cp /var/lib/syntx/memory.lbug /var/backups/syntx-memory-$DATE.lbug
```

## Upgrade Notes
### Version Upgrades
1. Stop the server:
   ```bash
   sudo systemctl stop syntx-memory
   ```

2. Backup database:
   ```bash
   cp /var/lib/syntx/memory.lbug /var/backups/pre-upgrade.lbug
   ```

3. Update code:
   ```bash
   cd /opt/syntx-memory
   git pull
   pip install -e . --upgrade
   ```

4. Check for configuration changes in release notes

5. Update Ollama models if required:
   ```bash
   ollama pull nomic-embed-text:latest
   ```

6. Start the server:
   ```bash
   sudo systemctl start syntx-memory
   ```

### Breaking Changes
- v0.2.0: Embedding dimension changed to 1536, update `OLLAMA_EMBED_DIM`
- v0.1.5: Database schema migration required, backup before upgrade

## Troubleshooting
### Common Issues
**Server won't start:**
- Check Ollama is running: `ollama list`
- Verify port 9100 is available: `netstat -tlnp | grep 9100`
- Check logs: `journalctl -u syntx-memory`

**Embedding failures:**
- Pull latest models: `ollama pull nomic-embed-text`
- Check model compatibility

**Database errors:**
- Ensure write permissions on database directory
- Check disk space

## Monitoring
### Health Checks
Basic health check endpoint (if implemented):
```bash
curl http://localhost:9100/health
```

### Logs
Monitor systemd logs:
```bash
journalctl -u syntx-memory -f
```

### Metrics
No built-in metrics, consider integrating with Prometheus for production monitoring.

## References to Code
- Server startup: `src/syntx_mcp/server.py`
- Database initialization: `src/syntx_mcp/db.py`
- Configuration loading: `src/syntx_mcp/server.py:41-45`
