# Security Documentation

## Purpose
This document outlines the security considerations for the Syntx Memory MCP Server, including authentication/authorization mechanisms, secrets handling, secure defaults, rotation policies, and auditing capabilities.

## Overview
The server currently implements minimal security measures, assuming deployment in a trusted environment. All components are designed to run locally with no external access. Security is primarily handled at the infrastructure level rather than application level.

## Authentication and Authorization
### Current Implementation
**No Authentication:**
- The server does not implement user authentication
- All MCP clients have full access to all tools and data
- No session management or access control

**No Authorization:**
- No role-based access control (RBAC)
- No project-level permissions
- No tool-specific access restrictions

### Recommended Security Measures
**API Key Authentication:**
- Implement API key validation in `server.py`
- Store hashed keys in database
- Validate keys on each request

**Session-Based Access:**
- Use session tokens for tool activation
- Implement session timeout
- Track active sessions

**Project Scoping:**
- Add project membership checks
- Implement project-level access control
- Use database queries with user/project filters

### Code-Level Hints
```python
# src/syntx_mcp/server.py - Add authentication middleware
async def authenticate_request(request):
    api_key = request.headers.get('X-API-Key')
    if not api_key or not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return get_user_from_key(api_key)
```

## Secrets Handling
### Configuration Secrets
**Environment Variables:**
- Database paths and credentials stored in environment
- No encryption of configuration values
- `.env` files contain sensitive paths

**Ollama Credentials:**
- No authentication to Ollama service
- Assumes local trusted Ollama instance
- No secure communication with Ollama

### Secure Storage
**Database Encryption:**
- Ladybug database stored in plaintext
- No encryption at rest
- File system permissions control access

**Backup Security:**
- Database backups contain all data
- No encryption of backup files
- Secure backup storage required

### Secrets Rotation
**Configuration Updates:**
- No automated rotation mechanism
- Manual update of environment variables
- Server restart required for changes

**Ollama Access:**
- No credentials to rotate
- Model updates require manual intervention

## Secure Defaults
### Server Configuration
**Default Bindings:**
- Binds to `127.0.0.1:9100` by default
- Prevents external access without configuration
- Requires explicit `0.0.0.0` for external binding

**Transport Security:**
- HTTP only, no HTTPS
- No TLS/SSL termination
- Assumes reverse proxy for encryption

### Database Security
**File Permissions:**
- Database file created with default permissions
- Requires manual permission setting
- No automatic secure defaults

**Connection Handling:**
- Single database connection
- No connection pooling
- No connection encryption

### Tool Security
**Input Validation:**
- Basic parameter validation via Pydantic
- No SQL injection protection (graph queries)
- Limited input sanitization

**Error Handling:**
- Detailed error messages may leak information
- Stack traces potentially exposed
- No error message sanitization

## Rotation Policies
### Database Credentials
**Current State:**
- No database credentials (embedded DB)
- File-based access control

**Future Implementation:**
- Implement credential rotation for external DB
- Automated key rotation scripts
- Zero-downtime rotation procedures

### API Keys
**Planned Rotation:**
- 90-day rotation cycle
- Automated notification system
- Graceful key deactivation

### Backup Encryption
**Encryption Keys:**
- Rotate backup encryption keys quarterly
- Secure key storage (HSM recommended)
- Audit key access

## Auditing
### Current Auditing
**No Built-in Auditing:**
- No request logging
- No access audit trails
- No data modification tracking

**External Auditing:**
- Rely on system logs
- Ollama service logs
- File system access logs

### Recommended Auditing
**Request Auditing:**
- Log all MCP tool calls
- Track client IP and user agent
- Record request/response metadata

**Data Auditing:**
- Audit database changes
- Track memory modifications
- Log decision and violation changes

**Code-Level Auditing:**
```python
# src/syntx_mcp/server.py - Add audit logging
async def audit_tool_call(tool_name, params, result, user_id):
    audit_entry = {
        'timestamp': datetime.utcnow(),
        'user_id': user_id,
        'tool_name': tool_name,
        'action': 'tool_call',
        'params': sanitize_params(params),
        'result': 'success' if 'error' not in result else 'error'
    }
    await log_audit_entry(audit_entry)
```

### Audit Storage
**Audit Logs:**
- Store audit logs in separate database
- Implement log rotation
- Secure log file permissions

**Retention Policies:**
- 7-year retention for security events
- 1-year retention for access logs
- Automated archival and deletion

## Security Considerations by Component
### Server Component
**Network Security:**
- Bind to localhost by default
- No rate limiting implemented
- Vulnerable to DoS attacks

**Code Security:**
- Input validation gaps
- Error information disclosure
- No authentication layer

### Tools Component
**Data Exposure:**
- Tools return detailed error messages
- No data filtering based on permissions
- Full database access per tool

**Injection Risks:**
- Cypher query injection possible
- Limited input sanitization
- Trust in client-provided parameters

### Agent Component
**Execution Security:**
- Agents can execute arbitrary code
- No sandboxing of agent operations
- File system access via tools

**Data Access:**
- Agents have full tool access
- No agent-specific restrictions
- Potential for data exfiltration

### Database Security
**Access Control:**
- No database-level authentication
- File-based access control only
- No query-level permissions

**Data Protection:**
- No encryption at rest
- Plaintext data storage
- No data masking

## Infrastructure Security
### Deployment Security
**Container Security:**
- Run as non-root user
- Minimal base images
- No privileged containers

**Network Security:**
- Use internal networks
- Implement network policies
- Firewall configuration

### Monitoring and Alerting
**Security Monitoring:**
- Monitor for anomalous access patterns
- Alert on failed authentication attempts
- Track tool usage metrics

**Incident Response:**
- Log analysis procedures
- Data breach response plan
- System hardening checklists

## Compliance Considerations
### Data Protection
**PII Handling:**
- May store conversation data with PII
- No PII detection or masking
- Retention policies needed

**Data Residency:**
- Data stored locally
- No cloud storage options
- Geographic data location control

### Regulatory Compliance
**GDPR/CCPA:**
- Data subject access requests
- Right to erasure implementation
- Consent management

**Industry Standards:**
- SOC 2 Type II compliance
- ISO 27001 certification
- Security audit requirements

## References to Code
- Server initialization: `src/syntx_mcp/server.py`
- Database access: `src/syntx_mcp/db.py`
- Tool implementations: `src/syntx_mcp/tools/*.py`
- Agent execution: `src/syntx_mcp/agents/audit_agent.py`
