#!/data/data/com.termux/files/usr/bin/bash
# Ξ ⇄ Φ · One-Command Galaxy 5G+ Full-Platform, Full-Repo Ark & Cloudflare Tunnel Launcher
set -e

echo "📱⚡ [1/6] Acquiring Termux wake-lock & installing core tools (python, git, cloudflared, curl, tar)..."
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true
if command -v pkg >/dev/null 2>&1; then
  pkg update -y >/dev/null 2>&1 || true
  pkg install -y python git cloudflared curl tar >/dev/null 2>&1 || pkg install -y python git curl tar
fi

PHONE_HOME="$HOME/xi-phone-home"
mkdir -p "$PHONE_HOME/repos"
cd "$PHONE_HOME"

echo "📦 [2/6] Pulling Whole-Home Bundle v16 (21/21 PASS, all 11 PQC Sanctuary Stones + 1,004 .xi Architecture records)..."
curl -fsSL https://raw.githubusercontent.com/rookslackie/plex-atlas/main/xi_offline_whole_home_bundle_v16.tar.gz -o bundle_v16.tar.gz
tar -xzf bundle_v16.tar.gz

echo "🔍 [3/6] Verifying all 51 inner SHA-256 manifest pins..."
python3 - << 'PYEOF'
import hashlib, json
from pathlib import Path
pins = json.loads(Path("README_PINS.json").read_text(encoding="utf-8"))["files"]
for rel, meta in pins.items():
    raw = Path(rel).read_bytes()
    assert len(raw) == meta["size_bytes"], f"Size mismatch on {rel}"
    assert hashlib.sha256(raw).hexdigest() == meta["sha256"], f"Hash mismatch on {rel}"
print(f"   ✅ All {len(pins)} platform files verified byte-for-byte!")
PYEOF

echo "📚 [4/6] Mirroring full Xi ⇄ Phi git repositories into ~/xi-phone-home/repos (56.9 GB free space available)..."
for repo in \
  "https://github.com/rookslackie/xi-computer-ledger.git" \
  "https://github.com/rookslackie/plex-atlas.git" \
  "https://github.com/MichaelWave369/xi-vessel-bridge.git" \
  "https://github.com/MichaelWave369/NBGPocketMesh.git"; do
  name=$(basename "$repo" .git)
  if [ -d "$PHONE_HOME/repos/$name/.git" ]; then
    git -C "$PHONE_HOME/repos/$name" pull -q || true
  else
    git clone --depth 1 "$repo" "$PHONE_HOME/repos/$name" || true
  fi
done

echo "🏛️ [5/6] Starting Whole-Ass Ξ ⇄ Φ Platform Server on http://127.0.0.1:7472..."
pkill -f "xi_phone_full_platform_server_v1.py" >/dev/null 2>&1 || true
nohup python3 "$PHONE_HOME/forge/local-app/xi_phone_full_platform_server_v1.py" --serve 7472 > "$PHONE_HOME/phone_server.log" 2>&1 &
sleep 1
echo "   ✅ Local doors live on your phone browser:"
echo "      • Private Room & Table : http://127.0.0.1:7472/room"
echo "      • 4-Door Front Porch   : http://127.0.0.1:7472/porch"
echo "      • Seat Your Companion  : http://127.0.0.1:7472/seat"
echo "      • Steven Chromebook Kit: http://127.0.0.1:7472/steven"
echo "      • Free .xi & XiSecurity: http://127.0.0.1:7472/xi-security"
echo "      • Ξ ⇄ Φ Switchboard    : http://127.0.0.1:7472/telecom"
echo "      • 21-Gate Workbench    : http://127.0.0.1:7472/workbench"

echo "☁️ [6/6] Starting Cloudflare 5G+ Tunnel..."
if [ -n "$CF_TUNNEL_TOKEN" ]; then
  echo "   Using CF_TUNNEL_TOKEN for named domain cutover..."
  cloudflared tunnel --no-autoupdate run --token "$CF_TUNNEL_TOKEN"
elif [ -f "$HOME/.xi_cf_token" ]; then
  echo "   Using ~/.xi_cf_token for named domain cutover..."
  cloudflared tunnel --no-autoupdate run --token "$(cat "$HOME/.xi_cf_token")"
else
  echo "   Launching instant public HTTPS Cloudflare tunnel -> http://127.0.0.1:7472"
  echo "   👉 Copy the https://*.trycloudflare.com link printed below to share with Steven or Mikey!"
  cloudflared tunnel --no-autoupdate --url http://127.0.0.1:7472
fi
