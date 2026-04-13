# Runbook Documentation

## Purpose
This document provides operational runbook for the Syntx Memory MCP Server, including common workflows, incident response steps, and triage checks for outages or degraded behavior.

## Overview
The runbook covers routine operations, troubleshooting procedures, and emergency response for the MCP server. It assumes deployment in a production environment with systemd service management and monitoring.

## Routine Operations
### Server Startup
**Normal Startup:**
1. Verify Ollama service is running:
   ```bash
   systemctl status ollama
   ollama list
   ```

2. Start MCP server:
   ```bash
   sudo systemctl start syntx-memory
   ```

3. Verify server is responding:
   ```bash
   curl -s http://localhost:9100 | head -20
   ```

4. Check logs for successful startup:
   ```bash
   journalctl -u syntx-memory -n 20
   ```

**Startup Checklist:**
- [ ] Ollama models loaded
- [ ] Database file accessible
- [ ] Port 9100 available
- [ ] No error messages in logs

### Server Shutdown
**Graceful Shutdown:**
1. Stop accepting new connections
2. Complete in-flight requests
3. Close database connections
4. Shutdown cleanly

**Command:**
```bash
sudo systemctl stop syntx-memory
```

### Service Monitoring
**Status Checks:**
```bash
# Service status
systemctl status syntx-memory
# Process check
ps aux | grep mem-graph
# Port check
netstat -tlnp | grep 9100
# Log monitoring
journalctl -u syntx-memory -f
```

**Health Metrics:**
- CPU usage < 50%
- Memory usage < 2GB
- Disk I/O reasonable
- Response time < 5s

## Common Workflows
### Database Maintenance
**Daily Backup:**
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/var/backups/syntx
DB_PATH=/var/lib/syntx/memory.lbug
cp $DB_PATH $BACKUP_DIR/memory-$DATE.lbug
find $BACKUP_DIR -name "memory-*.lbug" -mtime +30 -delete
```

**Database Optimization:**
```bash
# Check database size
ls -lh /var/lib/syntx/memory.lbug
# Vacuum if needed (Ladybug specific)
# Monitor index performance
```

### Log Management
**Log Rotation:**
```bash
# Systemd handles log rotation
journalctl --vacuum-time=30d
```

**Log Analysis:**
```bash
# Recent errors
journalctl -u syntx-memory | grep -i error | tail -10
# Tool call patterns
journalctl -u syntx-memory | grep "tool_call" | awk '{print $1, $2}' | uniq -c | tail -5
```

### Configuration Updates
**Environment Changes:**
1. Edit `.env` file or environment
2. Validate configuration
3. Restart service:
   ```bash
   sudo systemctl restart syntx-memory
   ```
4. Verify functionality

### Software Updates
**Update Process:**
1. Create backup
2. Download new version
3. Install dependencies
4. Test in staging
5. Deploy to production
6. Monitor for issues

## Incident Response
### Severity Levels
**SEV1 - Critical:**
- Server completely down
- Data corruption
- Security breach

**SEV2 - High:**
- Degraded performance
- Partial functionality loss
- Data inconsistency

**SEV3 - Medium:**
- Intermittent issues
- Performance degradation
- Warning messages

**SEV4 - Low:**
- Monitoring alerts
- Non-critical errors

### Response Procedures
#### Server Down (SEV1)
**Immediate Actions:**
1. Confirm outage:
   ```bash
   curl -f http://localhost:9100
   ```

2. Check service status:
   ```bash
   systemctl status syntx-memory
   ```

3. Review recent logs:
   ```bash
   journalctl -u syntx-memory --since "1 hour ago" | tail -50
   ```

4. Attempt restart:
   ```bash
   sudo systemctl restart syntx-memory
   ```

5. If restart fails, check dependencies:
   - Ollama service
   - Database file permissions
   - Disk space

6. Restore from backup if data corruption suspected

7. Notify stakeholders

**Post-Incident:**
- Root cause analysis
- Preventative measures
- Documentation updates

#### Performance Degradation (SEV2)
**Symptoms:**
- Slow response times
- High CPU/memory usage
- Tool call timeouts

**Diagnosis:**
1. Check system resources:
   ```bash
   top -p $(pgrep -f mem-graph)
   free -h
   df -h
   ```

2. Monitor database performance:
   ```bash
   # Check active connections
   lsof /var/lib/syntx/memory.lbug | wc -l
   ```

3. Review recent activity:
   ```bash
   journalctl -u syntx-memory --since "30 min ago"
   ```

4. Check Ollama performance:
   ```bash
   ollama ps
   ```

**Resolution:**
- Scale resources if needed
- Optimize queries
- Clear caches if applicable
- Restart service

#### Data Inconsistency (SEV2)
**Symptoms:**
- Incorrect search results
- Missing relationships
- Tool errors

**Diagnosis:**
1. Validate database integrity:
   ```bash
   # Ladybug integrity check (if available)
   ```

2. Check recent transactions:
   ```bash
   # Review logs for failed operations
   journalctl -u syntx-memory | grep "ERROR"
   ```

3. Test basic operations

**Resolution:**
- Restore from backup
- Rebuild indexes
- Recalculate embeddings

### Communication
**Internal Communication:**
- Use incident tracking system
- Update status page
- Notify on-call team

**External Communication:**
- Client impact assessment
- Estimated resolution time
- Workaround instructions

## Triage Checks
### Quick Health Check
```bash
#!/bin/bash
# Service status
if ! systemctl is-active --quiet syntx-memory; then
    echo "CRITICAL: Service not running"
    exit 2
fi
# Port availability
if ! nc -z localhost 9100; then
    echo "CRITICAL: Port not responding"
    exit 2
fi
# Database access
if [ ! -f /var/lib/syntx/memory.lbug ]; then
    echo "CRITICAL: Database file missing"
    exit 2
fi
# Disk space
DISK_USAGE=$(df /var/lib/syntx | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 90 ]; then
    echo "WARNING: Low disk space"
    exit 1
fi
# Memory usage
MEM_USAGE=$(ps aux --no-headers -o pmem -C python | awk '{sum+=$1} END {print sum}')
if (( $(echo "$MEM_USAGE > 80" | bc -l) )); then
    echo "WARNING: High memory usage"
    exit 1
fi
echo "OK: All checks passed"
exit 0
```

### Detailed Diagnostics
**Log Analysis:**
```bash
# Error patterns
journalctl -u syntx-memory --since "1 day ago" | grep -i error | tail -10
# Performance metrics
journalctl -u syntx-memory | grep "tool_call" | awk '{print $1, $2}' | uniq -c | tail -5
```

**Database Diagnostics:**
```bash
# Connection count
lsof /var/lib/syntx/memory.lbug | wc -l
# File size monitoring
ls -lh /var/lib/syntx/memory.lbug
```

**Network Diagnostics:**
```bash
# Connection states
netstat -t | grep 9100
# Request rate
journalctl -u syntx-memory --since "1 hour ago" | grep "tool_call" | wc -l
```

## Recovery Procedures
### Database Recovery
**From Backup:**
1. Stop server
2. Move corrupted database
3. Restore from backup
4. Verify integrity
5. Start server

**Partial Recovery:**
- Identify corrupted data
- Export good data
- Reimport after cleanup

### Service Recovery
**Forced Restart:**
```bash
sudo systemctl stop syntx-memory
sudo killall -9 python  # if needed
sudo systemctl start syntx-memory
```

**Clean Restart:**
- Clear temporary files
- Reset caches
- Verify configuration

### Data Recovery
**Embedding Recalculation:**
```python
# Script to recalculate embeddings
import asyncio
from mem-graph.db import get_conn
from mem-graph.embeddings import embed
async def recalculate_embeddings():
    conn = await get_conn()
    # Query nodes needing embedding recalculation
    # Update embeddings
    pass
```

## Maintenance Windows
### Scheduled Maintenance
**Weekly Tasks:**
- Log rotation
- Backup verification
- Index optimization

**Monthly Tasks:**
- Security updates
- Performance analysis
- Capacity planning

### Emergency Maintenance
**Unscheduled Downtime:**
- Schedule during low-usage periods
- Communicate with stakeholders
- Minimize downtime duration

## Monitoring and Alerting
### Monitoring Setup
**System Monitoring:**
- CPU, memory, disk usage
- Network I/O
- Process status

**Application Monitoring:**
- Tool call success rate
- Response time percentiles
- Error rate

**Business Monitoring:**
- Active projects
- Conversation volume
- Memory growth rate

### Alert Configuration
**Critical Alerts:**
- Service down
- Database corruption
- Security incidents

**Warning Alerts:**
- High resource usage
- Increased error rates
- Performance degradation

**Info Alerts:**
- Successful deployments
- Backup completions
- Maintenance windows

## Escalation Procedures
### Support Tiers
**Tier 1 - Operations:**
- Basic troubleshooting
- Service restarts
- Log analysis

**Tier 2 - Development:**
- Code-level issues
- Configuration problems
- Performance optimization

**Tier 3 - Architecture:**
- Design issues
- Scaling problems
- Security incidents

### Escalation Triggers
- Issue unresolved > 30 minutes
- Multiple system impact
- Data loss potential
- Security concern

## References to Code
- Server startup: `src/mem-graph/server.py`
- Service management: `/etc/systemd/system/syntx-memory.service`
- Monitoring scripts: `/opt/syntx-memory/monitoring/`
- Backup scripts: `/opt/syntx-memory/backup/`
