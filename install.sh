#!/bin/bash
# VampGotchi Installation Script
# Automated setup for Raspberry Pi Zero W

set -e  # Exit on error

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

# Setup debug logging
LOG_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.cursor/debug.log"
mkdir -p "$(dirname "$LOG_FILE")"

# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"A\",\"location\":\"install.sh:30\",\"message\":\"Starting dpkg state check\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

# Simple, direct approach to fix dpkg corruption
echo -e "${YELLOW}  Checking and fixing dpkg state...${NC}"

# Step 1: Fix triggers file (always recreate if exists)
if [ -f /var/lib/dpkg/triggers/File ]; then
    echo -e "${YELLOW}  Fixing dpkg triggers file...${NC}"
    # Backup and recreate
    cp /var/lib/dpkg/triggers/File /var/lib/dpkg/triggers/File.backup.$(date +%s) 2>/dev/null || true
    rm -f /var/lib/dpkg/triggers/File
    touch /var/lib/dpkg/triggers/File
    chmod 644 /var/lib/dpkg/triggers/File
    echo -e "${GREEN}  ✓ Triggers file recreated${NC}"
    # #region agent log
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"B\",\"location\":\"install.sh:40\",\"message\":\"Triggers file fixed\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
fi

# Step 2: Recreate status file (always do this to be safe)
echo -e "${YELLOW}  Recreating dpkg status file...${NC}"
if [ -f /var/lib/dpkg/status ]; then
    # Backup current status
    cp /var/lib/dpkg/status /var/lib/dpkg/status.backup.$(date +%s) 2>/dev/null || true
    rm -f /var/lib/dpkg/status
fi
# Remove old backup to avoid conflicts
rm -f /var/lib/dpkg/status-old 2>/dev/null || true

# Get architecture and create fresh status file
ARCH=$(dpkg --print-architecture 2>/dev/null || echo armhf)
cat > /var/lib/dpkg/status << STATUS_EOF
Package: dpkg
Status: install ok installed
Priority: required
Section: admin
Architecture: $ARCH
Version: 1.21.22
Description: Debian package management system

STATUS_EOF
chmod 644 /var/lib/dpkg/status
echo -e "${GREEN}  ✓ Status file recreated${NC}"
# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"C\",\"location\":\"install.sh:65\",\"message\":\"Status file recreated\",\"data\":{\"arch\":\"$ARCH\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

# Step 3: Remove all package list files that might be corrupted
echo -e "${YELLOW}  Removing potentially corrupted package list files...${NC}"
find /var/lib/dpkg/info -name "*.list" -type f 2>/dev/null | while read LIST_FILE; do
    if [ -f "$LIST_FILE" ]; then
        echo -e "${YELLOW}  Removing: $(basename "$LIST_FILE")${NC}"
        rm -f "$LIST_FILE" 2>/dev/null || true
    fi
done 2>/dev/null || true
echo -e "${GREEN}  ✓ Package list files removed${NC}"
# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"D\",\"location\":\"install.sh:85\",\"message\":\"Package list files cleaned\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

# Step 4: Configure dpkg
echo -e "${YELLOW}  Attempting to configure dpkg...${NC}"
dpkg --configure -a 2>&1 | tee /tmp/dpkg_configure.log || {
    EXIT_CODE=$?
    ERROR_MSG=$(cat /tmp/dpkg_configure.log 2>/dev/null || echo "Unknown error")
    # #region agent log
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"E\",\"location\":\"install.sh:92\",\"message\":\"dpkg configure failed\",\"data\":{\"exitCode\":$EXIT_CODE,\"errorPreview\":\"$(echo "$ERROR_MSG" | head -c 200)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Check for specific error: files list file contains empty filename
    if echo "$ERROR_MSG" | grep -qiE "files list file.*contains empty filename|unrecoverable fatal error"; then
        echo -e "${YELLOW}  Detected corrupted package files, attempting fix...${NC}"
        # Extract package name
        PACKAGE_NAME=$(echo "$ERROR_MSG" | grep -oE "package '[^']+'" | sed "s/package '//; s/'//" | head -n 1)
        
        if [ -n "$PACKAGE_NAME" ]; then
            echo -e "${YELLOW}  Removing corrupted package files for: $PACKAGE_NAME${NC}"
            # Extract base package name
            BASE_PACKAGE=$(echo "$PACKAGE_NAME" | cut -d: -f1)
            
            # Remove all files for this package
            rm -f /var/lib/dpkg/info/${PACKAGE_NAME}.* 2>/dev/null || true
            rm -f /var/lib/dpkg/info/${BASE_PACKAGE}.* 2>/dev/null || true
            
            # Remove from status file
            awk -v pkg="$PACKAGE_NAME" -v base="$BASE_PACKAGE" '
                /^Package: / {
                    pkg_name = $2
                    in_pkg = (pkg_name == pkg || pkg_name == base)
                }
                !in_pkg {print}
                /^$/ && in_pkg {in_pkg = 0}
            ' /var/lib/dpkg/status > /var/lib/dpkg/status.tmp 2>/dev/null && mv /var/lib/dpkg/status.tmp /var/lib/dpkg/status || true
            
            echo -e "${GREEN}  ✓ Removed corrupted package files${NC}"
            
            # Try to configure again
            dpkg --configure -a 2>/dev/null || true
        fi
    fi
}
echo -e "${GREEN}  ✓ dpkg configured${NC}"
# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"F\",\"location\":\"install.sh:120\",\"message\":\"dpkg check completed\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

# Now proceed with apt-get update
apt-get update -qq 2>&1 | tee /tmp/apt_update_error.log || {
    # #region agent log
    EXIT_CODE=$?
    ERROR_MSG=$(cat /tmp/apt_update_error.log 2>/dev/null || echo "Unknown error")
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"G\",\"location\":\"install.sh:125\",\"message\":\"apt-get update failed\",\"data\":{\"exitCode\":$EXIT_CODE,\"errorPreview\":\"$(echo "$ERROR_MSG" | head -c 200)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Check if error is related to dpkg status
    if echo "$ERROR_MSG" | grep -qiE "Problem with MergeList.*status|Encountered a section with no Package"; then
        echo -e "${YELLOW}  Status file still corrupted, recreating...${NC}"
        # Recreate status file
        ARCH=$(dpkg --print-architecture 2>/dev/null || echo armhf)
        cat > /var/lib/dpkg/status << STATUS_EOF
Package: dpkg
Status: install ok installed
Priority: required
Section: admin
Architecture: $ARCH
Version: 1.21.22
Description: Debian package management system

STATUS_EOF
        chmod 644 /var/lib/dpkg/status
        
        # Retry apt-get update
        apt-get update -qq || {
            RETRY_EXIT=$?
            RETRY_ERROR=$(cat /tmp/apt_update_error2.log 2>/dev/null || echo "Unknown error")
            echo -e "${RED}  apt-get update still failing${NC}"
            exit $RETRY_EXIT
        }
    else
        exit $EXIT_CODE
    fi
}
# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"H\",\"location\":\"install.sh:150\",\"message\":\"apt-get update succeeded\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

apt-get upgrade -y -qq || {
    # #region agent log
    EXIT_CODE=$?
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"I\",\"location\":\"install.sh:153\",\"message\":\"apt-get upgrade failed\",\"data\":{\"exitCode\":$EXIT_CODE,\"error\":\"apt-get upgrade failed with code $EXIT_CODE\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    exit $EXIT_CODE
}
# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"J\",\"location\":\"install.sh:160\",\"message\":\"apt-get upgrade succeeded\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
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

# Verify Scrpit.py exists
echo -e "${GREEN}[6/8] Verifying installation...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [ ! -f "Scrpit.py" ]; then
    echo -e "${RED}Error: Scrpit.py not found in $SCRIPT_DIR${NC}"
    exit 1
else
    chmod +x Scrpit.py
    echo -e "${GREEN}✓ Scrpit.py verified and made executable${NC}"
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
# Try both possible names (vampigotchi.service and vampgotchi.service)
if [ -f "$SCRIPT_DIR/vampigotchi.service" ]; then
    SERVICE_SOURCE="$SCRIPT_DIR/vampigotchi.service"
elif [ -f "$SCRIPT_DIR/vampgotchi.service" ]; then
    SERVICE_SOURCE="$SCRIPT_DIR/vampgotchi.service"
else
    SERVICE_SOURCE=""
fi

if [ -n "$SERVICE_SOURCE" ]; then
    SERVICE_FILE="/etc/systemd/system/vampigotchi.service"
    # Update service file with correct paths before copying
    sed "s|/path/to/Scrpit.py|$SCRIPT_DIR/Scrpit.py|g; s|/path/to/VAMPIGOTCHI|$SCRIPT_DIR|g; s|vampgotchi\.py|Scrpit.py|g; s|vampigotchi\.py|Scrpit.py|g" "$SERVICE_SOURCE" > "$SERVICE_FILE" 2>/dev/null || cp "$SERVICE_SOURCE" "$SERVICE_FILE"
    systemctl daemon-reload > /dev/null 2>&1
    echo -e "${GREEN}✓ Systemd service installed${NC}"
    echo -e "${YELLOW}  To enable auto-start: sudo systemctl enable vampigotchi${NC}"
    echo -e "${YELLOW}  To start service: sudo systemctl start vampigotchi${NC}"
else
    echo -e "${YELLOW}Systemd service file not found, skipping...${NC}"
fi

# Update service file to use Scrpit.py
if [ -n "$SERVICE_SOURCE" ]; then
    echo -e "${YELLOW}  Updating service file to use Scrpit.py...${NC}"
    sed -i "s|vampigotchi\.py|Scrpit.py|g; s|vampgotchi\.py|Scrpit.py|g" "$SERVICE_FILE" 2>/dev/null || true
    systemctl daemon-reload > /dev/null 2>&1
fi

# Final verification
echo ""
echo -e "${GREEN}=================================="
echo -e "Installation completed successfully!${NC}"
echo ""
echo "Next steps:"
echo "1. Run: sudo python3 Scrpit.py"
echo "2. Or enable service: sudo systemctl enable --now vampigotchi"
echo "3. Access web interface at http://<device-ip>"
echo ""
echo -e "${GREEN}Happy hacking! 🧛🦇${NC}"
