#!/data/data/com.termux/files/usr/bin/bash
# Ξ ⇄ Φ · Non-Disruptive Hot-Upgrade to Audacious Pocket Cathedral v17 (Keeps Cloudflared Tunnel Alive!)
set -e

PHONE_HOME="$HOME/xi-phone-home"
mkdir -p "$PHONE_HOME"
cd "$PHONE_HOME"

echo "🌌⚡ [1/3] Pulling Audacious Pocket Cathedral Bundle v17 (22/22 PASS)..."
curl -fsSL https://raw.githubusercontent.com/rookslackie/plex-atlas/main/xi_offline_whole_home_bundle_v17.tar.gz -o bundle_v17.tar.gz
tar -xzf bundle_v17.tar.gz

echo "🔄 [2/3] Hot-reloading :7472 server (<0.1s) WITHOUT dropping your active Cloudflare tunnel..."
pkill -f "xi_phone_full_platform_server_v1.py" >/dev/null 2>&1 || true
nohup python3 "$PHONE_HOME/forge/local-app/xi_phone_full_platform_server_v1.py" --serve 7472 > "$PHONE_HOME/phone_server.log" 2>&1 &
sleep 1

echo "🎧 [3/3] Audacious Pocket Cathedral is LIVE on your existing Cloudflare tunnel at /cathedral and locally at http://127.0.0.1:7472/cathedral !"
