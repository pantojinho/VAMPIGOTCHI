#!/usr/bin/env python3
import subprocess
import time
import threading
import socket
import os
import signal
import re
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, jsonify
from waveshare_epd import epd2in13_V4
from PIL import Image, ImageDraw, ImageFont

# ================= CONFIGURAÇÕES =================
# Network Config
AP_SSID = "BLEeding-Pi"
AP_PASS = "12345678"
AP_IP = "192.168.4.1"

# Caminhos dos arquivos de rede
HOSTAPD_CONF = "/etc/hostapd/hostapd.conf"
DNSMASQ_CONF = "/etc/dnsmasq.conf"
WPA_SUPPLICANT_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"

# BLEeding
BLEEDING_PATH = "/root/BLEeding"
ATTACK_TIMEOUT = 10

# ================= ESTADO GLOBAL =================
# Rede
current_mode = "UNKNOWN"
current_ip = "127.0.0.1"
start_time = datetime.now()

# BLEeding
targets = []
targets_info = {}  # MAC -> {name, rssi, last_seen}
selected_target = ""
attacking = False
scan_status = "Idle"
attack_thread = None

# Estatísticas
total_scans = 0
total_attacks = 0
total_targets_found = 0
mood = "bored"  # bored, happy, excited, sad, angry
display_update_count = 0  # Contador para otimização de atualização V4

# ================= E-PAPER SETUP (CORRIGIDO) =================
print("Inicializando E-Paper...")
epd = None # Inicia como None para segurança
font = None
font_small = None
font_large = None

def init_display_safe():
    global epd, font, font_small, font_large
    try:
        # Instancia o display V4 da Waveshare
        epd = epd2in13_V4.EPD()
        
        # Inicializa o display (V4 suporta FULL_UPDATE e PART_UPDATE)
        # Primeira inicialização sempre usa FULL_UPDATE
        epd.init()
        epd.Clear(0xFF)
        
        print(f"Display V4 inicializado: {epd.width}x{epd.height} pixels")
        
        # Tenta carregar fontes melhores, fallback para default
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
            print("Fontes TrueType carregadas com sucesso.")
        except Exception as font_error:
            print(f"Usando fontes padrão (TrueType não disponível: {font_error})")
            font = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_large = ImageFont.load_default()
        
        print("Display V4 Iniciado com Sucesso.")
        
    except Exception as e:
        print(f"ERRO CRÍTICO NO DISPLAY V4: {e}")
        print("O sistema continuará rodando sem display.")
        epd = None # Garante que é None para não tentar usar

def get_ip_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def detect_mode():
    global current_mode, current_ip
    ip = get_ip_address()
    if ip.startswith("192.168.4"):
        current_mode = "AP"
        current_ip = ip
    else:
        current_mode = "CLIENT"
        current_ip = ip
    return current_mode, current_ip

# ================= FUNÇÕES DE REDE =================

def write_hostapd_conf():
    config = f"""
interface=wlan0
driver=nl80211
ssid={AP_SSID}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={AP_PASS}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
rsn_pairwise=CCMP
"""
    with open(HOSTAPD_CONF, 'w') as f:
        f.write(config)

def write_dnsmasq_conf():
    config = f"""
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
"""
    with open(DNSMASQ_CONF, 'w') as f:
        f.write(config)

def write_wpa_supplicant(ssid, password):
    config = f"""
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=BR

network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
}}
"""
    with open(WPA_SUPPLICANT_CONF, 'w') as f:
        f.write(config)

def restart_services_ap():
    print(">>> Reiniciando para modo AP...")
    subprocess.run(["systemctl", "stop", "wpa_supplicant"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "stop", "dhcpcd"], stderr=subprocess.DEVNULL)
    write_hostapd_conf()
    write_dnsmasq_conf()
    with open("/etc/dhcpcd.conf", "a") as f:
        f.write(f"\ninterface wlan0\nstatic ip_address={AP_IP}/24\nnohook wpa_supplicant\n")
    subprocess.run(["systemctl", "daemon-reload"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "restart", "dhcpcd"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "unmask", "hostapd"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "restart", "hostapd"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "restart", "dnsmasq"], stderr=subprocess.DEVNULL)

def restart_services_client(ssid, password):
    print(f">>> Reiniciando para modo Cliente ({ssid})...")
    subprocess.run(["systemctl", "stop", "hostapd"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "stop", "dnsmasq"], stderr=subprocess.DEVNULL)
    write_wpa_supplicant(ssid, password)
    subprocess.run(["systemctl", "restart", "wpa_supplicant"], stderr=subprocess.DEVNULL)

# ================= FUNÇÕES BLEEDING =================

def run_bleeding_scan():
    global targets, targets_info, scan_status, total_scans, total_targets_found, mood
    scan_status = "Scanning..."
    mood = "excited"
    update_display()
    
    os.chdir(BLEEDING_PATH)
    try:
        result = subprocess.run(['python3', 'bleeding.py', 'scan', '--ble'], 
                              capture_output=True, text=True, timeout=20)
        output = result.stdout
        
        # Parse melhorado - procura por MAC addresses e informações
        lines = output.split('\n')
        found_macs = []
        new_targets = 0
        
        for line in lines:
            # Procura MAC addresses (formato XX:XX:XX:XX:XX:XX ou XX-XX-XX-XX-XX-XX)
            mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', line)
            if mac_match:
                mac_str = mac_match.group(0).replace('-', ':').upper()
                if mac_str not in found_macs:
                    found_macs.append(mac_str)
                    
                    # Tenta extrair nome do dispositivo (vários formatos possíveis)
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
                    
                    # Tenta extrair RSSI (vários formatos)
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
                        new_targets += 1
                    
                    targets_info[mac_str] = {
                        'name': device_name[:20],  # Limita tamanho
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
    except Exception as e:
        print(f"Erro Scan: {e}")
        scan_status = "Error"
        mood = "sad"
    
    update_display()

def run_bleeding_attack_thread(mac):
    global attacking, attack_thread, total_attacks, mood
    attacking = True
    mood = "angry"
    total_attacks += 1
    update_display()
    
    os.chdir(BLEEDING_PATH)
    try:
        cmd = ['python3', 'bleeding.py', 'deauth', mac, '--ble', '--timeout', str(ATTACK_TIMEOUT)]
        subprocess.run(cmd)
    except Exception as e:
        print(f"Erro Ataque: {e}")
    
    attacking = False
    mood = "happy" if len(targets) > 0 else "bored"
    update_display()

def stop_bleeding_attack():
    global attacking, attack_thread
    if attack_thread and attack_thread.is_alive():
        subprocess.run(["pkill", "-f", "bleeding.py"])
        attacking = False
        update_display()

# ================= DISPLAY MANAGER =================

def draw_face(draw, x, y, mood_state):
    """Desenha uma face simples baseada no mood (inspirado no Pwnagotchi)"""
    # Cabeça (círculo)
    draw.ellipse([x, y, x+30, y+30], outline=0, width=1)
    
    # Olhos e boca baseados no mood
    if mood_state == "happy":
        # Olhos felizes
        draw.ellipse([x+8, y+10, x+12, y+14], fill=0)
        draw.ellipse([x+18, y+10, x+22, y+14], fill=0)
        # Sorriso
        draw.arc([x+8, y+15, x+22, y+25], start=0, end=180, fill=0, width=2)
    elif mood_state == "excited":
        # Olhos grandes
        draw.ellipse([x+7, y+9, x+13, y+15], fill=0)
        draw.ellipse([x+17, y+9, x+23, y+15], fill=0)
        # Sorriso grande
        draw.arc([x+6, y+14, x+24, y+28], start=0, end=180, fill=0, width=2)
    elif mood_state == "angry":
        # Olhos fechados/bravos
        draw.line([x+8, y+12, x+12, y+10], fill=0, width=2)
        draw.line([x+18, y+10, x+22, y+12], fill=0, width=2)
        # Boca brava
        draw.arc([x+10, y+20, x+20, y+28], start=180, end=360, fill=0, width=2)
    elif mood_state == "sad":
        # Olhos tristes
        draw.ellipse([x+8, y+10, x+12, y+14], fill=0)
        draw.ellipse([x+18, y+10, x+22, y+14], fill=0)
        # Boca triste
        draw.arc([x+8, y+20, x+22, y+28], start=180, end=360, fill=0, width=2)
    else:  # bored
        # Olhos normais
        draw.ellipse([x+8, y+10, x+12, y+14], fill=0)
        draw.ellipse([x+18, y+10, x+22, y+14], fill=0)
        # Linha reta (neutro)
        draw.line([x+10, y+22, x+20, y+22], fill=0, width=2)

def get_uptime_str():
    """Retorna string de uptime formatada"""
    delta = datetime.now() - start_time
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    return f"{delta.days}d {hours:02d}h {minutes:02d}m"

def update_display():
    if epd is None:
        return # Se o display falhou, não tenta atualizar (preserva o Flask)
    
    try:
        mode, ip = detect_mode()
        global current_mode, current_ip
        current_mode = mode
        current_ip = ip
        
        # V4: Dimensões são height x width (122 x 250)
        # Cria imagem no formato correto para V4
        image = Image.new('1', (epd.height, epd.width), 255)  # height=122, width=250
        draw = ImageDraw.Draw(image)
        
        # Layout inspirado no Pwnagotchi e Bjorn
        # ========== HEADER ==========
        draw.text((5, 2), "BLEeding Pi", font=font_large, fill=0)
        
        # ========== FACE/MOOD (lado esquerdo) ==========
        draw_face(draw, 5, 25, mood)
        
        # ========== INFO PRINCIPAL (lado direito da face) ==========
        x_info = 40
        y_info = 25
        
        # Status
        status_text = "IDLE"
        if attacking:
            status_text = "ATTACK!"
        elif scan_status == "Scanning...":
            status_text = "SCAN..."
        elif scan_status == "Error":
            status_text = "ERROR"
            
        draw.text((x_info, y_info), status_text, font=font, fill=0)
        y_info += 15
        
        # Network
        draw.text((x_info, y_info), f"{mode}", font=font_small, fill=0)
        y_info += 12
        
        # IP (truncado se muito longo)
        ip_short = ip[:12] if len(ip) > 12 else ip
        draw.text((x_info, y_info), ip_short, font=font_small, fill=0)
        
        # ========== ESTATÍSTICAS (abaixo da face) ==========
        y_stats = 60
        draw.text((5, y_stats), f"Targets: {len(targets)}", font=font_small, fill=0)
        y_stats += 12
        draw.text((5, y_stats), f"Scans: {total_scans}", font=font_small, fill=0)
        y_stats += 12
        draw.text((5, y_stats), f"Attacks: {total_attacks}", font=font_small, fill=0)
        
        # ========== TARGET INFO (se selecionado ou atacando) ==========
        y_target = 100
        if attacking and selected_target:
            target_info = targets_info.get(selected_target, {})
            target_name = target_info.get('name', 'Unknown')[:15]
            draw.text((5, y_target), f">> {target_name}", font=font_small, fill=0)
            y_target += 12
            mac_short = selected_target[:17] if len(selected_target) > 17 else selected_target
            draw.text((5, y_target), mac_short, font=font_small, fill=0)
        elif selected_target:
            target_info = targets_info.get(selected_target, {})
            target_name = target_info.get('name', 'Unknown')[:15]
            draw.text((5, y_target), f"Sel: {target_name}", font=font_small, fill=0)
            y_target += 12
            rssi = target_info.get('rssi', 0)
            if rssi != 0:
                draw.text((5, y_target), f"RSSI: {rssi} dBm", font=font_small, fill=0)
        
        # ========== UPTIME (rodapé) ==========
        y_footer = 115
        uptime = get_uptime_str()
        draw.line([(0, y_footer-2), (epd.width, y_footer-2)], fill=0)
        draw.text((5, y_footer), f"Uptime: {uptime}", font=font_small, fill=0)

        # V4: Otimização de atualização
        # Primeira atualização sempre FULL, depois tenta PART para velocidade
        global display_update_count
        display_update_count += 1
        
        # Primeira atualização e a cada 10 atualizações usa FULL para limpar ghosting
        if display_update_count == 1 or display_update_count % 10 == 0:
            epd.init()
            epd.display(epd.getbuffer(image))
        else:
            # Usa PART_UPDATE para atualizações mais rápidas (V4 suporta)
            try:
                epd.init(epd.PART_UPDATE)
                epd.displayPartial(epd.getbuffer(image))
            except (AttributeError, Exception):
                # Se PART_UPDATE não estiver disponível ou falhar, usa FULL
                epd.init()
                epd.display(epd.getbuffer(image))
            
    except Exception as e:
        print(f"Erro ao desenhar: {e}")

def run_display_loop():
    init_display_safe()
    # Pequeno delay para garantir que o display ligou antes do Flask
    time.sleep(2) 
    
    last_activity = datetime.now()
    
    while True:
        # Atualiza mood para "bored" se não houver atividade há mais de 30 segundos
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
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BLEeding Ultimate</title>
    <style>
        body { font-family: sans-serif; background: #222; color: #fff; text-align: center; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }
        .card { background: #333; padding: 20px; border-radius: 10px; }
        h1, h2 { color: #00d4ff; }
        button { padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; margin: 5px; }
        .btn-blue { background: #00d4ff; color: #000; }
        .btn-red { background: #ff6b6b; color: #fff; }
        .btn-green { background: #4cd964; color: #000; }
        input { padding: 10px; width: 100%; margin: 10px 0; background: #444; border: 1px solid #555; color: #fff; box-sizing: border-box; }
        ul { list-style: none; padding: 0; text-align: left; }
        li { background: #444; margin: 5px 0; padding: 10px; border-radius: 5px; font-family: monospace; cursor: pointer; }
        .status-badge { display: inline-block; padding: 5px 10px; border-radius: 5px; font-weight: bold; }
        .idle { background: #4cd964; color: #000; }
        .scanning { background: #ffd43b; color: #000; }
        .attacking { background: #ff6b6b; color: #fff; }
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
                    select.innerHTML = '<option value="">Selecione...</option>';
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
    </script>
</head>
<body>
    <div class="container">
        <h1>🔓 BLEeding Ultimate</h1>
        <div class="card">
            <h2>Configuração de Rede</h2>
            <p><strong>Modo:</strong> {{ network_mode }} ({{ network_ip }})</p>
            <h3>Modo AP (Hotspot)</h3>
            <form action="/set_ap" method="POST"><button type="submit" class="btn-blue">Ativar AP ({{ ap_ssid }})</button></form>
            <h3>Modo Cliente (Wi-Fi)</h3>
            <form action="/set_client" method="POST"><input type="text" name="ssid" placeholder="Nome da Rede" required><input type="password" name="password" placeholder="Senha" required><button type="submit" class="btn-blue">Conectar</button></form>
        </div>
        <div class="card">
            <h2>Controle BLEeding</h2>
            <p>Status: <span id="status-badge" class="status-badge idle">Idle</span></p>
            <p id="status-text">Aguardando...</p>
            <button id="scan-btn" onclick="location.href='/scan'" class="btn-green">SCAN BLE</button>
            <hr style="border-color: #555;">
            <p>Alvos Encontrados: <span id="target-count">0</span></p>
            <p style="font-size: 12px; color: #888;">Scans: <span id="stat-scans">0</span> | Attacks: <span id="stat-attacks">0</span> | Mood: <span id="stat-mood">bored</span></p>
            <div style="display: flex; gap: 10px;"><select id="target-select"></select></div>
            <div style="display: flex; gap: 10px;"><button id="attack-btn" onclick="startAttack()" class="btn-red" disabled>ATTACK</button><button id="stop-btn" onclick="stopAttack()" class="btn-blue" disabled>STOP</button></div>
            <ul id="target-list" style="margin-top: 10px; max-height: 150px; overflow-y: auto;"></ul>
        </div>
    </div>
    <script>
        function startAttack() { var mac = document.getElementById('target-select').value; if(!mac) return alert('Selecione um alvo!'); fetch('/attack', { method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: 'mac=' + mac }); }
        function stopAttack() { fetch('/stop', { method: 'POST' }); }
    </script>
</body>
</html>
"""

# ================= FLASK ROUTES =================

@app.route('/')
def index():
    mode, ip = detect_mode()
    return render_template_string(HTML_TEMPLATE, network_mode=mode, network_ip=ip, ap_ssid=AP_SSID)

@app.route('/api/status')
def api_status():
    global targets, attacking, scan_status, selected_target, total_scans, total_attacks, mood
    status_text = "Idle"
    status_class = "idle"
    if attacking:
        status_text = f"Attacking {selected_target}"
        status_class = "attacking"
    elif scan_status == "Scanning...":
        status_text = "Scanning..."
        status_class = "scanning"
    
    # Prepara lista de targets com informações
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

@app.route('/set_ap', methods=['POST'])
def set_ap():
    threading.Thread(target=restart_services_ap).start()
    time.sleep(1)
    return index()

@app.route('/set_client', methods=['POST'])
def set_client():
    ssid = request.form['ssid']
    password = request.form['password']
    threading.Thread(target=restart_services_client, args=(ssid, password)).start()
    time.sleep(1)
    return index()

@app.route('/scan')
def scan():
    threading.Thread(target=run_bleeding_scan).start()
    return index()

@app.route('/attack', methods=['POST'])
def attack():
    global attack_thread, selected_target
    mac = request.form['mac']
    selected_target = mac
    stop_bleeding_attack()
    attack_thread = threading.Thread(target=run_bleeding_attack_thread, args=(mac,))
    attack_thread.start()
    return index()

@app.route('/stop', methods=['POST'])
def stop():
    stop_bleeding_attack()
    return index()

# ================= MAIN =================
if __name__ == '__main__':
    # Inicia o Display em Thread (com segurança)
    t = threading.Thread(target=run_display_loop)
    t.daemon = True
    t.start()
    
    # Pausa para estabilizar
    time.sleep(3)
    
    # Inicia Flask
    print("=" * 50)
    print("🩸 BLEeding Ultimate v4 - Pwnagotchi Style")
    print(f"📡 Para conectar, use: http://{get_ip_address()}")
    print(f"🎭 Mood inicial: {mood}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=80, debug=False)