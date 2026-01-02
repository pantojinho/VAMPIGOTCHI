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
# This is a known issue where the triggers file gets corrupted with syntax errors
if [ -f /var/lib/dpkg/triggers/File ]; then
    # #region agent log
    FILE_SIZE=$(stat -c%s /var/lib/dpkg/triggers/File 2>/dev/null || echo 0)
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"B\",\"location\":\"install.sh:38\",\"message\":\"Triggers file exists, backing up and recreating\",\"data\":{\"fileSize\":$FILE_SIZE},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    echo -e "${YELLOW}  Fixing dpkg triggers file (common issue on Pi)...${NC}"
    # Backup original file
    BACKUP_FILE="/var/lib/dpkg/triggers/File.backup.$(date +%s)"
    cp /var/lib/dpkg/triggers/File "$BACKUP_FILE" 2>/dev/null || true
    
    # Remove corrupted file - dpkg will recreate it with correct syntax when needed
    rm -f /var/lib/dpkg/triggers/File 2>/dev/null || true
    touch /var/lib/dpkg/triggers/File 2>/dev/null || true
    chmod 644 /var/lib/dpkg/triggers/File 2>/dev/null || true
    
    # #region agent log
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"C\",\"location\":\"install.sh:50\",\"message\":\"Triggers file recreated\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    echo -e "${GREEN}  ✓ Triggers file recreated${NC}"
fi

# Check and fix dpkg status file if corrupted
if [ -f /var/lib/dpkg/status ]; then
    # #region agent log
    STATUS_SIZE=$(stat -c%s /var/lib/dpkg/status 2>/dev/null || echo 0)
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"D\",\"location\":\"install.sh:62\",\"message\":\"Checking dpkg status file\",\"data\":{\"statusFileSize\":$STATUS_SIZE},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Check if status file is empty or too small (should be at least a few KB)
    if [ ! -s /var/lib/dpkg/status ] || [ "$STATUS_SIZE" -lt 1000 ]; then
        echo -e "${YELLOW}  dpkg status file appears empty or corrupted, attempting to fix...${NC}"
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"E1\",\"location\":\"install.sh:68\",\"message\":\"Status file empty or too small\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        
        # Backup and try to recover from available sources
        BACKUP_STATUS="/var/lib/dpkg/status.backup.$(date +%s)"
        cp /var/lib/dpkg/status "$BACKUP_STATUS" 2>/dev/null || true
        
        # Try to recover from status-old if available
        if [ -f /var/lib/dpkg/status-old ] && [ -s /var/lib/dpkg/status-old ]; then
            echo -e "${YELLOW}  Attempting to recover from status-old...${NC}"
            cp /var/lib/dpkg/status-old /var/lib/dpkg/status 2>/dev/null || true
        fi
    else
        # Check for syntax errors: look for sections without Package: header
        # A valid status file should have "Package: " at the start of each package entry
        if ! grep -q "^Package: " /var/lib/dpkg/status 2>/dev/null || [ $(grep -c "^Package: " /var/lib/dpkg/status 2>/dev/null || echo 0) -eq 0 ]; then
            echo -e "${YELLOW}  dpkg status file has syntax errors, attempting to fix...${NC}"
            # #region agent log
            echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"E2\",\"location\":\"install.sh:80\",\"message\":\"Status file has syntax errors\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
            # #endregion agent log
            
            # Backup and try to recover
            BACKUP_STATUS="/var/lib/dpkg/status.backup.$(date +%s)"
            cp /var/lib/dpkg/status "$BACKUP_STATUS" 2>/dev/null || true
            
            # Try to recover from status-old if available
            if [ -f /var/lib/dpkg/status-old ] && [ -s /var/lib/dpkg/status-old ]; then
                echo -e "${YELLOW}  Attempting to recover from status-old...${NC}"
                cp /var/lib/dpkg/status-old /var/lib/dpkg/status 2>/dev/null || true
            fi
        fi
    fi
fi

# Try to fix any broken dpkg packages (non-blocking)
echo -e "${YELLOW}  Verifying dpkg packages...${NC}"
dpkg --configure -a 2>/dev/null || true

# #region agent log
echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"F\",\"location\":\"install.sh:95\",\"message\":\"dpkg check completed, proceeding to apt-get\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
# #endregion agent log

# Re-enable exit on error for the rest of the script
set -e

apt-get update -qq 2>&1 | tee /tmp/apt_update_error.log || {
    # #region agent log
    EXIT_CODE=$?
    ERROR_MSG=$(cat /tmp/apt_update_error.log 2>/dev/null || echo "Unknown error")
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"D\",\"location\":\"install.sh:73\",\"message\":\"apt-get update failed\",\"data\":{\"exitCode\":$EXIT_CODE,\"errorPreview\":\"$(echo "$ERROR_MSG" | head -c 200)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Check if error is related to dpkg status file
    if echo "$ERROR_MSG" | grep -qiE "Problem with MergeList.*status|Encountered a section with no Package|dpkg.*status.*could not be parsed"; then
        echo -e "${YELLOW}  Detected dpkg status file error, attempting to fix...${NC}"
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"H\",\"location\":\"install.sh:120\",\"message\":\"Fixing status file after apt-get error\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        
        # Try to recover from status-old
        BACKUP_STATUS="/var/lib/dpkg/status.backup.$(date +%s)"
        cp /var/lib/dpkg/status "$BACKUP_STATUS" 2>/dev/null || true
        
        if [ -f /var/lib/dpkg/status-old ] && [ -s /var/lib/dpkg/status-old ]; then
            echo -e "${YELLOW}  Recovering from status-old backup...${NC}"
            cp /var/lib/dpkg/status-old /var/lib/dpkg/status 2>/dev/null || true
            dpkg --configure -a 2>/dev/null || true
        else
            # If status-old is not available, this is a serious issue
            # Try to use dpkg --clear-avail and rebuild
            echo -e "${YELLOW}  status-old not available, attempting dpkg repair...${NC}"
            # #region agent log
            echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"J\",\"location\":\"install.sh:140\",\"message\":\"Attempting dpkg repair without status-old\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
            # #endregion agent log
            
            # Try to rebuild status from available information
            dpkg --clear-avail 2>/dev/null || true
            # This is risky, but sometimes necessary
            # The system will rebuild status as packages are queried
        fi
        
        echo -e "${GREEN}  ✓ Fixed, retrying apt-get update...${NC}"
        
        # Retry apt-get update
        apt-get update -qq 2>&1 | tee /tmp/apt_update_error2.log || {
            RETRY_EXIT=$?
            RETRY_ERROR=$(cat /tmp/apt_update_error2.log 2>/dev/null || echo "Unknown error")
            # #region agent log
            echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"I\",\"location\":\"install.sh:150\",\"message\":\"apt-get update failed after status fix\",\"data\":{\"exitCode\":$RETRY_EXIT,\"errorPreview\":\"$(echo "$RETRY_ERROR" | head -c 200)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
            # #endregion agent log
            echo -e "${RED}  apt-get update still failing after status fix${NC}"
            echo -e "${YELLOW}  You may need to manually fix /var/lib/dpkg/status${NC}"
            exit $RETRY_EXIT
        }
    # Check if error is related to dpkg triggers file (multiple possible error messages)
    elif echo "$ERROR_MSG" | grep -qiE "syntax error.*triggers.*File|dpkg.*error.*triggers|error.*triggers file"; then
        echo -e "${YELLOW}  Detected dpkg triggers file error, attempting to fix...${NC}"
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"E\",\"location\":\"install.sh:80\",\"message\":\"Fixing triggers file after apt-get error\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        
        # Always recreate the triggers file
        BACKUP_FILE="/var/lib/dpkg/triggers/File.backup.$(date +%s)"
        if [ -f /var/lib/dpkg/triggers/File ]; then
            cp /var/lib/dpkg/triggers/File "$BACKUP_FILE" 2>/dev/null || true
        fi
        rm -f /var/lib/dpkg/triggers/File 2>/dev/null || true
        touch /var/lib/dpkg/triggers/File 2>/dev/null || true
        chmod 644 /var/lib/dpkg/triggers/File 2>/dev/null || true
        
        # Try to fix dpkg state
        dpkg --configure -a 2>/dev/null || true
        
        echo -e "${GREEN}  ✓ Fixed, retrying apt-get update...${NC}"
        
        # Retry apt-get update
        apt-get update -qq 2>&1 | tee /tmp/apt_update_error2.log || {
            RETRY_EXIT=$?
            RETRY_ERROR=$(cat /tmp/apt_update_error2.log 2>/dev/null || echo "Unknown error")
            # #region agent log
            echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"F\",\"location\":\"install.sh:95\",\"message\":\"apt-get update failed after fix attempt\",\"data\":{\"exitCode\":$RETRY_EXIT,\"errorPreview\":\"$(echo "$RETRY_ERROR" | head -c 200)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
            # #endregion agent log
            echo -e "${RED}  apt-get update still failing after fix attempt${NC}"
            exit $RETRY_EXIT
        }
    else
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"G\",\"location\":\"install.sh:100\",\"message\":\"apt-get update failed with non-triggers error\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
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
# Try both possible names (vampigotchi.service and vampgotchi.service)
SERVICE_SOURCE=""
if [ -f "$SCRIPT_DIR/vampigotchi.service" ]; then
    SERVICE_SOURCE="$SCRIPT_DIR/vampigotchi.service"
elif [ -f "$SCRIPT_DIR/vampgotchi.service" ]; then
    SERVICE_SOURCE="$SCRIPT_DIR/vampgotchi.service"
fi

if [ -n "$SERVICE_SOURCE" ]; then
    SERVICE_FILE="/etc/systemd/system/vampigotchi.service"
    # Update the service file with correct paths before copying
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

