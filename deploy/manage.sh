#!/bin/bash
# ============================================================
# TrendBot Management Script
# Usage: bash manage.sh [start|stop|restart|status|logs|update]
# ============================================================

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC} $1"; }

SERVICES="xvfb-trendbot mt5-trendbot trendbot-main trendbot-scalper"
PROJECT_DIR="$HOME/trendbot"

case "$1" in
    start)
        info "Starting semua services..."
        for svc in $SERVICES; do
            sudo systemctl start "$svc"
            echo "  ✓ $svc"
        done
        ;;
    stop)
        info "Stopping semua services..."
        for svc in $(echo $SERVICES | tr ' ' '\n' | tac); do
            sudo systemctl stop "$svc" 2>/dev/null
            echo "  ✓ $svc stopped"
        done
        ;;
    restart)
        bash "$0" stop
        sleep 3
        bash "$0" start
        ;;
    status)
        echo ""
        for svc in $SERVICES; do
            status=$(systemctl is-active "$svc" 2>/dev/null)
            icon="✅"
            [ "$status" != "active" ] && icon="❌"
            printf "  %s %-30s %s\n" "$icon" "$svc" "$status"
        done
        echo ""
        ;;
    logs)
        target="${2:-main}"
        if [ "$target" = "main" ]; then
            tail -f "$PROJECT_DIR/logs/main.log"
        elif [ "$target" = "scalper" ]; then
            tail -f "$PROJECT_DIR/logs/scalper.log"
        else
            journalctl -u "trendbot-$target" -f
        fi
        ;;
    update)
        info "Update project dari GitHub..."
        cd "$PROJECT_DIR"
        git pull origin main
        source venv/bin/activate
        pip install -r requirements.txt -q
        info "Restart bot..."
        sudo systemctl restart trendbot-main trendbot-scalper
        info "Update selesai"
        ;;
    *)
        echo "Usage: bash manage.sh [start|stop|restart|status|logs|update]"
        echo ""
        echo "  start    — jalankan semua services"
        echo "  stop     — hentikan semua services"
        echo "  restart  — restart semua services"
        echo "  status   — cek status services"
        echo "  logs     — lihat log (default: main, atau scalper)"
        echo "  update   — git pull + restart bot"
        ;;
esac
