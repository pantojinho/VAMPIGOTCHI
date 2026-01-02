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
    
    scan_status = "Scanning..."
    mood = "excited"
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
        else:
            mood = "sad"
        
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
            else:
                mood = "sad"
            
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
    
    attacking = True
    mood = "angry"
    total_attacks += 1
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

def draw_vampire_sprite(draw, x, y, mood_state):
    """Draw vampire pixel art sprite based on mood"""
    # Head (circle)
    draw.ellipse([x, y, x+30, y+30], outline=0, width=1)
    
    # Bat ears (vampire characteristic)
    draw.polygon([(x+5, y+2), (x+8, y+8), (x+5, y+6)], fill=0)  # Left ear
    draw.polygon([(x+25, y+2), (x+22, y+8), (x+25, y+6)], fill=0)  # Right ear
    
    # Collar/cape (vampire aesthetic)
    draw.arc([x+5, y+28, x+25, y+35], start=0, end=180, fill=0, width=2)
    
    # Eyes and mouth based on mood
    if mood_state == "happy":
        # Happy eyes
        draw.ellipse([x+8, y+10, x+12, y+14], fill=0)
        draw.ellipse([x+18, y+10, x+22, y+14], fill=0)
        # Smile with fangs
        draw.arc([x+8, y+15, x+22, y+25], start=0, end=180, fill=0, width=2)
        # Fangs
        draw.rectangle([x+11, y+20, x+12, y+23], fill=0)
        draw.rectangle([x+18, y+20, x+19, y+23], fill=0)
        
    elif mood_state == "excited":
        # Big excited eyes
        draw.ellipse([x+7, y+9, x+13, y+15], fill=0)
        draw.ellipse([x+17, y+9, x+23, y+15], fill=0)
        # Big open mouth with prominent fangs
        draw.arc([x+6, y+14, x+24, y+28], start=0, end=180, fill=0, width=2)
        # Big fangs
        draw.rectangle([x+10, y+18, x+12, y+24], fill=0)
        draw.rectangle([x+18, y+18, x+20, y+24], fill=0)
        
    elif mood_state == "angry":
        # Angry slanted eyes
        draw.line([x+8, y+12, x+12, y+10], fill=0, width=2)
        draw.line([x+18, y+10, x+22, y+12], fill=0, width=2)
        # Frown with bared fangs
        draw.arc([x+10, y+20, x+20, y+28], start=180, end=360, fill=0, width=2)
        # Fangs visible
        draw.rectangle([x+11, y+23, x+13, y+26], fill=0)
        draw.rectangle([x+17, y+23, x+19, y+26], fill=0)
        
    elif mood_state == "sad":
        # Sad eyes
        draw.ellipse([x+8, y+10, x+12, y+14], fill=0)
        draw.ellipse([x+18, y+10, x+22, y+14], fill=0)
        # Sad frown, no fangs visible
        draw.arc([x+8, y+20, x+22, y+28], start=180, end=360, fill=0, width=2)
        
    else:  # bored
        # Neutral eyes
        draw.ellipse([x+8, y+10, x+12, y+14], fill=0)
        draw.ellipse([x+18, y+10, x+22, y+14], fill=0)
        # Straight line (neutral)
        draw.line([x+10, y+22, x+20, y+22], fill=0, width=2)

def get_uptime_str():
    """Get formatted uptime string"""
    delta = datetime.now() - start_time
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    return f"{delta.days}d {hours:02d}h {minutes:02d}m"

def update_display():
    """Update E-paper display"""
    if epd is None:
        return
    
    try:
        mode, ip = detect_mode()
        global current_mode, current_ip, display_update_count
        current_mode = mode
        current_ip = ip
        
        display_mode = config.get("display_mode", "black")
        bg_color = 0 if display_mode == "white" else 255
        fg_color = 255 if display_mode == "white" else 0
        
        # Create image
        image = Image.new('1', (epd.height, epd.width), bg_color)
        draw = ImageDraw.Draw(image)
        
        # Header
        draw.text((5, 2), "VampGotchi", font=font_large, fill=fg_color)
        
        # Vampire sprite
        draw_vampire_sprite(draw, 5, 25, mood)
        
        # Status info (right of sprite)
        x_info = 40
        y_info = 25
        
        status_text = "IDLE"
        if attacking:
            status_text = "ATTACK!"
        elif scan_status == "Scanning...":
            status_text = "SCAN..."
        elif scan_status == "Error":
            status_text = "ERROR"
        
        draw.text((x_info, y_info), status_text, font=font, fill=fg_color)
        y_info += 15
        
        # Network mode
        draw.text((x_info, y_info), f"{mode}", font=font_small, fill=fg_color)
        y_info += 12
        
        # IP address
        ip_short = ip[:12] if len(ip) > 12 else ip
        draw.text((x_info, y_info), ip_short, font=font_small, fill=fg_color)
        
        # Statistics
        y_stats = 60
        draw.text((5, y_stats), f"Targets: {len(targets)}", font=font_small, fill=fg_color)
        y_stats += 12
        draw.text((5, y_stats), f"Scans: {total_scans}", font=font_small, fill=fg_color)
        y_stats += 12
        draw.text((5, y_stats), f"Attacks: {total_attacks}", font=font_small, fill=fg_color)
        
        # Target info (if selected or attacking)
        y_target = 100
        if attacking and selected_target:
            target_info = targets_info.get(selected_target, {})
            target_name = target_info.get('name', 'Unknown')[:15]
            draw.text((5, y_target), f">> {target_name}", font=font_small, fill=fg_color)
            y_target += 12
            mac_short = selected_target[:17] if len(selected_target) > 17 else selected_target
            draw.text((5, y_target), mac_short, font=font_small, fill=fg_color)
        elif selected_target:
            target_info = targets_info.get(selected_target, {})
            target_name = target_info.get('name', 'Unknown')[:15]
            draw.text((5, y_target), f"Sel: {target_name}", font=font_small, fill=fg_color)
            y_target += 12
            rssi = target_info.get('rssi', 0)
            if rssi != 0:
                draw.text((5, y_target), f"RSSI: {rssi} dBm", font=font_small, fill=fg_color)
        
        # Footer
        y_footer = 115
        uptime = get_uptime_str()
        draw.line([(0, y_footer-2), (epd.width, y_footer-2)], fill=fg_color)
        draw.text((5, y_footer), f"Uptime: {uptime}", font=font_small, fill=fg_color)
        
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
    
    while True:
        # Update mood to "bored" if no activity for 30 seconds
        global mood
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

if __name__ == '__main__':
    # Start display in background thread
    display_thread = threading.Thread(target=run_display_loop)
    display_thread.daemon = True
    display_thread.start()
    
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

