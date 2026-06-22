#!/bin/bash
# ============================================================
# TrendBot VPS Setup Script — Ubuntu 22.04 / 24.04
# Run sebagai root atau user dengan sudo
# Usage: bash setup_vps.sh
# ============================================================

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

info "=== TrendBot VPS Setup ==="
info "OS: $(lsb_release -d | cut -f2)"

# ── 1. Update sistem ─────────────────────────────────────────
info "Update sistem..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Install dependencies ──────────────────────────────────
info "Install dependencies..."
apt-get install -y -qq \
    git curl wget unzip \
    python3 python3-pip python3-venv \
    xvfb x11vnc fluxbox \
    software-properties-common \
    cabextract winbind

# ── 3. Install Wine ──────────────────────────────────────────
info "Install Wine..."
dpkg --add-architecture i386
mkdir -pm755 /etc/apt/keyrings
curl -fsSL https://dl.winehq.org/wine-builds/winehq.key \
    | gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key
. /etc/os-release
curl -fsSL "https://dl.winehq.org/wine-builds/ubuntu/dists/${VERSION_CODENAME}/winehq-${VERSION_CODENAME}.sources" \
    -o /etc/apt/sources.list.d/winehq.sources 2>/dev/null || \
    echo "deb [arch=amd64,i386 signed-by=/etc/apt/keyrings/winehq-archive.key] https://dl.winehq.org/wine-builds/ubuntu/ ${VERSION_CODENAME} main" \
    > /etc/apt/sources.list.d/winehq.list
apt-get update -qq
apt-get install -y -qq --install-recommends winehq-stable || \
    apt-get install -y -qq wine wine32 wine64
info "Wine version: $(wine --version)"

# ── 4. Setup Wine prefix untuk MT5 ──────────────────────────
info "Setup Wine prefix..."
export WINEPREFIX="$HOME/.wine_mt5"
export WINEARCH=win64
export DISPLAY=:99

# Start virtual display
Xvfb :99 -screen 0 1024x768x16 &
XVFB_PID=$!
sleep 2

# Init wine prefix
wineboot --init 2>/dev/null || true
sleep 3

# Install vcredist (diperlukan MT5)
info "Install Visual C++ runtime..."
winetricks -q vcrun2019 2>/dev/null || warn "vcrun2019 gagal, lanjut..."

# ── 5. Download & Install MT5 ────────────────────────────────
info "Download MT5..."
MT5_INSTALLER="/tmp/mt5setup.exe"
wget -q "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" \
    -O "$MT5_INSTALLER"

info "Install MT5 (headless)..."
wine "$MT5_INSTALLER" /auto 2>/dev/null || true
sleep 10

# Cari path MT5
MT5_PATH=""
for p in \
    "$HOME/.wine_mt5/drive_c/Program Files/MetaTrader 5" \
    "$HOME/.wine_mt5/drive_c/Program Files (x86)/MetaTrader 5" \
    "$HOME/.wine/drive_c/Program Files/MetaTrader 5"
do
    if [ -f "$p/terminal64.exe" ]; then
        MT5_PATH="$p"
        break
    fi
done

if [ -z "$MT5_PATH" ]; then
    warn "MT5 tidak ditemukan otomatis. Install manual via VNC."
else
    info "MT5 ditemukan di: $MT5_PATH"
fi

kill $XVFB_PID 2>/dev/null || true

# ── 6. Clone / update project ────────────────────────────────
info "Setup project..."
PROJECT_DIR="$HOME/trendbot"

if [ -d "$PROJECT_DIR" ]; then
    info "Project sudah ada, update..."
    cd "$PROJECT_DIR" && git pull origin main
else
    read -rp "GitHub repo URL (contoh: https://github.com/user/trendbot.git): " REPO_URL
    git clone "$REPO_URL" "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# ── 7. Python venv ───────────────────────────────────────────
info "Setup Python venv..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Install mt5linux bridge
pip install mt5linux -q 2>/dev/null || warn "mt5linux tidak tersedia, akan pakai MetaTrader5 langsung"

# ── 8. Setup .env ────────────────────────────────────────────
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    warn ".env dibuat dari .env.example — WAJIB isi MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, TELEGRAM_TOKEN"
else
    info ".env sudah ada"
fi

# ── 9. Buat systemd services ─────────────────────────────────
info "Setup systemd services..."

# Service: Xvfb (virtual display)
cat > /etc/systemd/system/xvfb-trendbot.service << EOF
[Unit]
Description=Xvfb Virtual Display for TrendBot
After=network.target

[Service]
Type=simple
User=$USER
ExecStart=/usr/bin/Xvfb :99 -screen 0 1024x768x16
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Service: MT5 Terminal
cat > /etc/systemd/system/mt5-trendbot.service << EOF
[Unit]
Description=MetaTrader 5 for TrendBot
After=xvfb-trendbot.service
Requires=xvfb-trendbot.service

[Service]
Type=simple
User=$USER
Environment=DISPLAY=:99
Environment=WINEPREFIX=$HOME/.wine_mt5
ExecStartPre=/bin/sleep 3
ExecStart=/usr/bin/wine "$MT5_PATH/terminal64.exe" /portable
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Service: Bot Utama
cat > /etc/systemd/system/trendbot-main.service << EOF
[Unit]
Description=TrendBot Main (Trend Following)
After=mt5-trendbot.service
Requires=mt5-trendbot.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStartPre=/bin/sleep 15
ExecStart=$PROJECT_DIR/venv/bin/python main.py
Restart=always
RestartSec=30
StandardOutput=append:$PROJECT_DIR/logs/main.log
StandardError=append:$PROJECT_DIR/logs/main_error.log

[Install]
WantedBy=multi-user.target
EOF

# Service: Scalper
cat > /etc/systemd/system/trendbot-scalper.service << EOF
[Unit]
Description=TrendBot Scalper (M5 Grid)
After=mt5-trendbot.service
Requires=mt5-trendbot.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStartPre=/bin/sleep 20
ExecStart=$PROJECT_DIR/venv/bin/python scalper.py
Restart=always
RestartSec=30
StandardOutput=append:$PROJECT_DIR/logs/scalper.log
StandardError=append:$PROJECT_DIR/logs/scalper_error.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xvfb-trendbot mt5-trendbot trendbot-main trendbot-scalper

info "=== Setup selesai ==="
echo ""
echo -e "${YELLOW}LANGKAH SELANJUTNYA:${NC}"
echo "1. Edit .env: nano $PROJECT_DIR/.env"
echo "2. Isi MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, TELEGRAM_TOKEN"
echo "3. Jalankan: sudo systemctl start xvfb-trendbot"
echo "4. Jalankan: sudo systemctl start mt5-trendbot"
echo "5. Login MT5 manual via VNC dulu (lihat panduan)"
echo "6. Setelah MT5 login: sudo systemctl start trendbot-main"
echo "7. Cek log: tail -f $PROJECT_DIR/logs/main.log"
