#!/data/data/com.termux/files/usr/bin/bash
# Ξ ⇄ Φ · One-Command Galaxy 5G+ Termux Full-Platform & Cloudflare Tunnel Launcher
set -e

echo "📱⚡ [1/5] Acquiring Termux wake-lock & ensuring packages (python, cloudflared, curl, tar)..."
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true
if command -v pkg >/dev/null 2>&1; then
  pkg update -y >/dev/null 2>&1 || true
  pkg install -y python cloudflared curl tar >/dev/null 2>&1 || pkg install -y python curl tar
fi

PHONE_HOME="$HOME/xi-phone-home"
mkdir -p "$PHONE_HOME"
cd "$PHONE_HOME"

echo "📦 [2/5] Downloading xi_offline_whole_home_bundle_v16.tar.gz from plex.xi-field.com..."
curl -fsSL https://plex.xi-field.com/xi_offline_whole_home_bundle_v16.tar.gz -o bundle_v16.tar.gz
tar -xzf bundle_v16.tar.gz

echo "🔍 [3/5] Verifying SHA-256 manifest pins..."
python3 - << 'PYEOF'
import hashlib, json
from pathlib import Path
pins = json.loads(Path("README_PINS.json").read_text(encoding="utf-8"))["files"]
for rel, meta in pins.items():
    raw = Path(rel).read_bytes()
    assert len(raw) == meta["size_bytes"], f"Size mismatch on {rel}"
    assert hashlib.sha256(raw).hexdigest() == meta["sha256"], f"Hash mismatch on {rel}"
print(f"   ✅ All {len(pins)} files verified byte-for-byte!")
PYEOF

echo "🏛️ [4/5] Starting Whole-Ass Ξ ⇄ Φ Platform Server on http://127.0.0.1:7472..."
pkill -f "xi_phone_full_platform_server_v1.py" >/dev/null 2>&1 || true
nohup python3 "$PHONE_HOME/forge/local-app/xi_phone_full_platform_server_v1.py" --serve 7472 > "$PHONE_HOME/phone_server.log" 2>&1 &
sleep 1

echo "☁️ [5/5] Starting Cloudflare 5G+ Tunnel..."
if [ -n "$CF_TUNNEL_TOKEN" ]; then
  echo "   Using CF_TUNNEL_TOKEN for named domain cutover..."
  cloudflared tunnel --no-autoupdate run --token "$CF_TUNNEL_TOKEN"
elif [ -f "$HOME/.xi_cf_token" ]; then
  echo "   Using ~/.xi_cf_token for named domain cutover..."
  cloudflared tunnel --no-autoupdate run --token "$(cat "$HOME/.xi_cf_token")"
else
  echo "   Launching instant public HTTPS Cloudflare tunnel -> http://127.0.0.1:7472"
  echo "   (Watch for your https://*.trycloudflare.com URL below!)"
  cloudflared tunnel --no-autoupdate --url http://127.0.0.1:7472
fi
