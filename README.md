# 🧛 VampiGotchi - BLEeding Ultimate v4

**A standalone Tamagotchi-like Bluetooth monitor with a vampire's bite**

VampiGotchi is a portable BLE (Bluetooth Low Energy) monitoring device that watches over your Bluetooth network. Feed it devices, watch its mood change, and let it jam unwanted connections when needed. Inspired by Pwnagotchi, but with a spooky vampire twist!

**✨ NEW IN v4.0: Standalone single-file application!** Everything you need in one `Scrpit.py` file.

---

## 🦇 Features

- 🧛 **Vampire Character**: Beautiful pixel art vampire that reacts to network activity with different moods
- 📡 **BLE Monitoring**: Passive scanning of nearby Bluetooth devices
- 🦇 **Active Jamming**: Jam unwanted connections when needed (educational/research purposes only)
- 📺 **E-Paper Display**: Low-power 2.13" display showing vampire status, stats, and network information
- 🌐 **Modern Web Interface**: Beautiful, customizable web interface accessible from any device
- 🎭 **Mood System**: Character expresses different moods (bored, happy, excited, sad, angry) based on activity
- 🐛 **Debug Mode**: Comprehensive debug information in both terminal and web interface
- 🎨 **Theme Customization**: Customize colors directly from the web interface
- 📱 **Full-Screen Layout**: Optimized vertical layout using entire E-Paper screen

---

## 📦 Hardware Requirements

- **Raspberry Pi Zero W** (with Wi-Fi and Bluetooth)
- **Waveshare 2.13" E-Paper Display HAT (V4)** (250x122 pixels)
- **MicroSD Card** (64GB recommended, 8GB minimum)
- Optional: 3D printed case, battery pack for portable use

---

## 🚀 Quick Start

### 1. Flash Raspberry Pi OS

Flash **Raspberry Pi OS (Legacy)** to your SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/).

### 2. Install Dependencies

**For Raspberry Pi OS (Debian 12+) with externally-managed Python:**

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y python3-pip python3-pil python3-numpy git

# Install Python packages (use --break-system-packages flag for Raspberry Pi OS)
sudo pip3 install --break-system-packages Flask>=2.3.0 Pillow>=9.5.0 waveshare-epd>=2.0.0

# Or install from requirements.txt
sudo pip3 install --break-system-packages -r requirements.txt

# Install BLEeding
git clone https://github.com/sammwyy/BLEeding.git ~/bleeding
cd ~/bleeding
sudo pip3 install --break-system-packages -r requirements.txt
cd ~
```

**Note:** The `--break-system-packages` flag is required for Raspberry Pi OS Bookworm (Debian 12+) which uses externally-managed Python environments. This is safe to use on Raspberry Pi for system-wide installations.

### 3. Download and Run

```bash
# Download the standalone script
wget https://raw.githubusercontent.com/pantojinho/VAMPIGOTCHI/main/Scrpit.py

# Make executable
chmod +x Scrpit.py

# Run (requires sudo for Bluetooth access)
sudo python3 Scrpit.py
```

**That's it!** The script is completely standalone - no configuration files needed (optional).

### 4. Access Web Interface

The script will display the IP address in the terminal. Connect to:
```
http://192.168.4.1  (AP mode - default)
http://<device-ip>  (Client mode - if connected to Wi-Fi)
```

---

## 📁 Project Structure (Simplified!)

```
VampiGotchi/
├── Scrpit.py          # ⭐ Main standalone application (everything in one file!)
├── requirements.txt   # Python dependencies
├── install.sh         # Optional automated installation script
├── README.md          # This file
├── CONTRIBUTING.md    # Contribution guidelines
└── LICENSE            # MIT License
```

**All functionality is in `Scrpit.py` - no other Python files needed!**

---

## ⚙️ Configuration

The script uses hardcoded defaults that work out of the box. You can modify constants at the top of `Scrpit.py`:

```python
# Network Config
AP_SSID = "BLEeding-Pi"
AP_PASS = "12345678"
AP_IP = "192.168.4.1"

# BLEeding
BLEEDING_PATH = "/root/bleeding"  # Auto-detected if not found here
ATTACK_TIMEOUT = 10
```

The script automatically searches for BLEeding in common locations:
- `/root/bleeding`
- `/root/BLEeding`
- `/opt/BLEeding`
- `/home/pi/bleeding`
- And more...

---

## 🎮 Usage

### E-Paper Display

The E-paper display shows:
- **Vampire character** with current mood (bottom center)
- **Status**: IDLE, SCAN..., ATTACK!, or ERROR
- **Network mode** and IP address
- **Statistics**: Targets found, total scans, total attacks
- **Selected target** information (if any)
- **Uptime**

Display uses white background by default for better visibility.

### Web Interface

Access the web interface to:
- **Switch between AP and client Wi-Fi modes**
- **Customize theme colors** (background, cards, text)
- **Start BLE scans** with real-time feedback
- **View discovered devices** with MAC addresses and RSSI
- **Select and attack targets**
- **View comprehensive debug information** including:
  - BLEeding path detection
  - Command execution details
  - Full output from scans
  - Error messages and tracebacks

### Moods

The vampire character has different moods:
- **Bored** 😴: No activity detected
- **Happy** 😊: Devices found
- **Excited** 🤩: Scanning in progress
- **Sad** 😢: No devices found or error occurred
- **Angry** 😠: Attacking a target

---

## 🔧 Troubleshooting

### BLE Scanning Shows 0 Devices

1. **Check permissions**: Run with `sudo` (Bluetooth requires root on Linux)
2. **Verify Bluetooth**: Check if `hci0` is up:
   ```bash
   sudo hciconfig hci0 up
   ```
3. **Test manually**: Try `sudo hcitool lescan` to verify hardware
4. **Check BLEeding**: View debug section in web interface to see if BLEeding was found
5. **Use debug info**: The web interface now shows detailed debug information including:
   - Where BLEeding was found
   - Exact commands executed
   - Full output from scans
   - Any errors encountered

### Display Shows Flashing

The display is optimized to avoid flashing:
- Uses partial updates for speed
- Full refresh every 30 updates to prevent ghosting
- White background by default

If flashing persists, check the `update_display()` function optimization settings.

### Web Interface Not Accessible

1. Check the IP address shown in terminal output
2. Verify network mode (AP or client)
3. Ensure Flask is running: `ps aux | grep Scrpit`
4. Check firewall: `sudo ufw status`

### BLEeding Not Found

The script automatically searches multiple paths. Check the debug section in the web interface to see:
- All paths that were tested
- Where BLEeding was eventually found
- If BLEeding wasn't found, it will show all attempted paths

Install BLEeding manually if needed:
```bash
git clone https://github.com/sammwyy/BLEeding.git ~/bleeding
cd ~/bleeding
sudo pip3 install --break-system-packages -r requirements.txt
```

---

## 🛠️ Development

### Running from Source

1. Just download `Scrpit.py` - it's standalone!

2. Install dependencies:
   ```bash
   sudo pip3 install flask pillow waveshare-epd
   ```

3. Install BLEeding:
   ```bash
   git clone https://github.com/sammwyy/BLEeding.git ~/bleeding
   cd ~/bleeding
   sudo pip3 install -r requirements.txt
   ```

4. Run:
   ```bash
   sudo python3 Scrpit.py
   ```

### Making Changes

Edit `Scrpit.py` directly - it's all in one file! The script is organized with clear sections:
- Configuration constants (top)
- Display functions
- Network functions
- BLEeding functions
- Web interface (HTML embedded)
- Flask routes
- Main execution

---

## 📸 Screenshots

![VampiGotchi Display](Pixel%20Arte%20IA.png)

*E-Paper display showing the vampire character with full-screen vertical layout*

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details.

Since this is now a standalone file, contributions should:
- Maintain the single-file structure
- Keep code organized with clear sections
- Add comprehensive debug information
- Update this README if adding features

---

## ⚠️ Legal Disclaimer

This tool is for **educational and research purposes only**. The jamming functionality can interfere with Bluetooth communications. Use responsibly and only on devices you own or have explicit permission to test. The authors are not responsible for any misuse of this tool.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Credits

- Inspired by [Pwnagotchi](https://github.com/evilsocket/pwnagotchi)
- Uses [BLEeding](https://github.com/sammwyy/BLEeding) for Bluetooth operations
- E-paper display driver: [Waveshare](https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT)
- Pixel art vampire character design

---

## 📝 Changelog

### v4.0 Ultimate (Standalone)
- ✅ **Single-file standalone application** - everything in `Scrpit.py`
- ✅ Full-screen vertical layout for E-Paper display
- ✅ Modern web interface with theme customization
- ✅ Comprehensive debug information in web UI
- ✅ Automatic BLEeding path detection
- ✅ Optimized display updates (no flashing)
- ✅ White background by default
- ✅ Enhanced error handling and logging

### v3.0
- Multi-file structure
- YAML configuration support
- Enhanced vampire character display

### v2.0
- Initial release
- Basic BLE scanning
- E-Paper display support

---

**Made with 🧛 by the VampiGotchi community**

*One file to rule them all!* 🦇
