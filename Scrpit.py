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

# BLEeding - Tenta encontrar o caminho correto
BLEEDING_PATH = "/root/bleeding"  # Caminho padrão encontrado no sistema
ATTACK_TIMEOUT = 10
# Caminhos alternativos possíveis (mais abrangente)
BLEEDING_PATHS = [
    "/root/bleeding",      # Caminho encontrado no sistema
    "/root/BLEeding",      # Versão com maiúsculas
    "/opt/BLEeding",
    "/opt/bleeding",
    "/home/pi/BLEeding",
    "/home/pi/bleeding",
    "/home/root/BLEeding",
    "/home/root/bleeding",
    "/usr/local/BLEeding",
    "/usr/local/bleeding",
    "./BLEeding",
    "./bleeding",
    "~/BLEeding",
    "~/bleeding"
]
# Adiciona caminho relativo ao script se disponível
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    BLEEDING_PATHS.append(os.path.join(script_dir, "BLEeding"))
except:
    pass

# Theme and Display Settings
THEME_COLOR = "#00d4ff"  # Cor principal do tema
DARK_BG = "#1a1a2e"      # Fundo escuro
CARD_BG = "#16213e"      # Fundo dos cards
TEXT_COLOR = "#eaeaea"   # Cor do texto

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
last_full_update = None  # Timestamp da última atualização FULL

# Debug info para exibir na interface web
debug_info = {
    'last_scan_output': '',
    'last_scan_error': '',
    'bleeding_path': '',
    'last_scan_time': '',
    'last_scan_command': '',
    'last_scan_return_code': None
}

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

def find_bleeding_path():
    """Encontra o caminho correto do BLEeding"""
    global BLEEDING_PATH
    
    # Primeiro, tenta usar o caminho atual se já foi encontrado antes
    if BLEEDING_PATH and os.path.exists(BLEEDING_PATH) and os.path.exists(os.path.join(BLEEDING_PATH, "bleeding.py")):
        return BLEEDING_PATH
    
    # Busca em todos os caminhos possíveis
    for path in BLEEDING_PATHS:
        try:
            expanded_path = os.path.expanduser(path)
            if os.path.exists(expanded_path) and os.path.exists(os.path.join(expanded_path, "bleeding.py")):
                BLEEDING_PATH = expanded_path
                print(f"✓ BLEeding encontrado em: {BLEEDING_PATH}")
                return expanded_path
        except Exception as e:
            continue
    
    # Se não encontrou, tenta buscar em diretórios comuns
    search_dirs = ["/root", "/opt", "/home/pi", "/usr/local"]
    for base_dir in search_dirs:
        if os.path.exists(base_dir):
            try:
                for item in os.listdir(base_dir):
                    potential_path = os.path.join(base_dir, item)
                    if os.path.isdir(potential_path) and os.path.exists(os.path.join(potential_path, "bleeding.py")):
                        BLEEDING_PATH = potential_path
                        print(f"✓ BLEeding encontrado em: {BLEEDING_PATH}")
                        return potential_path
            except:
                continue
    
    print(f"✗ BLEeding não encontrado. Caminhos testados: {BLEEDING_PATHS}")
    return None

def run_bleeding_scan():
    global targets, targets_info, scan_status, total_scans, total_targets_found, mood
    
    # Força flush imediato dos prints (importante para threads)
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    
    print("\n" + "="*60, flush=True)
    print("🔍 [DEBUG] Iniciando scan BLE...", flush=True)
    print("="*60, flush=True)
    
    scan_status = "Scanning..."
    mood = "excited"
    update_display()
    
    # Tenta encontrar o caminho do BLEeding
    bleeding_path = find_bleeding_path()
    if not bleeding_path:
        print(f"❌ [DEBUG] ERRO: BLEeding não encontrado!", flush=True)
        print(f"   [DEBUG] Por favor, instale o BLEeding ou configure o caminho correto.", flush=True)
        print(f"   [DEBUG] Caminhos testados: {BLEEDING_PATHS}", flush=True)
        scan_status = "Error"
        mood = "sad"
        update_display()
        return
    
    print(f"✓ [DEBUG] BLEeding encontrado em: {bleeding_path}", flush=True)
    
    old_cwd = os.getcwd()
    print(f"📁 [DEBUG] Diretório atual antes: {old_cwd}", flush=True)
    
    try:
        os.chdir(bleeding_path)
        print(f"📁 [DEBUG] Mudou para diretório: {os.getcwd()}", flush=True)
        
        # Verifica se o arquivo existe
        bleeding_script = os.path.join(bleeding_path, "bleeding.py")
        if not os.path.exists(bleeding_script):
            print(f"❌ [DEBUG] Arquivo bleeding.py não encontrado em: {bleeding_script}", flush=True)
            scan_status = "Error"
            mood = "sad"
            update_display()
            return
        
        print(f"✓ [DEBUG] Arquivo bleeding.py encontrado: {bleeding_script}", flush=True)
        
        # Teste: Verifica se o BLEeding funciona manualmente primeiro
        print(f"\n🧪 [DEBUG] Testando BLEeding diretamente...", flush=True)
        test_cmd = ['python3', 'bleeding.py', '--help']
        test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)
        print(f"   [DEBUG] Teste --help: return code = {test_result.returncode}", flush=True)
        if test_result.stdout:
            print(f"   [DEBUG] Saída do help (primeiras 200 chars): {test_result.stdout[:200]}", flush=True)
        
        # Comando a ser executado
        cmd = ['python3', 'bleeding.py', 'scan', '--ble']
        print(f"\n🚀 [DEBUG] Executando comando: {' '.join(cmd)}", flush=True)
        print(f"   [DEBUG] Timeout: 20 segundos", flush=True)
        sys.stdout.flush()
        
        result = subprocess.run(cmd, 
                              capture_output=True, text=True, timeout=20)
        
        print(f"\n📊 [DEBUG] Resultado do comando:", flush=True)
        print(f"   [DEBUG] Return code: {result.returncode}", flush=True)
        print(f"   [DEBUG] STDOUT ({len(result.stdout)} caracteres):", flush=True)
        print("-" * 60, flush=True)
        if result.stdout:
            print(result.stdout, flush=True)
        else:
            print("   (vazio)", flush=True)
        print("-" * 60, flush=True)
        
        print(f"   [DEBUG] STDERR ({len(result.stderr)} caracteres):", flush=True)
        print("-" * 60, flush=True)
        if result.stderr:
            print(result.stderr, flush=True)
        else:
            print("   (vazio)", flush=True)
        print("-" * 60, flush=True)
        sys.stdout.flush()
        
        output = result.stdout
        
        # Parse melhorado - procura por MAC addresses e informações
        print(f"\n🔎 [DEBUG] Analisando saída...", flush=True)
        lines = output.split('\n')
        print(f"   [DEBUG] Total de linhas na saída: {len(lines)}", flush=True)
        sys.stdout.flush()
        
        found_macs = []
        new_targets = 0
        
        for i, line in enumerate(lines):
            # Procura MAC addresses (formato XX:XX:XX:XX:XX:XX ou XX-XX-XX-XX-XX-XX)
            mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', line)
            if mac_match:
                mac_str = mac_match.group(0).replace('-', ':').upper()
                if mac_str not in found_macs:
                    found_macs.append(mac_str)
                    print(f"   ✓ [DEBUG] MAC encontrado na linha {i+1}: {mac_str}", flush=True)
                    print(f"      [DEBUG] Linha: {line[:80]}", flush=True)
                    sys.stdout.flush()
                    
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
        
        print(f"\n📈 [DEBUG] Resultado do scan:", flush=True)
        print(f"   [DEBUG] MACs encontrados: {len(found_macs)}", flush=True)
        print(f"   [DEBUG] Total de targets únicos: {len(targets_info)}", flush=True)
        print(f"   [DEBUG] Lista de MACs: {found_macs}", flush=True)
        
        if len(targets) > 0:
            mood = "happy"
            print(f"   ✓ [DEBUG] Scan bem-sucedido! Dispositivos encontrados.", flush=True)
        else:
            mood = "sad"
            print(f"   ⚠ [DEBUG] Nenhum dispositivo encontrado.", flush=True)
            print(f"   [DEBUG] Possíveis causas:", flush=True)
            print(f"      - Nenhum dispositivo Bluetooth próximo", flush=True)
            print(f"      - Bluetooth desabilitado", flush=True)
            print(f"      - Problema com o comando bleeding.py", flush=True)
            print(f"      - Formato de saída diferente do esperado", flush=True)
            
        scan_status = "Done"
        print("="*60 + "\n", flush=True)
        sys.stdout.flush()
        
    except subprocess.TimeoutExpired:
        error_msg = "Timeout - o comando demorou mais de 20 segundos"
        print(f"\n❌ [DEBUG] ERRO: {error_msg}", flush=True)
        print(f"   [DEBUG] Isso pode indicar que o BLEeding está travado ou há muitos dispositivos", flush=True)
        debug_info['last_scan_error'] = error_msg
        scan_status = "Error"
        mood = "sad"
        sys.stdout.flush()
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        traceback_str = ''.join(traceback.format_exc())
        print(f"\n❌ [DEBUG] ERRO no scan: {error_msg}", flush=True)
        print(f"   [DEBUG] Traceback completo:", flush=True)
        print(traceback_str, flush=True)
        debug_info['last_scan_error'] = f"{error_msg}\n\n{traceback_str}"
        sys.stdout.flush()
        scan_status = "Error"
        mood = "sad"
    finally:
        # Sempre retorna ao diretório original
        try:
            os.chdir(old_cwd)
            print(f"📁 [DEBUG] Retornou para diretório: {os.getcwd()}", flush=True)
        except Exception as e:
            print(f"⚠ [DEBUG] Erro ao retornar diretório: {e}", flush=True)
        sys.stdout.flush()
    
    update_display()

def run_bleeding_attack_thread(mac):
    global attacking, attack_thread, total_attacks, mood
    attacking = True
    mood = "angry"
    total_attacks += 1
    update_display()
    
    # Tenta encontrar o caminho do BLEeding
    bleeding_path = find_bleeding_path()
    if not bleeding_path:
        print(f"ERRO: BLEeding não encontrado!")
        print(f"Por favor, instale o BLEeding ou configure o caminho correto.")
        attacking = False
        mood = "sad"
        update_display()
        return
    
    old_cwd = os.getcwd()
    os.chdir(bleeding_path)
    try:
        cmd = ['python3', 'bleeding.py', 'deauth', mac, '--ble', '--timeout', str(ATTACK_TIMEOUT)]
        subprocess.run(cmd)
    except Exception as e:
        print(f"Erro Ataque: {e}")
    finally:
        # Sempre retorna ao diretório original
        try:
            os.chdir(old_cwd)
        except:
            pass
    
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

def draw_vampigotchi_chibi(draw, x, y, mood_state):
    """Desenha o VampiGotchi em estilo pixel art chibi baseado na imagem"""
    # Cabeça redonda (pixel art style com contorno grosso)
    draw.ellipse([x+2, y+4, x+28, y+30], outline=0, width=2)
    
    # Orelhas pontudas no topo da cabeça (estilo pixel art)
    # Orelha esquerda (triângulo)
    draw.polygon([(x+5, y+6), (x+7, y+2), (x+9, y+6)], fill=0)
    # Orelha direita (triângulo)
    draw.polygon([(x+21, y+6), (x+23, y+2), (x+25, y+6)], fill=0)
    
    # Cabelo escuro com franja (desenha como retângulos pixelados)
    # Topo da cabeça (cabelo preto)
    draw.rectangle([x+5, y+5, x+25, y+9], fill=0)
    # Franja (parte da frente)
    draw.rectangle([x+6, y+8, x+24, y+11], fill=0)
    # Lados do cabelo (laterais)
    draw.rectangle([x+3, y+8, x+7, y+14], fill=0)
    draw.rectangle([x+23, y+8, x+27, y+14], fill=0)
    # Cabelo na parte de trás
    draw.arc([x+5, y+10, x+25, y+18], start=180, end=360, fill=0, width=2)
    
    # Face (área clara dentro do cabelo)
    draw.ellipse([x+7, y+9, x+23, y+25], fill=255, outline=0, width=1)
    
    # Bochechas com blush (desenha círculos com contorno fino para simular cinza)
    draw.ellipse([x+9, y+17, x+12, y+20], outline=0, width=1)
    draw.ellipse([x+18, y+17, x+21, y+20], outline=0, width=1)
    
    # Olhos baseados no mood
    if mood_state == "happy" or mood_state == "excited":
        # Olho esquerdo grande e redondo (abrindo bem)
        draw.ellipse([x+9, y+14, x+13, y+18], fill=0)
        # Olho direito fechado (wink) - linha curva para cima
        draw.arc([x+17, y+14, x+21, y+18], start=0, end=180, fill=0, width=2)
        # Brilho no olho esquerdo
        draw.point([x+11, y+16], fill=255)
    elif mood_state == "angry":
        # Olhos bravos (linhas inclinadas)
        draw.line([x+9, y+17, x+13, y+14], fill=0, width=2)
        draw.line([x+17, y+17, x+21, y+14], fill=0, width=2)
    elif mood_state == "sad":
        # Olhos tristes (círculos com arco para baixo)
        draw.ellipse([x+9, y+14, x+13, y+18], fill=0)
        draw.ellipse([x+17, y+14, x+21, y+18], fill=0)
        # Linhas de lágrimas
        draw.line([x+11, y+19, x+11, y+22], fill=0, width=1)
        draw.line([x+19, y+19, x+19, y+22], fill=0, width=1)
    else:  # bored ou padrão
        # Olho esquerdo grande e redondo
        draw.ellipse([x+9, y+14, x+13, y+18], fill=0)
        # Olho direito fechado (wink) - padrão fofo
        draw.arc([x+17, y+14, x+21, y+18], start=0, end=180, fill=0, width=2)
        # Brilho no olho esquerdo
        draw.point([x+11, y+16], fill=255)
    
    # Presas pequenas no lábio superior
    draw.rectangle([x+11, y+19, x+12, y+22], fill=0)  # Presa esquerda
    draw.rectangle([x+18, y+19, x+19, y+22], fill=0)  # Presa direita
    
    # Boca baseada no mood
    if mood_state == "happy" or mood_state == "excited":
        # Sorriso pequeno e discreto
        draw.arc([x+12, y+20, x+18, y+24], start=0, end=180, fill=0, width=1)
    elif mood_state == "angry":
        # Boca brava (linha para baixo)
        draw.arc([x+13, y+22, x+17, y+26], start=180, end=360, fill=0, width=2)
    elif mood_state == "sad":
        # Boca triste (curva para baixo)
        draw.arc([x+12, y+22, x+18, y+26], start=180, end=360, fill=0, width=1)
    else:  # bored
        # Boca neutra (linha reta pequena)
        draw.line([x+13, y+22, x+17, y+22], fill=0, width=1)
    
    # Capa de vampiro com gola alta (desenha antes do laço)
    # Corpo da capa (parte de trás)
    draw.arc([x-2, y+24, x+32, y+42], start=0, end=180, fill=0, width=2)
    
    # Gola alta da capa (desenha por cima do pescoço)
    draw.arc([x+4, y+21, x+26, y+27], start=180, end=360, fill=0, width=2)
    # Parte interna da gola (branca - contrasta com preto)
    draw.arc([x+9, y+23, x+21, y+27], start=180, end=360, fill=255, width=1)
    
    # Laço no pescoço (sobreposto à gola)
    # Parte central do laço (vertical)
    draw.rectangle([x+13, y+25, x+17, y+27], fill=255, outline=0, width=1)
    # Laço esquerdo (borboleta)
    draw.ellipse([x+10, y+26, x+14, y+29], fill=255, outline=0, width=1)
    draw.ellipse([x+9, y+27, x+13, y+30], fill=255, outline=0, width=1)
    # Laço direito (borboleta)
    draw.ellipse([x+16, y+26, x+20, y+29], fill=255, outline=0, width=1)
    draw.ellipse([x+17, y+27, x+21, y+30], fill=255, outline=0, width=1)
    # Centro do laço (quadrado preto no meio)
    draw.rectangle([x+13, y+27, x+17, y+29], fill=0)

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
        
        # V4: Dimensões são width x height (250 x 122) - VERTICAL
        # Cria imagem no formato vertical para melhor aproveitamento
        image = Image.new('1', (epd.width, epd.height), 255)  # width=250, height=122, BRANCO
        draw = ImageDraw.Draw(image)
        
        # Layout VERTICAL - TELA COMPLETA com VampiGotchi na parte inferior
        # ========== HEADER ==========
        draw.text((5, 2), "VampiGotchi", font=font_large, fill=0)
        
        # Linha separadora abaixo do título
        draw.line([(0, 18), (epd.width, 18)], fill=0, width=1)
        
        # ========== ÁREA PRINCIPAL DE INFORMAÇÕES ==========
        y_start = 22
        
        # Status (esquerda)
        status_text = "IDLE"
        if attacking:
            status_text = "ATTACK!"
        elif scan_status == "Scanning...":
            status_text = "SCAN..."
        elif scan_status == "Error":
            status_text = "ERROR"
            
        draw.text((5, y_start), f"Status: {status_text}", font=font, fill=0)
        y_start += 14
        
        # Network Info (esquerda)
        draw.text((5, y_start), f"Mode: {mode}", font=font_small, fill=0)
        y_start += 12
        ip_short = ip[:18] if len(ip) > 18 else ip
        draw.text((5, y_start), f"IP: {ip_short}", font=font_small, fill=0)
        y_start += 12
        
        # Linha separadora
        draw.line([(0, y_start), (epd.width, y_start)], fill=0, width=1)
        y_start += 4
        
        # ========== ESTATÍSTICAS (lado esquerdo) ==========
        y_stats = y_start
        draw.text((5, y_stats), f"Targets: {len(targets)}", font=font_small, fill=0)
        y_stats += 12
        draw.text((5, y_stats), f"Scans: {total_scans}", font=font_small, fill=0)
        y_stats += 12
        draw.text((5, y_stats), f"Attacks: {total_attacks}", font=font_small, fill=0)
        y_stats += 12
        
        # ========== TARGET INFO (se selecionado ou atacando) ==========
        if attacking and selected_target:
            target_info = targets_info.get(selected_target, {})
            target_name = target_info.get('name', 'Unknown')[:18]
            draw.text((5, y_stats), f">> {target_name}", font=font_small, fill=0)
            y_stats += 12
            mac_short = selected_target[:20] if len(selected_target) > 20 else selected_target
            draw.text((5, y_stats), mac_short, font=font_small, fill=0)
            y_stats += 12
        elif selected_target:
            target_info = targets_info.get(selected_target, {})
            target_name = target_info.get('name', 'Unknown')[:18]
            draw.text((5, y_stats), f"Sel: {target_name}", font=font_small, fill=0)
            y_stats += 12
            rssi = target_info.get('rssi', 0)
            if rssi != 0:
                draw.text((5, y_stats), f"RSSI: {rssi} dBm", font=font_small, fill=0)
                y_stats += 12
        
        # ========== UPTIME ==========
        uptime = get_uptime_str()
        draw.text((5, y_stats), f"Uptime: {uptime}", font=font_small, fill=0)
        
        # ========== VAMPIGOTCHI CHIBI (PARTE INFERIOR) ==========
        # Calcula posição para centralizar na parte inferior
        char_y = epd.height - 50  # 50 pixels do fundo (altura do personagem + margem)
        char_x = (epd.width - 30) // 2  # Centraliza horizontalmente (personagem tem ~30px de largura)
        draw_vampigotchi_chibi(draw, char_x, char_y, mood)

        # V4: Otimização de atualização - EVITA PISCAR
        global display_update_count, last_full_update
        display_update_count += 1
        
        # Controle de atualização: FULL apenas quando necessário, PART para o resto
        # Primeira atualização sempre FULL
        if display_update_count == 1:
            epd.init()
            epd.Clear(0xFF)  # Limpa o display para branco
            epd.display(epd.getbuffer(image))
            last_full_update = datetime.now()
        # FULL a cada 30 atualizações (aproximadamente 1.5 minutos) para limpar ghosting
        elif display_update_count % 30 == 0:
            epd.init()
            epd.display(epd.getbuffer(image))
            last_full_update = datetime.now()
        else:
            # Usa PART_UPDATE para atualizações rápidas sem piscar
            try:
                epd.init(epd.PART_UPDATE)
                epd.displayPartial(epd.getbuffer(image))
            except (AttributeError, Exception) as e:
                # Se PART_UPDATE falhar, usa FULL mas apenas se não atualizou há mais de 5 segundos
                now = datetime.now()
                if last_full_update is None or (now - last_full_update).total_seconds() > 5:
                    epd.init()
                    epd.display(epd.getbuffer(image))
                    last_full_update = now
            
    except Exception as e:
        print(f"Erro ao desenhar: {e}")

def run_display_loop():
    global last_full_update
    last_full_update = None
    init_display_safe()
    # Pequeno delay para garantir que o display ligou antes do Flask
    time.sleep(2) 
    
    last_activity = datetime.now()
    last_update = datetime.now()
    
    while True:
        # Atualiza mood para "bored" se não houver atividade há mais de 30 segundos
        global mood
        if not attacking and scan_status != "Scanning...":
            time_since_activity = (datetime.now() - last_activity).total_seconds()
            if time_since_activity > 30 and mood not in ["sad", "angry"]:
                mood = "bored"
        else:
            last_activity = datetime.now()
        
        # Atualiza display apenas se necessário (mudança de estado ou a cada 5 segundos)
        now = datetime.now()
        time_since_update = (now - last_update).total_seconds()
        
        # Atualiza imediatamente se houver mudança de estado, senão atualiza a cada 5 segundos
        needs_update = (
            attacking or 
            scan_status == "Scanning..." or 
            time_since_update >= 5 or
            display_update_count == 0
        )
        
        if needs_update:
            update_display()
            last_update = now
        
        time.sleep(2)  # Reduzido para 2 segundos mas atualiza apenas quando necessário

# ================= WEB SERVER =================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🩸 BLEeding Ultimate - Enhanced Interface</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Poppins', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            color: #eaeaea;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding: 30px;
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .header h1 {
            font-size: 2.5em;
            background: linear-gradient(45deg, #00d4ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }
        
        .header p {
            color: #a0a0a0;
            font-size: 0.9em;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 40px rgba(0, 212, 255, 0.2);
        }
        
        .card h2 {
            color: #00d4ff;
            margin-bottom: 20px;
            font-size: 1.4em;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .card h2 i {
            font-size: 1.2em;
        }
        
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .info-row:last-child {
            border-bottom: none;
        }
        
        .info-label {
            color: #a0a0a0;
            font-weight: 500;
        }
        
        .info-value {
            color: #00ff88;
            font-weight: 600;
        }
        
        .button-group {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        
        button {
            padding: 15px 25px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.95em;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        button:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
        }
        
        button:active {
            transform: translateY(-1px);
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #00d4ff, #0099cc);
            color: #000;
        }
        
        .btn-success {
            background: linear-gradient(135deg, #00ff88, #00cc66);
            color: #000;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, #ff6b6b, #cc5555);
            color: #fff;
        }
        
        .btn-warning {
            background: linear-gradient(135deg, #ffd93d, #ccac30);
            color: #000;
        }
        
        input, select {
            padding: 12px 15px;
            background: rgba(255, 255, 255, 0.1);
            border: 2px solid rgba(255, 255, 255, 0.2);
            border-radius: 10px;
            color: #fff;
            font-size: 0.95em;
            width: 100%;
            margin-bottom: 15px;
            transition: all 0.3s ease;
        }
        
        input:focus, select:focus {
            outline: none;
            border-color: #00d4ff;
            background: rgba(255, 255, 255, 0.15);
        }
        
        input::placeholder {
            color: #808080;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            color: #a0a0a0;
            font-weight: 500;
        }
        
        .status-container {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
            margin: 20px 0;
            padding: 20px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 15px;
        }
        
        .status-badge {
            padding: 10px 25px;
            border-radius: 25px;
            font-weight: 700;
            font-size: 1.1em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .status-idle {
            background: linear-gradient(135deg, #4cd964, #3cb550);
            color: #000;
        }
        
        .status-scanning {
            background: linear-gradient(135deg, #ffd93d, #ccac30);
            color: #000;
            animation: pulse 1.5s infinite;
        }
        
        .status-attacking {
            background: linear-gradient(135deg, #ff6b6b, #cc5555);
            color: #fff;
            animation: shake 0.5s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-5px); }
            75% { transform: translateX(5px); }
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        
        .stat-box {
            background: rgba(0, 0, 0, 0.3);
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .stat-value {
            font-size: 2em;
            font-weight: 700;
            color: #00d4ff;
            margin-bottom: 5px;
        }
        
        .stat-label {
            color: #a0a0a0;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .target-list {
            list-style: none;
            max-height: 300px;
            overflow-y: auto;
            padding: 10px 0;
        }
        
        .target-list::-webkit-scrollbar {
            width: 8px;
        }
        
        .target-list::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        }
        
        .target-list::-webkit-scrollbar-thumb {
            background: #00d4ff;
            border-radius: 4px;
        }
        
        li.target-item {
            background: rgba(255, 255, 255, 0.08);
            margin: 10px 0;
            padding: 15px;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        li.target-item:hover {
            background: rgba(255, 255, 255, 0.15);
            border-color: #00d4ff;
            transform: translateX(5px);
        }
        
        .target-name {
            font-weight: 600;
            color: #00d4ff;
            margin-bottom: 5px;
        }
        
        .target-mac {
            font-size: 0.85em;
            color: #a0a0a0;
            font-family: 'Courier New', monospace;
        }
        
        .target-rssi {
            color: #00ff88;
            font-weight: 600;
        }
        
        .mood-indicator {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            font-weight: 500;
        }
        
        .mood-icon {
            font-size: 1.3em;
        }
        
        .config-section {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }
        
        .color-picker-wrapper {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .color-picker-wrapper input[type="color"] {
            width: 50px;
            height: 40px;
            padding: 0;
            margin: 0;
            border: none;
            border-radius: 8px;
            cursor: pointer;
        }
        
        .no-devices {
            text-align: center;
            padding: 40px;
            color: #808080;
        }
        
        .no-devices i {
            font-size: 3em;
            margin-bottom: 15px;
            color: #404040;
        }
        
        @media (max-width: 768px) {
            .header h1 {
                font-size: 1.8em;
            }
            
            .button-group {
                grid-template-columns: 1fr;
            }
            
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }
    </style>
    <script>
        setInterval(function() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status-badge').className = 'status-badge status-' + data.status_class;
                    document.getElementById('status-badge').textContent = data.status_text;
                    document.getElementById('status-text').textContent = data.status_text;
                    document.getElementById('target-count').textContent = data.count;
                    document.getElementById('stat-scans').textContent = data.stats.total_scans;
                    document.getElementById('stat-attacks').textContent = data.stats.total_attacks;
                    document.getElementById('stat-mood').textContent = data.stats.mood;
                    document.getElementById('stat-uptime').textContent = data.stats.uptime;
                    
                    // Atualiza informações de debug
                    if (data.debug) {
                        document.getElementById('debug-path').textContent = data.debug.bleeding_path || 'Não encontrado';
                        document.getElementById('debug-scan-time').textContent = data.debug.last_scan_time || '-';
                        document.getElementById('debug-command').textContent = data.debug.last_scan_command || '-';
                        document.getElementById('debug-return-code').textContent = 
                            data.debug.last_scan_return_code !== null ? data.debug.last_scan_return_code : '-';
                        document.getElementById('debug-output').value = data.debug.last_scan_output || 'Aguardando scan...';
                        document.getElementById('debug-error').value = data.debug.last_scan_error || 'Nenhum erro';
                    }
                    
                    const list = document.getElementById('target-list');
                    const select = document.getElementById('target-select');
                    
                    document.getElementById('scan-btn').disabled = data.scanning;
                    document.getElementById('attack-btn').disabled = !data.selected_target || data.attacking;
                    document.getElementById('stop-btn').disabled = !data.attacking;
                    
                    if (data.scanning) {
                        document.getElementById('scan-btn').innerHTML = '<i class="fas fa-spinner fa-spin"></i> Escaneando...';
                    } else {
                        document.getElementById('scan-btn').innerHTML = '<i class="fas fa-broadcast-tower"></i> SCAN BLE';
                    }
                    
                    if (data.attacking) {
                        document.getElementById('attack-btn').innerHTML = '<i class="fas fa-spinner fa-spin"></i> Atacando...';
                        document.getElementById('stop-btn').innerHTML = '<i class="fas fa-stop"></i> PARAR ATAQUE';
                    } else {
                        document.getElementById('attack-btn').innerHTML = '<i class="fas fa-crosshairs"></i> ATTACK';
                        document.getElementById('stop-btn').innerHTML = '<i class="fas fa-pause"></i> STOP';
                    }
                    
                    list.innerHTML = '';
                    select.innerHTML = '<option value="">Selecione um alvo...</option>';
                    
                    if (data.targets_info.length === 0) {
                        list.innerHTML = '<div class="no-devices"><i class="fas fa-search"></i><p>Nenhum dispositivo encontrado</p></div>';
                    } else {
                        data.targets_info.forEach(target => {
                            const li = document.createElement('li');
                            li.className = 'target-item';
                            li.innerHTML = `
                                <div class="target-name"><i class="fas fa-bluetooth-b"></i> ${target.name || 'Unknown'}</div>
                                <div class="target-mac">${target.mac}</div>
                                ${target.rssi ? `<div class="target-rssi"><i class="fas fa-signal"></i> ${target.rssi} dBm</div>` : ''}
                            `;
                            li.onclick = function() { selectTarget(target.mac); };
                            list.appendChild(li);
                            
                            const option = document.createElement('option');
                            option.value = target.mac;
                            option.textContent = `${target.name || 'Unknown'} - ${target.mac}`;
                            select.appendChild(option);
                        });
                    }
                    
                    // Update mood indicator
                    updateMoodIndicator(data.stats.mood);
                })
                .catch(error => console.error('Error:', error));
        }, 2000);
        
        function selectTarget(mac) {
            document.getElementById('target-select').value = mac;
            // Scroll to selected option
            const select = document.getElementById('target-select');
            for (let i = 0; i < select.options.length; i++) {
                if (select.options[i].value === mac) {
                    select.selectedIndex = i;
                    break;
                }
            }
        }
        
        function updateMoodIndicator(mood) {
            const moodMap = {
                'bored': { icon: '😴', label: 'Entediado' },
                'happy': { icon: '😊', label: 'Feliz' },
                'excited': { icon: '🤩', label: 'Excitado' },
                'sad': { icon: '😢', label: 'Triste' },
                'angry': { icon: '😠', label: 'Bravo' }
            };
            
            const moodData = moodMap[mood] || moodMap['bored'];
            document.getElementById('mood-icon').textContent = moodData.icon;
            document.getElementById('mood-label').textContent = moodData.label;
        }
        
        function applyTheme() {
            const bgColor = document.getElementById('bg-color').value;
            const cardColor = document.getElementById('card-color').value;
            const textColor = document.getElementById('text-color').value;
            
            document.body.style.background = bgColor;
            document.querySelectorAll('.card').forEach(card => {
                card.style.background = cardColor;
            });
            document.body.style.color = textColor;
        }
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-bluetooth-b"></i> BLEeding Ultimate</h1>
            <p>Interface Avançada de Monitoramento Bluetooth</p>
        </div>
        
        <div class="card">
            <h2><i class="fas fa-network-wired"></i> Configuração de Rede</h2>
            <div class="info-row">
                <span class="info-label">Modo Atual:</span>
                <span class="info-value">{{ network_mode }}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Endereço IP:</span>
                <span class="info-value">{{ network_ip }}</span>
            </div>
            
            <div class="button-group">
                <form action="/set_ap" method="POST" style="display: contents;">
                    <button type="submit" class="btn-primary">
                        <i class="fas fa-wifi"></i> Modo AP ({{ ap_ssid }})
                    </button>
                </form>
                <form action="/set_client" method="POST" style="display: contents;">
                    <input type="text" name="ssid" placeholder="Nome da Rede" required style="display: none;">
                    <input type="password" name="password" placeholder="Senha" required style="display: none;">
                    <button type="submit" class="btn-primary">
                        <i class="fas fa-plug"></i> Conectar Wi-Fi
                    </button>
                </form>
            </div>
        </div>
        
        <div class="card">
            <h2><i class="fas fa-palette"></i> Personalização da Interface</h2>
            <div class="config-section">
                <div>
                    <label>Cor de Fundo</label>
                    <div class="color-picker-wrapper">
                        <input type="color" id="bg-color" value="#1a1a2e" onchange="applyTheme()">
                        <span style="font-size: 0.9em; color: #a0a0a0;">Clique para alterar</span>
                    </div>
                </div>
                <div>
                    <label>Cor dos Cards</label>
                    <div class="color-picker-wrapper">
                        <input type="color" id="card-color" value="#16213e" onchange="applyTheme()">
                        <span style="font-size: 0.9em; color: #a0a0a0;">Clique para alterar</span>
                    </div>
                </div>
                <div>
                    <label>Cor do Texto</label>
                    <div class="color-picker-wrapper">
                        <input type="color" id="text-color" value="#eaeaea" onchange="applyTheme()">
                        <span style="font-size: 0.9em; color: #a0a0a0;">Clique para alterar</span>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2><i class="fas fa-crosshairs"></i> Controle BLE</h2>
            <div class="status-container">
                <span class="status-badge status-idle" id="status-badge">Idle</span>
                <span id="status-text" style="color: #a0a0a0;">Aguardando...</span>
            </div>
            
            <div class="stats-grid">
                <div class="stat-box">
                    <div class="stat-value" id="target-count">0</div>
                    <div class="stat-label">Alvos</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="stat-scans">0</div>
                    <div class="stat-label">Scans</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="stat-attacks">0</div>
                    <div class="stat-label">Ataques</div>
                </div>
                <div class="stat-box">
                    <div class="mood-indicator">
                        <span id="mood-icon" class="mood-icon">😴</span>
                        <span id="mood-label" style="color: #a0a0a0;">Entediado</span>
                    </div>
                </div>
            </div>
            
            <div class="button-group">
                <button id="scan-btn" onclick="location.href='/scan'" class="btn-success">
                    <i class="fas fa-broadcast-tower"></i> SCAN BLE
                </button>
                <button id="attack-btn" onclick="startAttack()" class="btn-danger" disabled>
                    <i class="fas fa-crosshairs"></i> ATTACK
                </button>
                <button id="stop-btn" onclick="stopAttack()" class="btn-warning" disabled>
                    <i class="fas fa-pause"></i> STOP
                </button>
            </div>
        </div>
        
        <div class="card">
            <h2><i class="fas fa-list"></i> Alvos Encontrados</h2>
            <select id="target-select">
                <option value="">Selecione um alvo...</option>
            </select>
            <ul id="target-list" class="target-list">
                <div class="no-devices">
                    <i class="fas fa-search"></i>
                    <p>Nenhum dispositivo encontrado</p>
                </div>
            </ul>
        </div>
        
        <div class="card">
            <h2><i class="fas fa-clock"></i> Informações do Sistema</h2>
            <div class="info-row">
                <span class="info-label">Tempo de Execução:</span>
                <span class="info-value" id="stat-uptime">0d 00h 00m</span>
            </div>
            <div class="info-row">
                <span class="info-label">Versão:</span>
                <span class="info-value">4.0 Ultimate</span>
            </div>
            <div class="info-row">
                <span class="info-label">Display:</span>
                <span class="info-value">E-Paper V4 (Fundo Branco)</span>
            </div>
        </div>
        
        <div class="card">
            <h2><i class="fas fa-bug"></i> Debug Information</h2>
            <p style="color: #888; font-size: 0.9em; margin-bottom: 15px;">
                Informações técnicas sobre o scan e BLEeding
            </p>
            
            <div class="info-row">
                <span class="info-label">Caminho do BLEeding:</span>
                <span class="info-value" id="debug-path" style="font-family: monospace; font-size: 0.85em;">Carregando...</span>
            </div>
            
            <div class="info-row">
                <span class="info-label">Último Scan:</span>
                <span class="info-value" id="debug-scan-time">-</span>
            </div>
            
            <div class="info-row">
                <span class="info-label">Comando Executado:</span>
                <span class="info-value" id="debug-command" style="font-family: monospace; font-size: 0.85em;">-</span>
            </div>
            
            <div class="info-row">
                <span class="info-label">Return Code:</span>
                <span class="info-value" id="debug-return-code">-</span>
            </div>
            
            <div style="margin-top: 20px;">
                <label style="display: block; margin-bottom: 8px; color: #a0a0a0; font-weight: 500;">
                    Última Saída do BLEeding:
                </label>
                <textarea id="debug-output" readonly 
                    style="width: 100%; min-height: 150px; padding: 10px; background: rgba(0,0,0,0.3); 
                           border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; 
                           color: #fff; font-family: monospace; font-size: 0.85em; 
                           resize: vertical; box-sizing: border-box;">Aguardando scan...</textarea>
            </div>
            
            <div style="margin-top: 15px;">
                <label style="display: block; margin-bottom: 8px; color: #a0a0a0; font-weight: 500;">
                    Erros (se houver):
                </label>
                <textarea id="debug-error" readonly 
                    style="width: 100%; min-height: 80px; padding: 10px; background: rgba(255,0,0,0.1); 
                           border: 1px solid rgba(255,0,0,0.3); border-radius: 8px; 
                           color: #ff6b6b; font-family: monospace; font-size: 0.85em; 
                           resize: vertical; box-sizing: border-box;">Nenhum erro</textarea>
            </div>
        </div>
    </div>
    
    <script>
        function startAttack() {
            var mac = document.getElementById('target-select').value;
            if(!mac) {
                alert('⚠️ Por favor, selecione um alvo primeiro!');
                return;
            }
            fetch('/attack', { 
                method: 'POST', 
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}, 
                body: 'mac=' + mac 
            });
        }
        
        function stopAttack() {
            fetch('/stop', { method: 'POST' });
        }
        
        // Initialize mood on page load
        updateMoodIndicator('bored');
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
    global targets, attacking, scan_status, selected_target, total_scans, total_attacks, mood, debug_info
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
        },
        'debug': debug_info
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
    import sys
    print("\n[ROUTE] /scan foi chamado - iniciando thread de scan", flush=True)
    sys.stdout.flush()
    threading.Thread(target=run_bleeding_scan, daemon=True).start()
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
    print("🩸 BLEeding Ultimate v4 - Enhanced Interface")
    print(f"📡 Para conectar, use: http://{get_ip_address()}")
    print(f"🎭 Mood inicial: {mood}")
    print(f"🖼️  Display: Fundo BRANCO ativado")
    print("=" * 50)
    app.run(host='0.0.0.0', port=80, debug=False)
