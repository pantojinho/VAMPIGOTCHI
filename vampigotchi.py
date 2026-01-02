#!/usr/bin/env python3
"""
VampGotchi - A Tamagotchi-like Bluetooth monitoring device
Monitors Bluetooth networks and performs jamming when needed.
"""

import subprocess
import time
import threading
import socket
import os
import sys
import re
import logging
from datetime import datetime
from pathlib import Path

# Third-party imports
try:
    from flask import Flask, render_template_string, request, jsonify
except ImportError:
    print("ERROR: Flask not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    from waveshare_epd import epd2in13_V4
except ImportError:
    print("WARNING: waveshare_epd not available. Display will be disabled.")
    epd2in13_V4 = None

from PIL import Image, ImageDraw, ImageFont

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

# ================= CONFIGURATION =================

CONFIG_FILE = "config.yml"
DEFAULT_CONFIG_FILE = "default_config.yml"

# Network configuration file paths
HOSTAPD_CONF = "/etc/hostapd/hostapd.conf"
DNSMASQ_CONF = "/etc/dnsmasq.conf"
WPA_SUPPLICANT_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"

# Default configuration values
DEFAULT_CONFIG = {
    "display_mode": "black",
    "display_full_refresh_interval": 30,
    "network_mode": "CLIENT",
    "ap_ssid": "VampGotchi-AP",
    "ap_pass": "vampgotchi123",
    "ap_ip": "192.168.4.1",
    "bleeding_path": "/root/BLEeding",
    "attack_timeout": 10,
    "scan_interval": 60,
    "debug_mode": False
}

# Global state
config = {}
current_mode = "UNKNOWN"
current_ip = "127.0.0.1"
start_time = datetime.now()

# BLEeding state
targets = []
targets_info = {}  # MAC -> {name, rssi, last_seen}
selected_target = ""
attacking = False
scan_status = "Idle"
attack_thread = None
last_scan_output = ""  # For debugging

# Statistics
total_scans = 0
total_attacks = 0
total_targets_found = 0
mood = "bored"  # bored, happy, excited, sad, angry
display_update_count = 0

# Character stats (VampGotchi stats)
hunger = 800  # 0-1000
blood = 100  # 0-100 (percentage)
level = 5
exp = 150
exp_to_next = 200
money = 400
player_level = 25
activity_messages = []  # List of recent activity messages
coffin_status = "SLEEPING"  # SLEEPING, AWAKE, etc.

# E-Paper display
epd = None
font = None
font_small = None
font_large = None

# ================= CONFIGURATION MANAGEMENT =================

def load_config():
    """Load configuration from YAML file, create from defaults if missing"""
    global config
    
    # Load defaults first
    config = DEFAULT_CONFIG.copy()
    
    # Try to load default_config.yml if it exists
    if os.path.exists(DEFAULT_CONFIG_FILE):
        try:
            with open(DEFAULT_CONFIG_FILE, 'r') as f:
                default_config = yaml.safe_load(f) or {}
                config.update(default_config)
        except Exception as e:
            print(f"Warning: Could not load {DEFAULT_CONFIG_FILE}: {e}")
    
    # Override with user config if it exists
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                user_config = yaml.safe_load(f) or {}
                config.update(user_config)
        except Exception as e:
            print(f"Warning: Could not load {CONFIG_FILE}: {e}")
    
    return config

def save_config():
    """Save current configuration to config.yml"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

# Load configuration on startup
config = load_config()

# ================= LOGGING SETUP =================

logging.basicConfig(
    level=logging.DEBUG if config.get("debug_mode", False) else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= NETWORK UTILITIES =================

def get_ip_address():
    """Get the device's IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def detect_mode():
    """Detect current network mode (AP or CLIENT)"""
    global current_mode, current_ip
    ip = get_ip_address()
    if ip.startswith("192.168.4"):
        current_mode = "AP"
        current_ip = ip
    else:
        current_mode = "CLIENT"
        current_ip = ip
    return current_mode, current_ip

# ================= NETWORK CONFIGURATION =================

def write_hostapd_conf():
    """Write hostapd configuration file"""
    ap_ssid = config.get("ap_ssid", "VampGotchi-AP")
    ap_pass = config.get("ap_pass", "vampgotchi123")
    
    config_content = f"""
interface=wlan0
driver=nl80211
ssid={ap_ssid}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={ap_pass}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
rsn_pairwise=CCMP
"""
    try:
        with open(HOSTAPD_CONF, 'w') as f:
            f.write(config_content)
    except Exception as e:
        logger.error(f"Error writing hostapd config: {e}")

def write_dnsmasq_conf():
    """Write dnsmasq configuration file"""
    ap_ip = config.get("ap_ip", "192.168.4.1")
    config_content = f"""
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
"""
    try:
        with open(DNSMASQ_CONF, 'w') as f:
            f.write(config_content)
    except Exception as e:
        logger.error(f"Error writing dnsmasq config: {e}")

def write_wpa_supplicant(ssid, password):
    """Write wpa_supplicant configuration file"""
    config_content = f"""
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
}}
"""
    try:
        with open(WPA_SUPPLICANT_CONF, 'w') as f:
            f.write(config_content)
    except Exception as e:
        logger.error(f"Error writing wpa_supplicant config: {e}")

def restart_services_ap():
    """Restart network services for AP mode"""
    logger.info("Switching to AP mode...")
    ap_ip = config.get("ap_ip", "192.168.4.1")
    
    subprocess.run(["systemctl", "stop", "wpa_supplicant"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "stop", "dhcpcd"], stderr=subprocess.DEVNULL)
    write_hostapd_conf()
    write_dnsmasq_conf()
    
    try:
        with open("/etc/dhcpcd.conf", "a") as f:
            f.write(f"\ninterface wlan0\nstatic ip_address={ap_ip}/24\nnohook wpa_supplicant\n")
    except:
        pass
    
    subprocess.run(["systemctl", "daemon-reload"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "restart", "dhcpcd"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "unmask", "hostapd"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "restart", "hostapd"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "restart", "dnsmasq"], stderr=subprocess.DEVNULL)

def restart_services_client(ssid, password):
    """Restart network services for client mode"""
    logger.info(f"Switching to client mode ({ssid})...")
    subprocess.run(["systemctl", "stop", "hostapd"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "stop", "dnsmasq"], stderr=subprocess.DEVNULL)
    write_wpa_supplicant(ssid, password)
    subprocess.run(["systemctl", "restart", "wpa_supplicant"], stderr=subprocess.DEVNULL)

# ================= BLE SCANNING =================

def run_bleeding_scan():
    """Run BLE scan using BLEeding"""
    global targets, targets_info, scan_status, total_scans, total_targets_found, mood, last_scan_output
    global hunger, blood, exp, level, exp_to_next, money, activity_messages
    
    scan_status = "Scanning..."
    mood = "excited"
    hunger = max(0, hunger - 10)  # Scanning consumes hunger
    activity_messages.append("> Scanning...")
    update_display()
    
    bleeding_path = config.get("bleeding_path", "/root/BLEeding")
    
    # Try direct import first (recommended approach)
    devices = []
    try:
        # Add BLEeding path to sys.path
        if bleeding_path not in sys.path:
            sys.path.insert(0, bleeding_path)
        
        from bleeding import ble_scan
        logger.info("Using direct BLEeding import for scanning")
        devices = ble_scan()
        
        # Convert to our format
        found_macs = []
        for device in devices:
            mac = device.get('address', '')
            if mac:
                mac = mac.upper()
                if mac not in found_macs:
                    found_macs.append(mac)
                    targets_info[mac] = {
                        'name': device.get('name', 'Unknown')[:20],
                        'rssi': device.get('rssi', 0),
                        'last_seen': datetime.now()
                    }
        
        targets = found_macs
        total_scans += 1
        total_targets_found = len(targets_info)
        
        if len(targets) > 0:
            mood = "happy"
            # Reward for finding devices
            exp += len(targets) * 5
            money += len(targets) * 2
            blood = min(100, blood + 5)
            activity_messages.append("> Found devices!")
            # Check for level up
            if exp >= exp_to_next:
                level += 1
                exp = 0
                exp_to_next = int(exp_to_next * 1.5)
                activity_messages.append("> Level up!")
        else:
            mood = "sad"
            activity_messages.append("> No devices found")
        
        scan_status = "Done"
        logger.info(f"Scan completed: {len(targets)} devices found")
        
    except ImportError:
        # Fallback to subprocess method
        logger.warning("Direct import failed, using subprocess method")
        try:
            old_cwd = os.getcwd()
            os.chdir(bleeding_path)
            
            result = subprocess.run(
                ['python3', 'bleeding.py', 'scan', '--ble', '--headless'],
                capture_output=True, text=True, timeout=20
            )
            
            last_scan_output = result.stdout + result.stderr
            output = last_scan_output
            
            # Parse output
            lines = output.split('\n')
            found_macs = []
            
            for line in lines:
                mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', line)
                if mac_match:
                    mac_str = mac_match.group(0).replace('-', ':').upper()
                    if mac_str not in found_macs:
                        found_macs.append(mac_str)
                        
                        device_name = "Unknown"
                        name_patterns = [
                            r'name[:\s]+([^\n,]+)',
                            r'([A-Za-z0-9\s\-_]+)\s+' + re.escape(mac_str),
                            r'Device[:\s]+([^\n,]+)'
                        ]
                        for pattern in name_patterns:
                            name_match = re.search(pattern, line, re.IGNORECASE)
                            if name_match:
                                device_name = name_match.group(1).strip()
                                break
                        
                        rssi = 0
                        rssi_patterns = [
                            r'RSSI[:\s]+(-?\d+)',
                            r'(-?\d+)\s*dBm',
                            r'signal[:\s]+(-?\d+)'
                        ]
                        for pattern in rssi_patterns:
                            rssi_match = re.search(pattern, line, re.IGNORECASE)
                            if rssi_match:
                                try:
                                    rssi = int(rssi_match.group(1))
                                    break
                                except:
                                    pass
                        
                        if mac_str not in targets_info:
                            total_targets_found += 1
                        
                        targets_info[mac_str] = {
                            'name': device_name[:20],
                            'rssi': rssi,
                            'last_seen': datetime.now()
                        }
            
            targets = found_macs
            total_scans += 1
            total_targets_found = len(targets_info)
            
            if len(targets) > 0:
                mood = "happy"
                # Reward for finding devices
                exp += len(targets) * 5
                money += len(targets) * 2
                blood = min(100, blood + 5)
                activity_messages.append("> Found devices!")
                # Check for level up
                if exp >= exp_to_next:
                    level += 1
                    exp = 0
                    exp_to_next = int(exp_to_next * 1.5)
                    activity_messages.append("> Level up!")
            else:
                mood = "sad"
                activity_messages.append("> No devices found")
            
            scan_status = "Done"
            os.chdir(old_cwd)
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            scan_status = "Error"
            mood = "sad"
            os.chdir(old_cwd)
    
    except Exception as e:
        logger.error(f"Scan error: {e}")
        scan_status = "Error"
        mood = "sad"
    
    update_display()

def run_bleeding_attack_thread(mac):
    """Run BLE attack in a separate thread"""
    global attacking, attack_thread, total_attacks, mood
    global hunger, blood, exp, level, exp_to_next, money, activity_messages
    
    attacking = True
    mood = "angry"
    total_attacks += 1
    hunger = max(0, hunger - 20)  # Attacking consumes more hunger
    blood = min(100, blood + 10)  # But increases blood
    exp += 15
    money += 10
    activity_messages.append("> Attacking target!")
    # Check for level up
    if exp >= exp_to_next:
        level += 1
        exp = 0
        exp_to_next = int(exp_to_next * 1.5)
        activity_messages.append("> Level up!")
    update_display()
    
    bleeding_path = config.get("bleeding_path", "/root/BLEeding")
    attack_timeout = config.get("attack_timeout", 10)
    
    try:
        old_cwd = os.getcwd()
        os.chdir(bleeding_path)
        cmd = ['python3', 'bleeding.py', 'deauth', mac, '--ble', '--timeout', str(attack_timeout)]
        subprocess.run(cmd)
        os.chdir(old_cwd)
    except Exception as e:
        logger.error(f"Attack error: {e}")
        os.chdir(old_cwd)
    
    attacking = False
    mood = "happy" if len(targets) > 0 else "bored"
    activity_messages.append("> Attack completed!")
    update_display()

def stop_bleeding_attack():
    """Stop any running BLE attack"""
    global attacking, attack_thread
    if attack_thread and attack_thread.is_alive():
        subprocess.run(["pkill", "-f", "bleeding.py"], stderr=subprocess.DEVNULL)
        attacking = False
        update_display()

# ================= E-PAPER DISPLAY =================

def init_display_safe():
    """Initialize E-paper display safely"""
    global epd, font, font_small, font_large
    
    if epd2in13_V4 is None:
        logger.warning("E-paper library not available, display disabled")
        epd = None
        return
    
    try:
        epd = epd2in13_V4.EPD()
        epd.init()
        epd.Clear(0xFF)
        
        logger.info(f"E-paper display initialized: {epd.width}x{epd.height} pixels")
        
        # Try to load better fonts
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
            logger.info("TrueType fonts loaded successfully")
        except Exception as font_error:
            logger.warning(f"Using default fonts (TrueType not available: {font_error})")
            font = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_large = ImageFont.load_default()
        
        logger.info("E-paper display initialized successfully")
        
    except Exception as e:
        logger.error(f"CRITICAL ERROR INITIALIZING E-PAPER: {e}")
        logger.info("System will continue running without display")
        epd = None

def draw_battery_icon(draw, x, y, fill_color):
    """Draw battery icon"""
    # Battery outline
    draw.rectangle([x, y, x+12, y+6], outline=fill_color, width=1)
    # Battery tip
    draw.rectangle([x+12, y+2, x+14, y+4], fill=fill_color)
    # Battery bars (full)
    draw.rectangle([x+2, y+1, x+4, y+5], fill=fill_color)
    draw.rectangle([x+5, y+1, x+7, y+5], fill=fill_color)
    draw.rectangle([x+8, y+1, x+10, y+5], fill=fill_color)

def draw_wifi_icon(draw, x, y, fill_color):
    """Draw Wi-Fi icon"""
    # Wi-Fi signal waves
    draw.arc([x, y+2, x+8, y+10], start=45, end=135, fill=fill_color, width=1)
    draw.arc([x+2, y+4, x+6, y+8], start=45, end=135, fill=fill_color, width=1)
    draw.ellipse([x+3, y+5, x+5, y+7], fill=fill_color)

def draw_bat_icon(draw, x, y, fill_color):
    """Draw bat icon"""
    # Bat body
    draw.ellipse([x+3, y+2, x+7, y+6], fill=fill_color)
    # Bat wings
    draw.polygon([(x, y+4), (x+2, y+2), (x+3, y+4)], fill=fill_color)
    draw.polygon([(x+7, y+4), (x+8, y+2), (x+10, y+4)], fill=fill_color)

def draw_coffin_icon(draw, x, y, fill_color):
    """Draw coffin icon"""
    # Coffin body
    draw.rectangle([x, y+2, x+8, y+6], fill=fill_color)
    # Coffin lid (open)
    draw.arc([x-1, y, x+9, y+4], start=180, end=0, fill=fill_color, width=1)

def draw_potion_icon(draw, x, y, fill_color):
    """Draw potion bottle icon"""
    # Bottle body
    draw.rectangle([x+2, y+2, x+6, y+6], outline=fill_color, width=1)
    # Bottle neck
    draw.rectangle([x+3, y, x+5, y+2], fill=fill_color)
    # Liquid inside
    draw.rectangle([x+3, y+3, x+5, y+5], fill=fill_color)

def draw_vampire_chibi(draw, x, y, mood_state, fill_color):
    """Draw chibi-style vampire character like in the image"""
    # Head (smaller to fit display)
    draw.ellipse([x+3, y+3, x+25, y+25], outline=fill_color, width=1)
    
    # Hair forming horns (black hair)
    draw.polygon([(x+5, y+1), (x+8, y+5), (x+7, y+7)], fill=fill_color)  # Left horn
    draw.polygon([(x+21, y+1), (x+18, y+5), (x+19, y+7)], fill=fill_color)  # Right horn
    
    # Eyes - winking (right eye closed)
    if mood_state == "happy" or mood_state == "excited":
        # Left eye open, right eye winking
        draw.ellipse([x+8, y+11, x+11, y+14], fill=fill_color)  # Left eye
        draw.line([x+17, y+12, x+20, y+12], fill=fill_color, width=2)  # Right eye winking
    elif mood_state == "angry":
        # Angry eyes
        draw.line([x+8, y+13, x+11, y+11], fill=fill_color, width=2)  # Left
        draw.line([x+17, y+11, x+20, y+13], fill=fill_color, width=2)  # Right
    elif mood_state == "sad":
        # Sad eyes
        draw.ellipse([x+8, y+11, x+11, y+14], fill=fill_color)
        draw.ellipse([x+17, y+11, x+20, y+14], fill=fill_color)
    else:  # bored
        # Normal eyes
        draw.ellipse([x+8, y+11, x+11, y+14], fill=fill_color)
        draw.ellipse([x+17, y+11, x+20, y+14], fill=fill_color)
    
    # Small fangs
    draw.rectangle([x+11, y+17, x+12, y+20], fill=fill_color)
    draw.rectangle([x+17, y+17, x+18, y+20], fill=fill_color)
    
    # Cape with white collar
    # Collar (white - inverted)
    draw.arc([x+5, y+23, x+23, y+29], start=0, end=180, outline=fill_color, width=2)
    # Cape body
    draw.arc([x+3, y+25, x+25, y+35], start=0, end=180, fill=fill_color, width=2)
    
    # Bow tie (white - inverted)
    draw.polygon([(x+12, y+22), (x+13, y+23), (x+14, y+22), (x+13, y+21)], outline=fill_color, width=1)
    
    # Ground line
    draw.line([x, y+35, x+28, y+35], fill=fill_color, width=1)

def get_uptime_str():
    """Get formatted uptime string"""
    delta = datetime.now() - start_time
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    return f"{delta.days}d {hours:02d}h {minutes:02d}m"

def update_display():
    """Update E-paper display with VAMPIGOTCHI style layout"""
    if epd is None:
        return
    
    try:
        mode, ip = detect_mode()
        global current_mode, current_ip, display_update_count, hunger, blood, level, exp, exp_to_next, money, player_level, activity_messages, coffin_status
        
        current_mode = mode
        current_ip = ip
        
        # Update stats based on activity
        if attacking:
            hunger = max(0, hunger - 5)
            blood = min(100, blood + 2)
            if len(activity_messages) == 0 or activity_messages[-1] != "> Attacking target!":
                activity_messages.append("> Attacking target!")
        elif scan_status == "Scanning...":
            hunger = max(0, hunger - 2)
            if len(activity_messages) == 0 or activity_messages[-1] != "> Scanning...":
                activity_messages.append("> Scanning...")
        elif len(targets) > 0:
            if len(activity_messages) == 0 or "Feeling" not in activity_messages[-1]:
                activity_messages.append("> Feeling spooky!")
        
        # Keep only last 3 messages
        if len(activity_messages) > 3:
            activity_messages = activity_messages[-3:]
        
        # Update coffin status
        if not attacking and scan_status != "Scanning...":
            coffin_status = "SLEEPING"
        else:
            coffin_status = "AWAKE"
        
        display_mode = config.get("display_mode", "black")
        bg_color = 0 if display_mode == "white" else 255
        fg_color = 255 if display_mode == "white" else 0
        
        # Create image (250x122 for V4)
        image = Image.new('1', (epd.height, epd.width), bg_color)
        draw = ImageDraw.Draw(image)
        
        # ========== TOP STATUS BAR ==========
        y_top = 0
        # Battery icon (left)
        draw_battery_icon(draw, 2, y_top+1, fg_color)
        
        # Wi-Fi icon and text
        draw_wifi_icon(draw, 18, y_top+1, fg_color)
        draw.text((26, y_top), "wi", font=font_small, fill=fg_color)
        
        # Raspberry Pi logo (simplified - just text)
        draw.text((50, y_top), "RPi", font=font_small, fill=fg_color)
        
        # Time (right)
        current_time = datetime.now().strftime("%H:%M")
        draw.text((epd.width - 35, y_top), current_time, font=font_small, fill=fg_color)
        
        # ========== TITLE SECTION ==========
        y_title = 10
        draw.text((5, y_title), "VAMPIGOTCHI", font=font_large, fill=fg_color)
        # Bat icon next to title
        draw_bat_icon(draw, 100, y_title+2, fg_color)
        
        # ========== CHARACTER STATS ==========
        y_stats = 22
        # HUNGER with coffin icon
        hunger_pct = int((hunger / 1000) * 100)
        draw_coffin_icon(draw, 5, y_stats, fg_color)
        draw.text((15, y_stats), f"HUNGER: [{hunger_pct}%]/1000", font=font_small, fill=fg_color)
        
        y_stats += 10
        # BLOOD with potion icon
        draw_potion_icon(draw, 5, y_stats, fg_color)
        draw.text((15, y_stats), f"BLOOD: [{blood}%]", font=font_small, fill=fg_color)
        
        y_stats += 10
        # LEVEL and EXP
        draw.text((5, y_stats), f"LEVEL: {level} / EXP: {exp}/{exp_to_next}", font=font_small, fill=fg_color)
        
        # ========== STATUS/ACTIVITY LOG ==========
        y_status = 48
        coffin_text = "SLEEPING" if coffin_status == "SLEEPING" else "AWAKE"
        draw.text((5, y_status), f"COFFIN: {coffin_text}", font=font_small, fill=fg_color)
        
        y_status += 9
        # Activity messages (max 2 to fit)
        for i, msg in enumerate(activity_messages[-2:]):
            if y_status + i*8 < 70:  # Make sure it fits
                draw.text((5, y_status + i*8), msg, font=font_small, fill=fg_color)
        
        # ========== ACTION BAR (icons) - simplified ==========
        y_actions = 68
        icon_spacing = 20
        # Garlic icon (simplified - circle)
        draw.ellipse([5, y_actions, 5+6, y_actions+6], outline=fg_color, width=1)
        # Hammer icon (simplified)
        draw.rectangle([5+icon_spacing, y_actions+1, 5+icon_spacing+4, y_actions+5], fill=fg_color)
        draw.rectangle([5+icon_spacing+4, y_actions, 5+icon_spacing+7, y_actions+2], fill=fg_color)
        # Diamond "Blep"
        draw.polygon([(5+icon_spacing*2+3, y_actions), (5+icon_spacing*2+6, y_actions+3), 
                     (5+icon_spacing*2+3, y_actions+6), (5+icon_spacing*2, y_actions+3)], fill=fg_color)
        # Moon "Step"
        draw.arc([5+icon_spacing*3, y_actions, 5+icon_spacing*3+6, y_actions+6], start=45, end=225, fill=fg_color, width=1)
        # Scroll icon
        draw.rectangle([5+icon_spacing*4, y_actions, 5+icon_spacing*4+5, y_actions+6], outline=fg_color, width=1)
        draw.line([5+icon_spacing*4+1, y_actions+1, 5+icon_spacing*4+4, y_actions+1], fill=fg_color)
        draw.line([5+icon_spacing*4+1, y_actions+3, 5+icon_spacing*4+4, y_actions+3], fill=fg_color)
        
        # ========== MAIN CHARACTER AND FINANCIALS ==========
        # Money and Player Level (left side)
        y_char = 78
        draw.text((5, y_char), f"${money}", font=font, fill=fg_color)
        draw.text((5, y_char+10), f"LVL", font=font_small, fill=fg_color)
        draw.text((5, y_char+18), f"{player_level}", font=font, fill=fg_color)
        
        # Vampire character (center-right)
        char_x = 50
        char_y = 75
        draw_vampire_chibi(draw, char_x, char_y, mood, fg_color)
        
        # Display update optimization
        display_update_count += 1
        refresh_interval = config.get("display_full_refresh_interval", 30)
        
        # Full refresh on first update or every N updates
        if display_update_count == 1 or display_update_count % refresh_interval == 0:
            epd.init()
            epd.display(epd.getbuffer(image))
        else:
            # Partial update for faster refresh
            try:
                epd.init(epd.PART_UPDATE)
                epd.displayPartial(epd.getbuffer(image))
            except (AttributeError, Exception):
                # Fallback to full update
                epd.init()
                epd.display(epd.getbuffer(image))
    
    except Exception as e:
        logger.error(f"Error updating display: {e}")

def run_display_loop():
    """Run display update loop in background thread"""
    init_display_safe()
    time.sleep(2)
    
    last_activity = datetime.now()
    last_auto_message = datetime.now()
    
    while True:
        # Update mood to "bored" if no activity for 30 seconds
        global mood, hunger, activity_messages
        import random
        
        # Auto-decrease hunger over time
        if (datetime.now() - last_activity).total_seconds() > 60:
            hunger = max(0, hunger - 1)
            last_activity = datetime.now()
        
        # Add automatic activity messages
        if (datetime.now() - last_auto_message).total_seconds() > 120:  # Every 2 minutes
            messages = [
                "> Slept well in.",
                "> Learned new trick!",
                "> Feeling spooky!",
                "> Ready to hunt!",
                "> Resting in coffin."
            ]
            activity_messages.append(random.choice(messages))
            if len(activity_messages) > 5:
                activity_messages = activity_messages[-5:]
            last_auto_message = datetime.now()
        
        if not attacking and scan_status != "Scanning...":
            time_since_activity = (datetime.now() - last_activity).total_seconds()
            if time_since_activity > 30 and mood not in ["sad", "angry"]:
                mood = "bored"
        else:
            last_activity = datetime.now()
        
        update_display()
        time.sleep(3)

# ================= WEB SERVER =================

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VampGotchi</title>
    <style>
        body { font-family: sans-serif; background: #222; color: #fff; text-align: center; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }
        .card { background: #333; padding: 20px; border-radius: 10px; }
        h1, h2 { color: #00d4ff; }
        button { padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; margin: 5px; }
        .btn-blue { background: #00d4ff; color: #000; }
        .btn-red { background: #ff6b6b; color: #fff; }
        .btn-green { background: #4cd964; color: #000; }
        input, select { padding: 10px; width: 100%; margin: 10px 0; background: #444; border: 1px solid #555; color: #fff; box-sizing: border-box; }
        ul { list-style: none; padding: 0; text-align: left; }
        li { background: #444; margin: 5px 0; padding: 10px; border-radius: 5px; font-family: monospace; cursor: pointer; }
        .status-badge { display: inline-block; padding: 5px 10px; border-radius: 5px; font-weight: bold; }
        .idle { background: #4cd964; color: #000; }
        .scanning { background: #ffd43b; color: #000; }
        .attacking { background: #ff6b6b; color: #fff; }
        .debug-section { margin-top: 20px; padding: 10px; background: #2a2a2a; border-radius: 5px; }
        .debug-toggle { cursor: pointer; color: #00d4ff; text-decoration: underline; }
    </style>
    <script>
        setInterval(function() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status-badge').className = 'status-badge ' + data.status_class;
                    document.getElementById('status-text').textContent = data.status_text;
                    document.getElementById('target-count').textContent = data.count;
                    document.getElementById('stat-scans').textContent = data.stats.total_scans;
                    document.getElementById('stat-attacks').textContent = data.stats.total_attacks;
                    document.getElementById('stat-mood').textContent = data.stats.mood;
                    const list = document.getElementById('target-list');
                    const select = document.getElementById('target-select');
                    document.getElementById('scan-btn').disabled = data.scanning;
                    document.getElementById('attack-btn').disabled = !data.selected_target || data.attacking;
                    document.getElementById('stop-btn').disabled = !data.attacking;
                    list.innerHTML = '';
                    select.innerHTML = '<option value="">Select...</option>';
                    data.targets_info.forEach(target => {
                        const li = document.createElement('li');
                        li.innerHTML = `<strong>${target.name || 'Unknown'}</strong><br><small>${target.mac}</small>${target.rssi ? ' <span style="color: #00d4ff;">(' + target.rssi + ' dBm)</span>' : ''}`;
                        li.onclick = function() { selectTarget(target.mac); };
                        list.appendChild(li);
                        const option = document.createElement('option');
                        option.value = target.mac;
                        option.textContent = `${target.name || 'Unknown'} - ${target.mac}`;
                        select.appendChild(option);
                    });
                });
        }, 2000);
        
        function selectTarget(mac) {
            document.getElementById('target-select').value = mac;
        }
        
        function toggleDebug() {
            const debugDiv = document.getElementById('debug-section');
            debugDiv.style.display = debugDiv.style.display === 'none' ? 'block' : 'none';
        }
    </script>
</head>
<body>
    <div class="container">
        <h1>🧛 VampGotchi</h1>
        <div class="card">
            <h2>Network Configuration</h2>
            <p><strong>Mode:</strong> {{ network_mode }} ({{ network_ip }})</p>
            <h3>AP Mode (Hotspot)</h3>
            <form action="/set_ap" method="POST"><button type="submit" class="btn-blue">Activate AP ({{ ap_ssid }})</button></form>
            <h3>Client Mode (Wi-Fi)</h3>
            <form action="/set_client" method="POST">
                <input type="text" name="ssid" placeholder="Network Name" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit" class="btn-blue">Connect</button>
            </form>
        </div>
        <div class="card">
            <h2>Display Settings</h2>
            <form action="/api/config" method="POST">
                <label>Display Mode:</label>
                <select name="display_mode">
                    <option value="black" {{ 'selected' if display_mode == 'black' else '' }}>Black Background (Vampire Theme)</option>
                    <option value="white" {{ 'selected' if display_mode == 'white' else '' }}>White Background</option>
                </select>
                <button type="submit" class="btn-blue">Save Display Settings</button>
            </form>
        </div>
        <div class="card">
            <h2>BLE Control</h2>
            <p>Status: <span id="status-badge" class="status-badge idle">Idle</span></p>
            <p id="status-text">Waiting...</p>
            <button id="scan-btn" onclick="location.href='/scan'" class="btn-green">SCAN BLE</button>
            <hr style="border-color: #555;">
            <p>Targets Found: <span id="target-count">0</span></p>
            <p style="font-size: 12px; color: #888;">Scans: <span id="stat-scans">0</span> | Attacks: <span id="stat-attacks">0</span> | Mood: <span id="stat-mood">bored</span></p>
            <div style="display: flex; gap: 10px;"><select id="target-select"></select></div>
            <div style="display: flex; gap: 10px;">
                <button id="attack-btn" onclick="startAttack()" class="btn-red" disabled>ATTACK</button>
                <button id="stop-btn" onclick="stopAttack()" class="btn-blue" disabled>STOP</button>
            </div>
            <ul id="target-list" style="margin-top: 10px; max-height: 150px; overflow-y: auto;"></ul>
            <p class="debug-toggle" onclick="toggleDebug()">Debug Information</p>
            <div id="debug-section" style="display: none;" class="debug-section">
                <h3>Debug Info</h3>
                <p><a href="/api/debug/scan">View Last Scan Output</a></p>
                <p><a href="/api/debug/bluetooth">View Bluetooth Status</a></p>
            </div>
        </div>
    </div>
    <script>
        function startAttack() {
            var mac = document.getElementById('target-select').value;
            if(!mac) return alert('Select a target!');
            fetch('/attack', { method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: 'mac=' + mac });
        }
        function stopAttack() {
            fetch('/stop', { method: 'POST' });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Main page"""
    mode, ip = detect_mode()
    display_mode = config.get("display_mode", "black")
    ap_ssid = config.get("ap_ssid", "VampGotchi-AP")
    return render_template_string(HTML_TEMPLATE, network_mode=mode, network_ip=ip, ap_ssid=ap_ssid, display_mode=display_mode)

@app.route('/api/status')
def api_status():
    """API endpoint for status"""
    global targets, attacking, scan_status, selected_target, total_scans, total_attacks, mood
    
    status_text = "Idle"
    status_class = "idle"
    if attacking:
        status_text = f"Attacking {selected_target}"
        status_class = "attacking"
    elif scan_status == "Scanning...":
        status_text = "Scanning..."
        status_class = "scanning"
    
    targets_with_info = []
    for mac in targets:
        info = targets_info.get(mac, {})
        targets_with_info.append({
            'mac': mac,
            'name': info.get('name', 'Unknown'),
            'rssi': info.get('rssi', 0)
        })
    
    return jsonify({
        'targets': targets,
        'targets_info': targets_with_info,
        'attacking': attacking,
        'scanning': scan_status == "Scanning...",
        'selected_target': selected_target,
        'status_text': status_text,
        'status_class': status_class,
        'count': len(targets),
        'stats': {
            'total_scans': total_scans,
            'total_attacks': total_attacks,
            'mood': mood,
            'uptime': get_uptime_str()
        }
    })

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """API endpoint for configuration"""
    global config
    
    if request.method == 'POST':
        if 'display_mode' in request.form:
            config['display_mode'] = request.form['display_mode']
            save_config()
            update_display()
        
        return index()
    else:
        return jsonify(config)

@app.route('/api/debug/scan')
def api_debug_scan():
    """API endpoint for debug scan output"""
    global last_scan_output
    return f"<pre>{last_scan_output}</pre>" if last_scan_output else "No scan output available"

@app.route('/api/debug/bluetooth')
def api_debug_bluetooth():
    """API endpoint for Bluetooth status"""
    try:
        result = subprocess.run(['hciconfig'], capture_output=True, text=True, timeout=5)
        return f"<pre>{result.stdout}</pre>"
    except Exception as e:
        return f"<pre>Error: {e}</pre>"

@app.route('/set_ap', methods=['POST'])
def set_ap():
    """Switch to AP mode"""
    threading.Thread(target=restart_services_ap).start()
    time.sleep(1)
    return index()

@app.route('/set_client', methods=['POST'])
def set_client():
    """Switch to client mode"""
    ssid = request.form['ssid']
    password = request.form['password']
    threading.Thread(target=restart_services_client, args=(ssid, password)).start()
    time.sleep(1)
    return index()

@app.route('/scan')
def scan():
    """Start BLE scan"""
    threading.Thread(target=run_bleeding_scan).start()
    return index()

@app.route('/attack', methods=['POST'])
def attack():
    """Start attack on target"""
    global attack_thread, selected_target
    mac = request.form['mac']
    selected_target = mac
    stop_bleeding_attack()
    attack_thread = threading.Thread(target=run_bleeding_attack_thread, args=(mac,))
    attack_thread.start()
    return index()

@app.route('/stop', methods=['POST'])
def stop():
    """Stop attack"""
    stop_bleeding_attack()
    return index()

# ================= MAIN =================

def run_auto_scan():
    """Run automatic scans if configured"""
    while True:
        scan_interval = config.get("scan_interval", 60)
        if scan_interval > 0 and not attacking and scan_status != "Scanning...":
            logger.info(f"Running automatic scan (interval: {scan_interval}s)")
            run_bleeding_scan()
        time.sleep(scan_interval)

if __name__ == '__main__':
    # Start display in background thread
    display_thread = threading.Thread(target=run_display_loop)
    display_thread.daemon = True
    display_thread.start()
    
    # Start auto-scan if configured
    scan_interval = config.get("scan_interval", 0)
    if scan_interval > 0:
        logger.info(f"Auto-scan enabled: interval={scan_interval}s")
        auto_scan_thread = threading.Thread(target=run_auto_scan)
        auto_scan_thread.daemon = True
        auto_scan_thread.start()
    
    # Wait for display to initialize
    time.sleep(3)
    
    # Start Flask server
    ip = get_ip_address()
    print("=" * 50)
    print("🧛 VampGotchi - Bluetooth Monitoring Device")
    print(f"📡 Connect at: http://{ip}")
    print(f"🎭 Initial mood: {mood}")
    print("=" * 50)
    
    try:
        app.run(host='0.0.0.0', port=80, debug=False)
    except PermissionError:
        print("ERROR: Port 80 requires root privileges. Run with sudo.")
        sys.exit(1)

