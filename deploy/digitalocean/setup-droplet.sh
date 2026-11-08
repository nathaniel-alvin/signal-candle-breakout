#!/bin/bash
# DigitalOcean Droplet Initial Setup Script
# Run this ONCE on a fresh Ubuntu droplet as root
# This prepares the server for the signal-candle-jengat deployment

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

if [[ $EUID -ne 0 ]]; then
   log_error "This script must be run as root (use sudo)"
   exit 1
fi

log_info "=== DigitalOcean Droplet Initial Setup ==="

# 1. Update system
log_info "Updating system packages..."
apt-get update && apt-get upgrade -y

# 2. Install essential packages
log_info "Installing essential packages..."
apt-get install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    ufw \
    fail2ban \
    logrotate \
    ca-certificates \
    gnupg \
    lsb-release

# 3. Configure timezone
log_info "Setting timezone to UTC..."
timedatectl set-timezone UTC

# 4. Configure UFW firewall
log_info "Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 22/tcp
# Uncomment if you need web access for monitoring
# ufw allow 80/tcp
# ufw allow 443/tcp
ufw --force enable

# 5. Configure fail2ban for SSH protection
log_info "Configuring fail2ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
backend = systemd

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
EOF

systemctl enable fail2ban
systemctl restart fail2ban

# 6. Create application user
APP_USER="signalbot"
if ! id "${APP_USER}" &>/dev/null; then
    log_info "Creating user ${APP_USER}..."
    useradd -r -m -s /bin/bash "${APP_USER}"
else
    log_info "User ${APP_USER} already exists"
fi

# 7. Install Docker
log_info "Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker "${APP_USER}"
    log_info "Docker installed successfully"
else
    log_info "Docker already installed"
fi

# 8. Install Docker Compose
log_info "Installing Docker Compose..."
if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null; then
    apt-get install -y docker-compose-plugin
    log_info "Docker Compose installed"
else
    log_info "Docker Compose already available"
fi

# 9. Configure logrotate for application logs
log_info "Setting up logrotate..."
cat > /etc/logrotate.d/signal-candle-jengat << 'EOF'
/opt/signal-candle-jengat/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 640 signalbot signalbot
    sharedscripts
    postrotate
        /usr/bin/docker kill --signal=USR1 signal-candle-jengat > /dev/null 2>&1 || true
    endscript
}
EOF

# 10. Create directory structure
log_info "Creating application directories..."
mkdir -p /opt/signal-candle-jengat/{data,logs,config}
chown -R "${APP_USER}:${APP_USER}" /opt/signal-candle-jengat
chmod 750 /opt/signal-candle-jengat/data
chmod 750 /opt/signal-candle-jengat/logs

# 11. Setup swap (recommended for small droplets)
log_info "Checking swap configuration..."
if ! swapon --show | grep -q '^/swapfile'; then
    log_info "Creating 1GB swap file..."
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    log_info "Swap created and enabled"
else
    log_info "Swap already configured"
fi

# 12. Configure sysctl for better performance
log_info "Applying sysctl optimizations..."
cat > /etc/sysctl.d/99-signal-bot.conf << 'EOF'
# Reduce swap usage
vm.swappiness = 10
vm.vfs_cache_pressure = 50

# Network optimizations
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
EOF
sysctl --system

# 13. Enable automatic security updates
log_info "Enabling automatic security updates..."
apt-get install -y unattended-upgrades
cat > /etc/apt/apt.conf.d/50unattended-upgrades << 'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
EOF

log_info "=== Setup Complete! ==="
echo ""
echo "Next steps:"
echo "  1. Copy your repository to /opt/signal-candle-jengat"
echo "  2. Copy deploy/digitalocean/.env.template to /opt/signal-candle-jengat/.env"
echo "  3. Edit /opt/signal-candle-jengat/.env with your credentials"
echo "  4. Run deploy/digitalocean/deploy.sh to deploy the application"
echo ""
echo "Useful commands:"
echo "  Check firewall: ufw status"
echo "  Check fail2ban: fail2ban-client status sshd"
echo "  Check docker: docker ps"
echo "  View logs: journalctl -u signal-candle-jengat -f"