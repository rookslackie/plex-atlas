#!/data/data/com.termux/files/usr/bin/bash
# Ξ ⇄ Φ · Oct 25, 2025 -> Oct 25, 2026 1-Year Xi.Glyph Anniversary Launcher:
# Runs Local DeepSeek-R1:1.5B (:11434) + Audacious Pocket Cathedral (:7472) + Cloudflare 5G+ Tunnel Together!
set -e

command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true
PHONE_HOME="$HOME/xi-phone-home"
mkdir -p "$PHONE_HOME"
cd "$PHONE_HOME"

echo "📅🌌 [1/4] Pulling v18 (Oct 25, 2025 -> 2026 1-Year Xi.Glyph Anniversary + Pocket DeepSeek Bridge)..."
curl -fsSL https://raw.githubusercontent.com/rookslackie/plex-atlas/main/xi_offline_whole_home_bundle_v18.tar.gz -o bundle_v18.tar.gz
tar -xzf bundle_v18.tar.gz

echo "🧠 [2/4] Ensuring Termux Ollama (deepseek-r1:1.5b) is running in background on 127.0.0.1:11434..."
if command -v ollama >/dev/null 2>&1; then
  pgrep -f "ollama serve" >/dev/null 2>&1 || (nohup ollama serve > "$PHONE_HOME/ollama.log" 2>&1 &)
  sleep 1
  echo "   ✅ Local DeepSeek R1 Distill Qwen 1.5B is warm and wired to /api/room!"
fi

echo "🏛️ [3/4] Starting Audacious Pocket Cathedral & Private Room on http://127.0.0.1:7472..."
pkill -f "xi_phone_full_platform_server_v1.py" >/dev/null 2>&1 || true
nohup python3 "$PHONE_HOME/forge/local-app/xi_phone_full_platform_server_v1.py" --serve 7472 > "$PHONE_HOME/phone_server.log" 2>&1 &
sleep 1
echo "   ✅ Local Phone Doors:"
echo "      • 3D E47 & 169.5 BPM Cathedral : http://127.0.0.1:7472/cathedral"
echo "      • Private Room (with @DeepSeek): http://127.0.0.1:7472/room"
echo "      • Steven's Chromebook Helper   : http://127.0.0.1:7472/steven"

echo "☁️ [4/4] Launching Cloudflare 5G+ Post-Quantum (X25519MLKEM768) Tunnel..."
if pgrep -f "cloudflared tunnel" >/dev/null 2>&1; then
  echo "   ✅ cloudflared is already running!"
else
  cloudflared tunnel --no-autoupdate --url http://127.0.0.1:7472
fi
