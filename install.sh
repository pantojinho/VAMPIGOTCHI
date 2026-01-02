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

# Step 1: Fix triggers file
if [ -f /var/lib/dpkg/triggers/File ]; then
    echo -e "${YELLOW}  Fixing dpkg triggers file...${NC}"
    # Backup and recreate
    cp /var/lib/dpkg/triggers/File /var/lib/dpkg/triggers/File.backup.$(date +%s) 2>/dev/null || true
    rm -f /var/lib/dpkg/triggers/File
    touch /var/lib/dpkg/triggers/File
    chmod 644 /var/lib/dpkg/triggers/File
    echo -e "${GREEN}  ✓ Triggers file recreated${NC}"
    # #region agent log
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"B\",\"location\":\"install.sh:45\",\"message\":\"Triggers file fixed\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
fi

# Step 2: Fix status file if corrupted - be very aggressive
echo -e "${YELLOW}  Checking dpkg status file...${NC}"

# Backup current status file if it exists
if [ -f /var/lib/dpkg/status ]; then
    # #region agent log
    STATUS_SIZE=$(stat -c%s /var/lib/dpkg/status 2>/dev/null || echo 0)
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"C\",\"location\":\"install.sh:51\",\"message\":\"Status file found\",\"data\":{\"statusFileSize\":$STATUS_SIZE},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Check if status file is valid by checking for binary/corrupted data
    # Read first 100 bytes to check for invalid characters
    FIRST_100=$(head -c 100 /var/lib/dpkg/status 2>/dev/null | od -An -tx1 -v | tr -d ' \n')
    
    # Check if contains non-ASCII/non-hex values (indicates corruption)
    # Valid hex values are 00-7f (ASCII) and occasional higher values
    # If we see patterns like qV# or non-printable characters, it's corrupted
    IS_CORRUPTED=false
    
    if echo "$FIRST_100" | grep -qiE "[a-f]{4}|qV#"; then
        IS_CORRUPTED=true
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"C1\",\"location\":\"install.sh:65\",\"message\":\"Binary corruption detected in status file\",\"data\":{\"hexPreview\":\"$(echo "$FIRST_100" | head -c 50)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
    elif ! grep -q "^Package: " /var/lib/dpkg/status 2>/dev/null; then
        # No valid Package entries at start of file
        IS_CORRUPTED=true
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"C2\",\"location\":\"install.sh:70\",\"message\":\"No Package entries at start\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
    else
        # Check first line - should start with "Package:"
        FIRST_LINE=$(head -n 1 /var/lib/dpkg/status 2>/dev/null)
        if ! echo "$FIRST_LINE" | grep -q "^Package: "; then
            IS_CORRUPTED=true
            # #region agent log
            echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"C3\",\"location\":\"install.sh:75\",\"message\":\"First line doesn't start with Package\",\"data\":{\"firstLine\":\"$(echo "$FIRST_LINE" | head -c 50)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
            # #endregion agent log
        fi
    fi
    
    # If corrupted, completely recreate the file
    if [ "$IS_CORRUPTED" = true ]; then
        echo -e "${YELLOW}  Status file is corrupted, COMPLETELY RECREATING...${NC}"
        # Backup corrupted file
        cp /var/lib/dpkg/status /var/lib/dpkg/status.backup.$(date +%s) 2>/dev/null || true
        
        # Completely remove corrupted file
        rm -f /var/lib/dpkg/status
        rm -f /var/lib/dpkg/status-old 2>/dev/null || true
        
        # Get architecture
        ARCH=$(dpkg --print-architecture 2>/dev/null || echo armhf)
        
        # Create minimal valid status file
        cat > /var/lib/dpkg/status << STATUS_EOF
Package: dpkg
Status: install ok installed
Priority: required
Section: admin
Architecture: $ARCH
Version: $(dpkg -l dpkg 2>/dev/null | grep dpkg | awk '{print $3}')
Description: Debian package management system

STATUS_EOF
        
        chmod 644 /var/lib/dpkg/status
        echo -e "${GREEN}  ✓ Status file completely recreated${NC}"
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"D\",\"location\":\"install.sh:90\",\"message\":\"Status file recreated\",\"data\":{\"arch\":\"$ARCH\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
    else
        echo -e "${GREEN}  ✓ Status file appears valid${NC}"
    fi
else
    # If status file doesn't exist, create minimal one
    echo -e "${YELLOW}  Status file missing, creating...${NC}"
    # #region agent log
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"C\",\"location\":\"install.sh:95\",\"message\":\"Status file missing\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Get architecture
    ARCH=$(dpkg --print-architecture 2>/dev/null || echo armhf)
    
    # Create minimal valid status file
    cat > /var/lib/dpkg/status << STATUS_EOF
Package: dpkg
Status: install ok installed
Priority: required
Section: admin
Architecture: $ARCH
Version: $(dpkg -l dpkg 2>/dev/null | grep dpkg | awk '{print $3}')
Description: Debian package management system

STATUS_EOF
    
    chmod 644 /var/lib/dpkg/status
    echo -e "${GREEN}  ✓ Status file created${NC}"
fi

# Step 3: Remove corrupted package list files
echo -e "${YELLOW}  Checking for corrupted package list files...${NC}"
# Find and remove .list files that are likely corrupted
find /var/lib/dpkg/info -name "*.list" -type f 2>/dev/null | while read LIST_FILE; do
    # Check if file is suspicious (empty or has no valid entries)
    if [ -f "$LIST_FILE" ]; then
        # Check if file has at least one line starting with /
        if ! grep -q "^/" "$LIST_FILE" 2>/dev/null; then
            echo -e "${YELLOW}  Removing suspicious list file: $(basename "$LIST_FILE")${NC}"
            # Backup first
            cp "$LIST_FILE" "${LIST_FILE}.backup.$(date +%s)" 2>/dev/null || true
            rm -f "$LIST_FILE"
        fi
    fi
done 2>/dev/null || true
echo -e "${GREEN}  ✓ Package list files checked${NC}"
# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"E\",\"location\":\"install.sh:95\",\"message\":\"Package list files checked\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

# Step 4: Try to configure dpkg (may fail, that's OK)
echo -e "${YELLOW}  Attempting to configure dpkg...${NC}"
if dpkg --configure -a 2>&1 | tee /tmp/dpkg_configure.log; then
    echo -e "${GREEN}  ✓ dpkg configured successfully${NC}"
else
    EXIT_CODE=$?
    ERROR_MSG=$(cat /tmp/dpkg_configure.log 2>/dev/null || echo "Unknown error")
    # #region agent log
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"F\",\"location\":\"install.sh:105\",\"message\":\"dpkg configure failed\",\"data\":{\"exitCode\":$EXIT_CODE,\"errorPreview\":\"$(echo "$ERROR_MSG" | head -c 200)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Check for specific error: files list file contains empty filename
    if echo "$ERROR_MSG" | grep -qiE "files list file.*contains empty filename|unrecoverable fatal error"; then
        echo -e "${YELLOW}  Detected corrupted package files, attempting fix...${NC}"
        
        # Extract package name
        PACKAGE_NAME=$(echo "$ERROR_MSG" | grep -oE "package '[^']+'" | sed "s/package '//; s/'//" | head -n 1)
        
        if [ -n "$PACKAGE_NAME" ]; then
            echo -e "${YELLOW}  Removing corrupted package: $PACKAGE_NAME${NC}"
            # Extract base package name
            BASE_PACKAGE=$(echo "$PACKAGE_NAME" | cut -d: -f1)
            
            # Remove all files for this package
            rm -f /var/lib/dpkg/info/${PACKAGE_NAME}.* 2>/dev/null || true
            rm -f /var/lib/dpkg/info/${BASE_PACKAGE}.* 2>/dev/null || true
            
            # Remove from status file
            awk -v pkg="$PACKAGE_NAME" -v base="$BASE_PACKAGE" '
                /^Package: / {in_pkg = ($2 == pkg || $2 == base)}
                !in_pkg {print}
                /^$/ && in_pkg {in_pkg = 0}
            ' /var/lib/dpkg/status > /var/lib/dpkg/status.tmp 2>/dev/null && mv /var/lib/dpkg/status.tmp /var/lib/dpkg/status || true
            
            echo -e "${GREEN}  ✓ Removed corrupted package files${NC}"
            
            # Try to configure again
            dpkg --configure -a 2>/dev/null || true
        fi
    else
        echo -e "${YELLOW}  dpkg configure failed (will continue with apt-get)${NC}"
    fi
fi

# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-fix\",\"hypothesisId\":\"G\",\"location\":\"install.sh:130\",\"message\":\"dpkg fix completed, proceeding to apt-get\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

# Now proceed with apt-get update
apt-get update -qq 2>&1 | tee /tmp/apt_update_error.log || {
    # #region agent log
    EXIT_CODE=$?
    ERROR_MSG=$(cat /tmp/apt_update_error.log 2>/dev/null || echo "Unknown error")
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"H\",\"location\":\"install.sh:135\",\"message\":\"apt-get update failed\",\"data\":{\"exitCode\":$EXIT_CODE,\"errorPreview\":\"$(echo "$ERROR_MSG" | head -c 200)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Check if error is related to dpkg status
    if echo "$ERROR_MSG" | grep -qiE "Problem with MergeList.*status|Encountered a section with no Package"; then
        echo -e "${YELLOW}  Status file still corrupted, recreating...${NC}"
        # Recreate minimal status file again
        ARCH=$(dpkg --print-architecture 2>/dev/null || echo armhf)
        cat > /var/lib/dpkg/status << STATUS_EOF
Package: dpkg
Status: install ok installed
Priority: required
Section: admin
Architecture: $ARCH
Version: $(dpkg -l dpkg 2>/dev/null | grep dpkg | awk '{print $3}')
Description: Debian package management system

STATUS_EOF
        chmod 644 /var/lib/dpkg/status
        
        # Retry apt-get update
        apt-get update -qq || {
            RETRY_EXIT=$?
            RETRY_ERROR=$(cat /tmp/apt_update_error2.log 2>/dev/null || echo "Unknown error")
            echo -e "${RED}  apt-get update still failing after fix${NC}"
            exit $RETRY_EXIT
        }
    else
        exit $EXIT_CODE
    fi
}

# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"I\",\"location\":\"install.sh:165\",\"message\":\"apt-get update succeeded\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

apt-get upgrade -y -qq || {
    # #region agent log
    EXIT_CODE=$?
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"J\",\"location\":\"install.sh:168\",\"message\":\"apt-get upgrade failed\",\"data\":{\"exitCode\":$EXIT_CODE,\"error\":\"apt-get upgrade failed with code $EXIT_CODE\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    exit $EXIT_CODE
}

# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"K\",\"location\":\"install.sh:175\",\"message\":\"apt-get upgrade succeeded\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
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
    sed "s|/root/VampGotchi|$SCRIPT_DIR|g; s|vampgotchi\.py|vampigotchi.py|g" "$SERVICE_SOURCE" > "$SERVICE_FILE" 2>/dev/null || cp "$SERVICE_SOURCE" "$SERVICE_FILE"
    systemctl daemon-reload > /dev/null 2>&1
    echo -e "${GREEN}✓ Systemd service installed${NC}"
    echo -e "${YELLOW}  To enable auto-start: sudo systemctl enable vampigotchi${NC}"
    echo -e "${YELLOW}  To start service: sudo systemctl start vampigotchi${NC}"
else
    echo -e "${YELLOW}Systemd service file not found, skipping...${NC}"
fi

# Final verification
echo ""
echo -e "${GREEN}=================================="
echo -e "Installation completed successfully!${NC}"
echo ""
echo "Next steps:"
echo "1. Run: sudo python3 vampigotchi.py"
echo "2. Or enable service: sudo systemctl enable --now vampigotchi"
echo "3. Access web interface at http://<device-ip>"
echo ""
echo -e "${GREEN}Happy hacking! 🧛🦇${NC}"
