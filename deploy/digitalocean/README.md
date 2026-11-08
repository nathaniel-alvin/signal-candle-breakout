# DigitalOcean Deployment Guide

This guide covers deploying Signal Candle Jengat to a DigitalOcean Droplet.

## Quick Start

### 1. Create Droplet
- **OS**: Ubuntu 22.04 LTS (or 24.04 LTS)
- **Size**: Basic $6/mo (1 vCPU, 1GB RAM) minimum recommended
- **Region**: Choose closest to you
- **Authentication**: SSH Key (recommended) or Password

### 2. Initial Server Setup
SSH into your droplet as root and run:

```bash
# Download and run setup script
curl -fsSL https://raw.githubusercontent.com/yourusername/signal-candle-jengat/main/deploy/digitalocean/setup-droplet.sh | bash
```

Or manually copy and run:
```bash
scp deploy/digitalocean/setup-droplet.sh root@your-droplet-ip:/tmp/
ssh root@your-droplet-ip "bash /tmp/setup-droplet.sh"
```

### 3. Deploy Application

**Option A: Using the deploy script (recommended)**
```bash
# On your local machine
scp -r deploy/digitalocean root@your-droplet-ip:/tmp/
ssh root@your-droplet-ip "bash /tmp/digitalocean/deploy.sh"
```

**Option B: Using Docker Compose**
```bash
# On the droplet
cd /opt/signal-candle-jengat
docker compose -f /path/to/docker-compose.yml up -d
```

**Option C: Using systemd service**
```bash
# Copy service file
cp deploy/digitalocean/signal-candle-jengat.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable signal-candle-jengat
systemctl start signal-candle-jengat
```

### 4. Configure Credentials
```bash
# On the droplet
cp /opt/signal-candle-jengat/.env.template /opt/signal-candle-jengat/.env
chmod 600 /opt/signal-candle-jengat/.env
vim /opt/signal-candle-jengat/.env  # Add your Telegram/Discord credentials

# Restart to apply
docker restart signal-candle-jengat
# or: systemctl restart signal-candle-jengat
```

## Detailed Steps

### Prerequisites
- DigitalOcean account
- Domain name (optional, for monitoring)
- Telegram Bot Token (from @BotFather)
- Telegram Chat ID (from @userinfobot)
- Discord Webhook URL (optional)

### Configuration Files

| File | Purpose | Required |
|------|---------|----------|
| `.env` | Secrets (tokens, webhooks) | Yes |
| `config/settings.yaml` | Bot configuration | Yes |
| `docker-compose.yml` | Container orchestration | Optional |
| `signal-candle-jengat.service` | Systemd service | Optional |

### Directory Structure on Droplet
```
/opt/signal-candle-jengat/
├── .env                    # Secrets (chmod 600)
├── config/
│   └── settings.yaml       # Bot config
├── data/                   # Persistent state (bot_state.json)
├── logs/                   # Application logs
└── deploy/                 # Deployment scripts
```

### Managing the Bot

**View logs:**
```bash
# Docker
docker logs -f signal-candle-jengat

# Systemd
journalctl -u signal-candle-jengat -f
```

**Restart:**
```bash
# Docker
docker restart signal-candle-jengat

# Systemd
systemctl restart signal-candle-jengat
```

**Update application:**
```bash
cd /opt/signal-candle-jengat
git pull origin main
docker build -t signal-candle-jengat:latest .
docker restart signal-candle-jengat
```

**Check status:**
```bash
docker ps
# or
systemctl status signal-candle-jengat
```

### Monitoring

**Health check:**
```bash
# Check if container is running
docker ps --filter name=signal-candle-jengat

# Check resource usage
docker stats signal-candle-jengat --no-stream
```

**Log rotation** is configured automatically via `/etc/logrotate.d/signal-candle-jengat`

### Security Notes

1. **Firewall**: Only SSH (port 22) is open by default
2. **Fail2ban**: Protects SSH from brute force
3. **Non-root user**: App runs as `signalbot` user
4. **Secrets**: `.env` file permissions set to 600
5. **Swap**: 1GB swap file created for memory safety

### Troubleshooting

**Container won't start:**
```bash
docker logs signal-candle-jengat
```

**Permission denied on data/logs:**
```bash
chown -R signalbot:signalbot /opt/signal-candle-jengat/data /opt/signal-candle-jengat/logs
chmod 750 /opt/signal-candle-jengat/data /opt/signal-candle-jengat/logs
```

**Out of memory:**
```bash
# Check memory usage
free -h

# Increase swap if needed
swapoff /swapfile
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
```

**Bot not sending signals:**
1. Check logs for errors
2. Verify `.env` has correct credentials
3. Test notifications: `docker exec signal-candle-jengat python main.py --test-notifications`
4. Run once: `docker exec signal-candle-jengat python main.py --once`

### Cost Optimization

For a $6/mo droplet (1GB RAM):
- Set memory limit to 512M in docker-compose.yml
- Use 1GB swap
- Monitor with `docker stats`

### Backup Strategy

**State file backup:**
```bash
# Backup bot state
cp /opt/signal-candle-jengat/data/bot_state.json ~/bot_state_backup_$(date +%Y%m%d).json
```

**Full backup script:**
```bash
#!/bin/bash
BACKUP_DIR=~/backups/$(date +%Y%m%d)
mkdir -p $BACKUP_DIR
cp /opt/signal-candle-jengat/data/bot_state.json $BACKUP_DIR/
cp /opt/signal-candle-jengat/.env $BACKUP_DIR/
cp -r /opt/signal-candle-jengat/config $BACKUP_DIR/
tar -czf ~/backups/signal-bot-$(date +%Y%m%d).tar.gz -C /opt signal-candle-jengat
# Keep last 7 days
find ~/backups -name "signal-bot-*.tar.gz" -mtime +7 -delete
```

## Support

- Check logs first: `docker logs -f signal-candle-jengat`
- Verify configuration: `docker exec signal-candle-jengat python main.py --once`
- Test notifications: `docker exec signal-candle-jengat python main.py --test-notifications`