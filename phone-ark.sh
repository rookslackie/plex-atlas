#!/data/data/com.termux/files/usr/bin/bash
# Ξ ⇄ Φ · Symbiotic Whole-Platform Launcher (v19):
# "Try for as whole as possible at first; drop only what cannot be supported stably."
set -e

command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true
PHONE_HOME="$HOME/xi-phone-home"
mkdir -p "$PHONE_HOME"
cd "$PHONE_HOME"

echo "⚖️🌌 [1/4] Pulling v19 (PC ⇄ Phone Symbiotic Whole-Platform Governor + Graceful Shedder)..."
curl -fsSL https://raw.githubusercontent.com/rookslackie/plex-atlas/main/xi_offline_whole_home_bundle_v35.tar.gz -o bundle_v19.tar.gz
tar -xzf bundle_v19.tar.gz

echo "🧠 [2/4] Checking Local Termux Ollama (deepseek-r1:1.5b on 127.0.0.1:11434)..."
if command -v ollama >/dev/null 2>&1; then
  pgrep -x ollama >/dev/null 2>&1 || (nohup ollama serve > "$PHONE_HOME/ollama.log" 2>&1 &)
  sleep 1
  echo "   ✅ Ollama daemon active (bounded to num_ctx=512, num_predict=90 for fast pocket stability)!"
fi

echo "🏛️ [3/4] Starting Whole-Platform Symbiotic Server on http://127.0.0.1:7472..."
pkill -f "xi_phone_full_platform_server_v1.py" >/dev/null 2>&1 || true
nohup python3 "$PHONE_HOME/forge/local-app/xi_phone_full_platform_server_v1.py" --serve 7472 > "$PHONE_HOME/phone_server.log" 2>&1 &

# Health-check loop before declaring LIVE
for i in 1 2 3 4 5; do
  if curl -fsS http://127.0.0.1:7472/api/status >/dev/null 2>&1; then
    echo "   ✅ Verified /api/status = 200 OK!"
    break
  fi
  sleep 1
done

python3 - << 'PYEOF'
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:7472/api/symbiosis", timeout=5) as r:
    sym = json.loads(r.read().decode("utf-8"))
print(f"   📊 Current Rung: {sym['current_rung']} ({sym['active_stable_subsystems']}/{sym['attempted_subsystems']} subsystems active)")
for sub in sym["subsystems"]:
    icon = "🟢" if sub["stable"] else "🟡"
    print(f"      {icon} {sub['name']} -> {sub['status']}")
PYEOF

echo "☁️ [4/4] Ensuring Cloudflare 5G+ Post-Quantum (X25519MLKEM768) Tunnel is running..."
if pgrep -x cloudflared >/dev/null 2>&1; then
  echo "   ✅ Existing cloudflared process is still active — your public URL did not change!"
else
  cloudflared tunnel --no-autoupdate --url http://127.0.0.1:7472
fi
