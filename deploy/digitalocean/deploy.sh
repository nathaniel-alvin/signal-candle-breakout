#!/bin/bash
# DigitalOcean Droplet Deployment Script for Signal Candle Jengat
# Run this on your DigitalOcean droplet after initial setup

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="signal-candle-jengat"
APP_USER="signalbot"
APP_DIR="/opt/${APP_NAME}"
REPO_URL="https://github.com/yourusername/signal-candle-jengat.git"  # UPDATE THIS
BRANCH="main"

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   log_error "This script must be run as root (use sudo)"
   exit 1
fi

log_info "Starting deployment of ${APP_NAME}..."

# 1. Create application user
if ! id "${APP_USER}" &>/dev/null; then
    log_info "Creating user ${APP_USER}..."
    useradd -r -m -s /bin/bash "${APP_USER}"
else
    log_info "User ${APP_USER} already exists"
fi

# 2. Install Docker if not present
if ! command -v docker &>/dev/null; then
    log_info "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker "${APP_USER}"
else
    log_info "Docker already installed"
fi

# 3. Install Docker Compose if not present
if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null; then
    log_info "Installing Docker Compose..."
    apt-get update && apt-get install -y docker-compose-plugin
else
    log_info "Docker Compose already available"
fi

# 4. Create application directory
log_info "Setting up application directory at ${APP_DIR}..."
mkdir -p "${APP_DIR}"
mkdir -p "${APP_DIR}/data"
mkdir -p "${APP_DIR}/logs"
mkdir -p "${APP_DIR}/config"

# 5. Clone or update repository
if [[ -d "${APP_DIR}/.git" ]]; then
    log_info "Repository exists, pulling latest changes..."
    cd "${APP_DIR}"
    sudo -u "${APP_USER}" git fetch origin
    sudo -u "${APP_USER}" git reset --hard "origin/${BRANCH}"
else
    log_info "Cloning repository..."
    sudo -u "${APP_USER}" git clone -b "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

# 6. Copy environment file template
if [[ ! -f "${APP_DIR}/.env" ]]; then
    log_warn "Creating .env from template - YOU MUST EDIT THIS WITH YOUR CREDENTIALS!"
    sudo -u "${APP_USER}" cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
fi

# 7. Copy config file
if [[ ! -f "${APP_DIR}/config/settings.yaml" ]]; then
    log_info "Copying config file..."
    sudo -u "${APP_USER}" cp "${APP_DIR}/config/settings.yaml" "${APP_DIR}/config/settings.yaml"
fi

# 8. Set permissions
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 750 "${APP_DIR}/data"
chmod 750 "${APP_DIR}/logs"

# 9. Build Docker image
log_info "Building Docker image..."
cd "${APP_DIR}"
sudo -u "${APP_USER}" docker build -t "${APP_NAME}:latest" .

# 10. Stop existing container if running
log_info "Stopping any existing container..."
sudo -u "${APP_USER}" docker stop "${APP_NAME}" 2>/dev/null || true
sudo -u "${APP_USER}" docker rm "${APP_NAME}" 2>/dev/null || true

# 11. Run new container
log_info "Starting new container..."
sudo -u "${APP_USER}" docker run -d \
    --name "${APP_NAME}" \
    --restart unless-stopped \
    --env-file "${APP_DIR}/.env" \
    -v "${APP_DIR}/data:/app/data" \
    -v "${APP_DIR}/logs:/app/logs" \
    -v "${APP_DIR}/config:/app/config:ro" \
    "${APP_NAME}:latest"

# 12. Verify container is running
sleep 3
if sudo -u "${APP_USER}" docker ps --filter "name=${APP_NAME}" --filter "status=running" | grep -q "${APP_NAME}"; then
    log_info "✅ Deployment successful! Container is running."
    log_info "Check logs with: sudo -u ${APP_USER} docker logs -f ${APP_NAME}"
else
    log_error "❌ Container failed to start. Check logs:"
    sudo -u "${APP_USER}" docker logs "${APP_NAME}"
    exit 1
fi

log_info "Deployment complete!"
echo ""
echo "Next steps:"
echo "  1. Edit ${APP_DIR}/.env with your Telegram/Discord credentials"
echo "  2. Restart container: sudo -u ${APP_USER} docker restart ${APP_NAME}"
echo "  3. View logs: sudo -u ${APP_USER} docker logs -f ${APP_NAME}"
echo "  4. Check status: sudo -u ${APP_USER} docker ps"