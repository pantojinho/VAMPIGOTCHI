# 🧛 VampGotchi

**A Tamagotchi-like Bluetooth monitor with a vampire's bite**

VampGotchi is a portable BLE (Bluetooth Low Energy) monitoring device that watches over your Bluetooth network. Feed it devices, watch its mood change, and let it jam unwanted connections when needed. Inspired by Pwnagotchi, but with a spooky vampire twist!

---

## 🦇 Features

- 🧛 **Vampire Character**: Pixel art vampire that reacts to network activity with different moods
- 📡 **BLE Monitoring**: Passive scanning of nearby Bluetooth devices
- 🦇 **Active Jamming**: Jam unwanted connections when needed (educational/research purposes only)
- 📺 **E-Paper Display**: Low-power display showing vampire status, stats, and network information
- 🌐 **Web Interface**: Configure and control via browser on the same network
- 🎭 **Mood System**: Character expresses different moods (bored, happy, excited, sad, angry) based on activity

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

### 2. Clone and Install

```bash
# Clone the repository
git clone https://github.com/yourusername/VampGotchi.git
cd VampGotchi

# Make install script executable (if needed)
chmod +x install.sh

# Run the automated installation script
sudo ./install.sh
```

That's it! The installation script will:
- Install all system dependencies
- Install Python packages
- Clone and configure BLEeding
- Set up configuration files
- Configure Bluetooth

### 3. Run VampGotchi

```bash
sudo python3 vampgotchi.py
```

Or enable the systemd service for auto-start on boot:

```bash
sudo systemctl enable vampgotchi.service
sudo systemctl start vampgotchi.service
```

### 4. Access Web Interface

Connect to the device via Wi-Fi (either AP mode or client mode) and open:
```
http://192.168.4.1  (AP mode)
http://<device-ip>  (Client mode)
```

---

## ⚙️ Configuration

Configuration is stored in `config.yml` (auto-created from `default_config.yml` on first run).

### Display Settings

- **display_mode**: `"white"` or `"black"` (background preference)
- **display_full_refresh_interval**: Number of partial updates before full refresh (default: 30)

Change display mode via the web interface or edit `config.yml` directly.

### Network Settings

- **network_mode**: `"AP"` or `"CLIENT"`
- **ap_ssid**: Access point SSID (default: "VampGotchi-AP")
- **ap_pass**: Access point password
- **ap_ip**: Access point IP address (default: "192.168.4.1")

Switch between AP and client mode via the web interface.

### BLEeding Settings

- **bleeding_path**: Path to BLEeding installation (default: "/root/BLEeding")
- **attack_timeout**: Default attack duration in seconds (default: 10)
- **scan_interval**: Seconds between automatic scans (0 = disabled)

---

## 🎮 Usage

### E-Paper Display

The E-paper display shows:
- **Vampire character** with current mood
- **Status**: IDLE, SCAN..., ATTACK!, or ERROR
- **Network mode** and IP address
- **Statistics**: Targets found, total scans, total attacks
- **Selected target** information (if any)
- **Uptime**

### Web Interface

Access the web interface to:
- Switch between AP and client Wi-Fi modes
- Configure display settings (black/white background)
- Start BLE scans
- View discovered devices
- Select and attack targets
- View debug information

### Moods

The vampire character has different moods:
- **Bored**: No activity detected
- **Happy**: Devices found
- **Excited**: Scanning in progress
- **Sad**: No devices found or error occurred
- **Angry**: Attacking a target

---

## 🔧 Troubleshooting

### BLE Scanning Shows 0 Devices

1. **Check permissions**: Run with `sudo` (Bluetooth requires root on Linux)
2. **Verify Bluetooth**: Check if `hci0` is up:
   ```bash
   sudo hciconfig hci0 up
   ```
3. **Test manually**: Try `sudo hcitool lescan` to verify hardware
4. **Check BLEeding**: Verify BLEeding is installed at the configured path
5. **View debug info**: Use the debug section in the web interface

### Display Shows Black/White Alternating

This is normal for E-paper displays. The display uses partial updates for speed, but needs full refreshes periodically to prevent ghosting. You can adjust the refresh interval in `config.yml`.

### Web Interface Not Accessible

1. Check the device IP address
2. Verify network mode (AP or client)
3. Check firewall settings
4. Ensure Flask is running (check process: `ps aux | grep vampgotchi`)

### Installation Issues

If the installation script fails:
1. Check internet connection
2. Update system: `sudo apt update && sudo apt upgrade`
3. Run installation script again (it's idempotent)

---

## 🛠️ Development

### Project Structure

```
VampGotchi/
├── vampgotchi.py          # Main application
├── config.yml             # User configuration (gitignored)
├── default_config.yml     # Default configuration template
├── requirements.txt       # Python dependencies
├── install.sh             # Automated installation script
├── vampgotchi.service     # Systemd service file
├── README.md              # This file
├── CONTRIBUTING.md        # Contribution guidelines
├── LICENSE                # License file
└── .gitignore             # Git ignore rules
```

### Running from Source

1. Install dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```

2. Install BLEeding:
   ```bash
   git clone https://github.com/sammwyy/BLEeding.git /root/BLEeding
   cd /root/BLEeding
   pip3 install -r requirements.txt
   ```

3. Run:
   ```bash
   sudo python3 vampgotchi.py
   ```

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on:
- Code style guidelines
- How to submit issues
- How to submit pull requests
- Development setup

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

---

## 📸 Screenshots

*Add screenshots of your device here!*

---

**Made with 🧛 by the VampGotchi community**
