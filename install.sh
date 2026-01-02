#!/bin/bash
# VampGotchi Installation Script
# Automated setup for Raspberry Pi Zero W

# Note: set -e is disabled during dpkg checks to allow error handling
# It will be re-enabled after dpkg state is verified
set +e  # Allow errors during dpkg checks

echo "🧛 VampGotchi Installation Script"
echo "=================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Please run as root (use sudo)${NC}"
    exit 1
fi

# Update system packages
echo -e "${GREEN}[1/8] Updating system packages...${NC}"

# Fix dpkg triggers file if corrupted
echo -e "${YELLOW}  Checking and fixing dpkg state...${NC}"

# #region agent log
LOG_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.cursor/debug.log"
mkdir -p "$(dirname "$LOG_FILE")"
echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"A\",\"location\":\"install.sh:27\",\"message\":\"Starting dpkg state check\",\"data\":{\"triggersFileExists\":$([ -f /var/lib/dpkg/triggers/File ] && echo true || echo false)},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

# Proactively fix the triggers file if it exists (common issue on fresh Pi installations)
if [ -f /var/lib/dpkg/triggers/File ]; then
    # #region agent log
    FILE_SIZE=$(stat -c%s /var/lib/dpkg/triggers/File 2>/dev/null || echo 0)
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"B\",\"location\":\"install.sh:32\",\"message\":\"Triggers file exists\",\"data\":{\"fileSize\":$FILE_SIZE},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Check if file is empty or potentially corrupted (common issue)
    if [ ! -s /var/lib/dpkg/triggers/File ] || [ "$FILE_SIZE" -eq 0 ]; then
        echo -e "${YELLOW}  Empty triggers file detected, fixing...${NC}"
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"C\",\"location\":\"install.sh:38\",\"message\":\"Empty triggers file, recreating\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        rm -f /var/lib/dpkg/triggers/File 2>/dev/null || true
        touch /var/lib/dpkg/triggers/File 2>/dev/null || true
        chmod 644 /var/lib/dpkg/triggers/File 2>/dev/null || true
    else
        # Try to read first line to check if file is readable
        if ! head -n 1 /var/lib/dpkg/triggers/File >/dev/null 2>&1; then
            echo -e "${YELLOW}  Unreadable triggers file detected, fixing...${NC}"
            # #region agent log
            echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"D\",\"location\":\"install.sh:47\",\"message\":\"Unreadable triggers file, recreating\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
            # #endregion agent log
            BACKUP_FILE="/var/lib/dpkg/triggers/File.backup.$(date +%s)"
            cp /var/lib/dpkg/triggers/File "$BACKUP_FILE" 2>/dev/null || true
            rm -f /var/lib/dpkg/triggers/File 2>/dev/null || true
            touch /var/lib/dpkg/triggers/File 2>/dev/null || true
            chmod 644 /var/lib/dpkg/triggers/File 2>/dev/null || true
        fi
    fi
fi

# Try to fix any broken dpkg packages (non-blocking)
echo -e "${YELLOW}  Verifying dpkg packages...${NC}"
dpkg --configure -a 2>/dev/null || true

# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"E\",\"location\":\"install.sh:60\",\"message\":\"dpkg check completed, proceeding to apt-get\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

# Re-enable exit on error for the rest of the script
set -e

apt-get update -qq 2>&1 | tee /tmp/apt_update_error.log || {
    # #region agent log
    EXIT_CODE=$?
    ERROR_MSG=$(cat /tmp/apt_update_error.log 2>/dev/null || echo "Unknown error")
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"D\",\"location\":\"install.sh:73\",\"message\":\"apt-get update failed\",\"data\":{\"exitCode\":$EXIT_CODE,\"error\":\"$ERROR_MSG\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Check if error is related to dpkg triggers file
    if echo "$ERROR_MSG" | grep -qi "syntax error.*triggers.*File" || echo "$ERROR_MSG" | grep -qi "dpkg.*error.*triggers"; then
        echo -e "${YELLOW}  Detected dpkg triggers file error, attempting to fix...${NC}"
        if [ -f /var/lib/dpkg/triggers/File ]; then
            BACKUP_FILE="/var/lib/dpkg/triggers/File.backup.$(date +%s)"
            cp /var/lib/dpkg/triggers/File "$BACKUP_FILE" 2>/dev/null || true
            rm -f /var/lib/dpkg/triggers/File 2>/dev/null || true
            touch /var/lib/dpkg/triggers/File 2>/dev/null || true
            chmod 644 /var/lib/dpkg/triggers/File 2>/dev/null || true
            dpkg --configure -a 2>/dev/null || true
            echo -e "${GREEN}  ✓ Fixed, retrying apt-get update...${NC}"
            apt-get update -qq || exit $?
        else
            echo -e "${RED}  Could not fix dpkg triggers file error${NC}"
            exit $EXIT_CODE
        fi
    else
        exit $EXIT_CODE
    fi
}

# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"E\",\"location\":\"install.sh:26\",\"message\":\"apt-get update succeeded, before upgrade\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

apt-get upgrade -y -qq || {
    # #region agent log
    EXIT_CODE=$?
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"F\",\"location\":\"install.sh:26\",\"message\":\"apt-get upgrade failed\",\"data\":{\"exitCode\":$EXIT_CODE,\"error\":\"apt-get upgrade failed with code $EXIT_CODE\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    exit $EXIT_CODE
}

# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"G\",\"location\":\"install.sh:26\",\"message\":\"apt-get upgrade succeeded\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

# Install system dependencies
echo -e "${GREEN}[2/8] Installing system dependencies...${NC}"
apt-get install -y \
    git \
    python3 \
    python3-pip \
    libbluetooth-dev \
    libboost-python-dev \
    libboost-thread-dev \
    libglib2.0-dev \
    pkg-config \
    bluez \
    bluez-tools \
    hostapd \
    dnsmasq \
    wpa_supplicant \
    > /dev/null 2>&1

# Install Python dependencies
echo -e "${GREEN}[3/8] Installing Python dependencies...${NC}"
pip3 install --break-system-packages -q -r requirements.txt

# Install BLEeding
BLEEDING_PATH="/root/BLEeding"
if [ ! -d "$BLEEDING_PATH" ]; then
    echo -e "${GREEN}[4/8] Installing BLEeding...${NC}"
    cd /root
    git clone https://github.com/sammwyy/BLEeding.git > /dev/null 2>&1
    cd BLEeding
    pip3 install --break-system-packages -q -r requirements.txt
    cd - > /dev/null
else
    echo -e "${YELLOW}[4/8] BLEeding already installed, skipping...${NC}"
fi

# Verify BLEeding installation
echo -e "${GREEN}[5/8] Verifying BLEeding installation...${NC}"
if [ -f "$BLEEDING_PATH/bleeding.py" ]; then
    echo -e "${GREEN}✓ BLEeding found${NC}"
else
    echo -e "${RED}✗ BLEeding not found at $BLEEDING_PATH${NC}"
    exit 1
fi

# Create configuration file if it doesn't exist
echo -e "${GREEN}[6/8] Setting up configuration...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [ ! -f "config.yml" ] && [ -f "default_config.yml" ]; then
    cp "default_config.yml" "config.yml"
    echo -e "${GREEN}✓ Configuration file created${NC}"
else
    echo -e "${YELLOW}Configuration file already exists or default_config.yml not found${NC}"
fi
cd - > /dev/null

# Set up Bluetooth
echo -e "${GREEN}[7/8] Configuring Bluetooth...${NC}"
systemctl enable bluetooth > /dev/null 2>&1
systemctl start bluetooth > /dev/null 2>&1
hciconfig hci0 up 2>/dev/null || true
echo -e "${GREEN}✓ Bluetooth configured${NC}"

# Install systemd service (optional)
echo -e "${GREEN}[8/8] Setting up systemd service...${NC}"
if [ -f "$SCRIPT_DIR/vampgotchi.service" ]; then
    SERVICE_FILE="/etc/systemd/system/vampgotchi.service"
    cp "$SCRIPT_DIR/vampgotchi.service" "$SERVICE_FILE"
    systemctl daemon-reload > /dev/null 2>&1
    echo -e "${GREEN}✓ Systemd service installed${NC}"
    echo -e "${YELLOW}  To enable auto-start: sudo systemctl enable vampgotchi${NC}"
    echo -e "${YELLOW}  To start service: sudo systemctl start vampgotchi${NC}"
else
    echo -e "${YELLOW}Systemd service file not found, skipping...${NC}"
fi

# Final verification
echo ""
echo -e "${GREEN}=================================="
echo -e "Installation completed successfully!${NC}"
echo ""
echo "Next steps:"
echo "1. Run: sudo python3 vampgotchi.py"
echo "2. Or enable service: sudo systemctl enable --now vampgotchi"
echo "3. Access web interface at http://<device-ip>"
echo ""
echo -e "${GREEN}Happy hacking! 🧛🦇${NC}"

