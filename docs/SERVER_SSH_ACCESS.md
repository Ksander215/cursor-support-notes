# SSH Access to Production Server

## Connection Details

```
Host: 85.239.38.163
Port: 22222
User: root
```

## SSH Command

```bash
ssh -p 22222 root@85.239.38.163
```

## SSH Key

Public key stored in `~/.ssh/id_ed25519.pub`:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIO3r7WzvOz1rau1LNPBD9T3C2iBKI8wBMcRd1YMT8+Fa ollama-tunnel
```

Added to server: `~/.ssh/authorized_keys`

## Quick Commands

```bash
# Check n8n status
ssh -p 22222 root@85.239.38.163 "docker ps | grep n8n"

# Check n8n environment
ssh -p 22222 root@85.239.38.163 "docker exec n8n env | grep -i telegram"

# Restart n8n
ssh -p 22222 root@85.239.38.163 "cd /opt/sec-scanner && docker-compose -f docker-compose.n8n.yml restart n8n"

# View n8n logs
ssh -p 22222 root@85.239.38.163 "docker logs n8n --tail 100"

# Check PostgreSQL
ssh -p 22222 root@85.239.38.163 "docker exec n8n-db psql -U n8n -d n8n -c 'SELECT count(*) FROM workflows;'"
```

## Server Location

- VPS: TimeWeb / MSP (Russia)
- Domain: n8n.sec-scanner.pro
- Project path: /opt/sec-scanner

## Services

- n8n: port 5678 (internal), exposed via Nginx on 443
- PostgreSQL: internal port 5432
- Nginx: ports 80, 443

## Last Updated

2026-03-29
