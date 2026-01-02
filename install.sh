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
# This is a known issue on fresh Pi installations where the status file gets corrupted
if [ -f /var/lib/dpkg/status ]; then
    # #region agent log
    STATUS_SIZE=$(stat -c%s /var/lib/dpkg/status 2>/dev/null || echo 0)
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"D\",\"location\":\"install.sh:62\",\"message\":\"Checking dpkg status file\",\"data\":{\"statusFileSize\":$STATUS_SIZE},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Always check if status-old exists and use it if current file has issues
    if [ -f /var/lib/dpkg/status-old ] && [ -s /var/lib/dpkg/status-old ]; then
        OLD_SIZE=$(stat -c%s /var/lib/dpkg/status-old 2>/dev/null || echo 0)
        CURRENT_SIZE=$(stat -c%s /var/lib/dpkg/status 2>/dev/null || echo 0)
        
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"E1\",\"location\":\"install.sh:70\",\"message\":\"Comparing status files\",\"data\":{\"currentSize\":$CURRENT_SIZE,\"oldSize\":$OLD_SIZE},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        
        # Check for common corruption signs
        PACKAGE_COUNT=$(grep -c "^Package: " /var/lib/dpkg/status 2>/dev/null || echo 0)
        OLD_PACKAGE_COUNT=$(grep -c "^Package: " /var/lib/dpkg/status-old 2>/dev/null || echo 0)
        NEEDS_RECOVERY=false
        
        # Check if file is empty or too small
        if [ ! -s /var/lib/dpkg/status ] || [ "$STATUS_SIZE" -lt 1000 ]; then
            NEEDS_RECOVERY=true
        # Check if no Package: entries found
        elif [ "$PACKAGE_COUNT" -eq 0 ]; then
            NEEDS_RECOVERY=true
        # Check if file size is suspiciously different (current much smaller than old)
        elif [ "$CURRENT_SIZE" -lt 1000 ] && [ "$OLD_SIZE" -gt 1000 ]; then
            NEEDS_RECOVERY=true
        # Check if old file has more packages (indicates current file lost data)
        elif [ "$OLD_PACKAGE_COUNT" -gt "$PACKAGE_COUNT" ] && [ "$PACKAGE_COUNT" -gt 0 ]; then
            # If old has significantly more packages, current might be corrupted
            if [ $((OLD_PACKAGE_COUNT - PACKAGE_COUNT)) -gt 10 ]; then
                NEEDS_RECOVERY=true
            fi
        fi
        
        # Additional check: look for sections without Package: header (the specific error we're seeing)
        # Count empty lines followed by non-Package lines (invalid sections)
        INVALID_SECTIONS=$(awk '/^$/ {empty=1; next} empty && !/^Package: / && !/^[[:space:]]/ && length($0) > 0 {count++} {empty=0} END {print count+0}' /var/lib/dpkg/status 2>/dev/null || echo 0)
        if [ "$INVALID_SECTIONS" -gt 0 ]; then
            NEEDS_RECOVERY=true
            # #region agent log
            echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"E3\",\"location\":\"install.sh:105\",\"message\":\"Found sections without Package header\",\"data\":{\"invalidSections\":$INVALID_SECTIONS},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
            # #endregion agent log
        fi
        
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"E2\",\"location\":\"install.sh:90\",\"message\":\"Status file validation\",\"data\":{\"packageCount\":$PACKAGE_COUNT,\"oldPackageCount\":$OLD_PACKAGE_COUNT,\"needsRecovery\":$NEEDS_RECOVERY},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        
        if [ "$NEEDS_RECOVERY" = true ]; then
            echo -e "${YELLOW}  dpkg status file appears corrupted, recovering from backup...${NC}"
            BACKUP_STATUS="/var/lib/dpkg/status.backup.$(date +%s)"
            cp /var/lib/dpkg/status "$BACKUP_STATUS" 2>/dev/null || true
            cp /var/lib/dpkg/status-old /var/lib/dpkg/status 2>/dev/null || true
            echo -e "${GREEN}  ✓ Status file recovered from backup${NC}"
        fi
    elif [ ! -s /var/lib/dpkg/status ] || [ "$STATUS_SIZE" -lt 1000 ]; then
        # If status-old doesn't exist but current file is empty/small, this is a problem
        echo -e "${YELLOW}  dpkg status file is empty or too small, but no backup available${NC}"
        echo -e "${YELLOW}  This may cause issues - attempting to rebuild...${NC}"
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"E3\",\"location\":\"install.sh:100\",\"message\":\"Status file empty, no backup available\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        dpkg --clear-avail 2>/dev/null || true
    fi
fi

# Try to fix any broken dpkg packages (non-blocking)
echo -e "${YELLOW}  Verifying dpkg packages...${NC}"
dpkg --configure -a 2>&1 | tee /tmp/dpkg_configure_error.log || {
    # #region agent log
    EXIT_CODE=$?
    ERROR_MSG=$(cat /tmp/dpkg_configure_error.log 2>/dev/null || echo "Unknown error")
    echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"F\",\"location\":\"install.sh:135\",\"message\":\"dpkg configure failed\",\"data\":{\"exitCode\":$EXIT_CODE,\"errorPreview\":\"$(echo "$ERROR_MSG" | head -c 200)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
    # #endregion agent log
    
    # Check if error is related to corrupted package files list
    if echo "$ERROR_MSG" | grep -qiE "files list file.*contains empty filename|unrecoverable fatal error"; then
        echo -e "${YELLOW}  Detected corrupted package files list during dpkg configure, attempting to fix...${NC}"
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"G\",\"location\":\"install.sh:145\",\"message\":\"Fixing corrupted package files list during configure\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        
        # Extract package name from error message
        # Error format: "files list file for package 'package-name:arch' contains empty filename"
        PACKAGE_NAME=$(echo "$ERROR_MSG" | grep -oE "package '[^']+'" | sed "s/package '//; s/'//" | head -n 1)
        
        # If extraction failed, try alternative pattern
        if [ -z "$PACKAGE_NAME" ]; then
            PACKAGE_NAME=$(echo "$ERROR_MSG" | grep -oE "for package [^ ]+" | sed "s/for package //" | head -n 1)
        fi
        
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"dpkg-check\",\"hypothesisId\":\"H\",\"location\":\"install.sh:158\",\"message\":\"Corrupted package detected\",\"data\":{\"packageName\":\"$PACKAGE_NAME\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        
        if [ -n "$PACKAGE_NAME" ]; then
            echo -e "${YELLOW}  Removing corrupted package files for: $PACKAGE_NAME${NC}"
            # Extract base package name (remove architecture suffix like :armhf)
            BASE_PACKAGE=$(echo "$PACKAGE_NAME" | cut -d: -f1)
            
            # Remove corrupted package files (try both with and without architecture)
            rm -f /var/lib/dpkg/info/${PACKAGE_NAME}.* 2>/dev/null || true
            rm -f /var/lib/dpkg/info/${BASE_PACKAGE}.* 2>/dev/null || true
            
            # Also remove the list file if it exists
            rm -f /var/lib/dpkg/info/${PACKAGE_NAME}.list 2>/dev/null || true
            rm -f /var/lib/dpkg/info/${BASE_PACKAGE}.list 2>/dev/null || true
            
            # Remove package from status if it exists
            if [ -f /var/lib/dpkg/status ]; then
                # Remove package entry from status file (match both with and without architecture)
                awk -v pkg="$PACKAGE_NAME" -v base="$BASE_PACKAGE" '
                    /^Package: / {
                        pkg_name = $2
                        in_pkg = (pkg_name == pkg || pkg_name == base)
                    }
                    !in_pkg {print}
                    /^$/ && in_pkg {in_pkg = 0}
                ' /var/lib/dpkg/status > /var/lib/dpkg/status.tmp 2>/dev/null && mv /var/lib/dpkg/status.tmp /var/lib/dpkg/status || true
            fi
            echo -e "${GREEN}  ✓ Removed corrupted package files${NC}"
        else
            echo -e "${YELLOW}  Could not extract package name, attempting general cleanup...${NC}"
            # If we can't identify the specific package, try to find and fix any .list files with issues
            find /var/lib/dpkg/info -name "*.list" -type f -exec sh -c 'if ! grep -q "^/" "$1" 2>/dev/null; then echo "$1"; fi' _ {} \; 2>/dev/null | head -5 | while read FILE; do
                echo -e "${YELLOW}  Removing potentially corrupted list file: $FILE${NC}"
                rm -f "$FILE" 2>/dev/null || true
            done
        fi
        
        # Retry dpkg configure after cleanup
        echo -e "${GREEN}  ✓ Fixed, retrying dpkg configure...${NC}"
        dpkg --configure -a 2>/dev/null || true
    fi
}

# Clean up any corrupted package files lists
# Note: We'll handle this reactively when the error occurs, as proactive detection
# can be too aggressive and remove valid files

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
    
    # Check if error is related to corrupted package files list
    if echo "$ERROR_MSG" | grep -qiE "files list file.*contains empty filename|unrecoverable fatal error"; then
        echo -e "${YELLOW}  Detected corrupted package files list, attempting to fix...${NC}"
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"K\",\"location\":\"install.sh:152\",\"message\":\"Fixing corrupted package files list\",\"data\":{},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        
        # Extract package name from error message
        # Error format: "files list file for package 'package-name:arch' contains empty filename"
        PACKAGE_NAME=$(echo "$ERROR_MSG" | grep -oE "package '[^']+'" | sed "s/package '//; s/'//" | head -n 1)
        
        # If extraction failed, try alternative pattern
        if [ -z "$PACKAGE_NAME" ]; then
            PACKAGE_NAME=$(echo "$ERROR_MSG" | grep -oE "for package [^ ]+" | sed "s/for package //" | head -n 1)
        fi
        
        # #region agent log
        echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"L\",\"location\":\"install.sh:158\",\"message\":\"Corrupted package detected\",\"data\":{\"packageName\":\"$PACKAGE_NAME\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
        # #endregion agent log
        
        if [ -n "$PACKAGE_NAME" ]; then
            echo -e "${YELLOW}  Removing corrupted package files for: $PACKAGE_NAME${NC}"
            # Extract base package name (remove architecture suffix like :armhf)
            BASE_PACKAGE=$(echo "$PACKAGE_NAME" | cut -d: -f1)
            
            # Remove corrupted package files (try both with and without architecture)
            rm -f /var/lib/dpkg/info/${PACKAGE_NAME}.* 2>/dev/null || true
            rm -f /var/lib/dpkg/info/${BASE_PACKAGE}.* 2>/dev/null || true
            
            # Remove package from status if it exists
            if [ -f /var/lib/dpkg/status ]; then
                # Remove package entry from status file (match both with and without architecture)
                awk -v pkg="$PACKAGE_NAME" -v base="$BASE_PACKAGE" '
                    /^Package: / {
                        pkg_name = $2
                        in_pkg = (pkg_name == pkg || pkg_name == base)
                    }
                    !in_pkg {print}
                    /^$/ && in_pkg {in_pkg = 0}
                ' /var/lib/dpkg/status > /var/lib/dpkg/status.tmp 2>/dev/null && mv /var/lib/dpkg/status.tmp /var/lib/dpkg/status || true
            fi
            echo -e "${GREEN}  ✓ Removed corrupted package files${NC}"
        else
            echo -e "${YELLOW}  Could not extract package name from error, attempting general cleanup...${NC}"
            # If we can't identify the specific package, try to fix dpkg state
            dpkg --configure -a 2>/dev/null || true
        fi
        
        # Try to fix dpkg state
        dpkg --configure -a 2>/dev/null || true
        
        echo -e "${GREEN}  ✓ Fixed, retrying apt-get update...${NC}"
        
        # Retry apt-get update
        apt-get update -qq 2>&1 | tee /tmp/apt_update_error2.log || {
            RETRY_EXIT=$?
            RETRY_ERROR=$(cat /tmp/apt_update_error2.log 2>/dev/null || echo "Unknown error")
            # #region agent log
            echo "{\"sessionId\":\"debug-session\",\"runId\":\"pre-apt\",\"hypothesisId\":\"M\",\"location\":\"install.sh:175\",\"message\":\"apt-get update failed after package files fix\",\"data\":{\"exitCode\":$RETRY_EXIT,\"errorPreview\":\"$(echo "$RETRY_ERROR" | head -c 200)\"},\"timestamp\":$(date +%s000)}" >> "$LOG_FILE"
            # #endregion agent log
            echo -e "${RED}  apt-get update still failing after fix attempt${NC}"
            exit $RETRY_EXIT
        }
    # Check if error is related to dpkg status file
    elif echo "$ERROR_MSG" | grep -qiE "Problem with MergeList.*status|Encountered a section with no Package|dpkg.*status.*could not be parsed|section with no Package: header"; then
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

