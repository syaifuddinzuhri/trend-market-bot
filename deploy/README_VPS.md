# Deploy TrendBot ke Linux VPS

## Arsitektur

```
Linux VPS (Ubuntu 22.04+)
├── Xvfb          → virtual display (MT5 butuh display)
├── Wine + MT5    → terminal MetaTrader 5
├── Python main.py    → bot trend utama (H4→M5)
└── Python scalper.py → bot scalping grid M5
```

---

## 1. Koneksi ke VPS

```bash
ssh root@IP_VPS_KAMU
```

---

## 2. Setup Otomatis

```bash
wget https://raw.githubusercontent.com/USER/REPO/main/deploy/setup_vps.sh
bash setup_vps.sh
```

Script akan install: Wine, Xvfb, Python, clone repo, buat systemd services.

---

## 3. Isi .env

```bash
nano ~/trendbot/.env
```

Isi minimal:
```
MT5_LOGIN=463533727
MT5_PASSWORD=Demo@1234
MT5_SERVER=Exness-MT5Trial17
SYMBOL=XAUUSDm
TELEGRAM_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

---

## 4. Login MT5 Manual (sekali saja)

MT5 perlu login manual pertama kali via VNC:

```bash
# Install VNC viewer di laptop kamu, lalu:
sudo apt install x11vnc -y
x11vnc -display :99 -nopw -listen 0.0.0.0 -xkb &
```

Buka VNC viewer → `IP_VPS:5900` → login MT5 → centang "Save password".

Setelah login tersimpan, MT5 akan auto-login setiap kali restart.

---

## 5. Start Services

```bash
cd ~/trendbot
bash deploy/manage.sh start
bash deploy/manage.sh status
```

Output:
```
  ✅ xvfb-trendbot          active
  ✅ mt5-trendbot           active
  ✅ trendbot-main          active
  ✅ trendbot-scalper       active
```

---

## 6. Monitor Log

```bash
# Bot utama
bash ~/trendbot/deploy/manage.sh logs main

# Scalper
bash ~/trendbot/deploy/manage.sh logs scalper
```

---

## 7. Update Bot (setelah git push dari Windows)

```bash
bash ~/trendbot/deploy/manage.sh update
```

Otomatis: `git pull` → install dependencies → restart bot.

---

## Perintah Berguna

```bash
# Status semua service
bash ~/trendbot/deploy/manage.sh status

# Stop semua
bash ~/trendbot/deploy/manage.sh stop

# Restart hanya bot (bukan MT5)
sudo systemctl restart trendbot-main trendbot-scalper

# Cek error
tail -f ~/trendbot/logs/main_error.log

# Cek MT5 running
systemctl status mt5-trendbot
```

---

## Troubleshooting

**MT5 tidak connect:**
```bash
# Pastikan Xvfb jalan
systemctl status xvfb-trendbot

# Restart MT5
sudo systemctl restart mt5-trendbot
sleep 15
sudo systemctl restart trendbot-main
```

**Bot error "MT5 initialize failed":**
- MT5 belum login (perlu VNC login sekali)
- MT5 crash → `sudo systemctl restart mt5-trendbot`

**Update .env tanpa restart MT5:**
```bash
sudo systemctl restart trendbot-main trendbot-scalper
```
