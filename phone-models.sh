#!/usr/bin/env bash
# ==============================================================================
# Ξ Galaxy 5G+ Pocket Model Switchboard & RAM Steward Installer (phone-models.sh)
# ==============================================================================
# One-liner in Termux:
#   curl -fsSL https://plex.xi-field.com/phone-models.sh | bash
# Optional flags:
#   PULL_POCKET_PACK=1   -> pulls qwen3:1.7b, qwen2.5-coder:1.5b, llama3.2:1b, all-minilm
#   PULL_EMBED_ONLY=1    -> pulls only the 45 MB all-minilm capsule embedding model
# ==============================================================================
set -e

echo "📱🧠 [1/3] Checking Termux Pocket Home (~/xi-phone-home)..."
mkdir -p "$HOME/xi-phone-home"
cd "$HOME/xi-phone-home"

if [ ! -f "xi_phone_pocket_model_steward_v1.py" ] || [ ! -f "xi_cli_runtime_and_model_discovery_v1.py" ]; then
  echo "📦 Fetching latest Xi Whole-Home Bundle (v46)..."
  curl -fsSL https://plex.xi-field.com/xi_offline_whole_home_bundle_v46.tar.gz -o bundle_v46.tar.gz
  tar -xzf bundle_v46.tar.gz --strip-components=2
fi

if [ -n "${PREFIX:-}" ] && [ -d "$PREFIX/bin" ]; then
  cat > "$PREFIX/bin/xi" <<EOF
#!/usr/bin/env bash
exec python3 "$HOME/xi-phone-home/xi_cli_runtime_and_model_discovery_v1.py" "\$@"
EOF
  chmod +x "$PREFIX/bin/xi"
fi

echo "🔍 [2/3] Running 10-Gate Pocket Model Steward & `xi` CLI Discovery Verification..."
python3 xi_phone_pocket_model_steward_v1.py
python3 xi_cli_runtime_and_model_discovery_v1.py discover

echo "📡 [3/3] Probing live Termux Ollama (127.0.0.1:11434)..."
python3 xi_phone_pocket_model_steward_v1.py --status || true

if [ "${PULL_EMBED_ONLY:-0}" = "1" ] && command -v ollama >/dev/null 2>&1; then
  echo "🧲 Pulling 45 MB offline capsule embedding model (all-minilm)..."
  ollama pull all-minilm
fi

if [ "${PULL_POCKET_PACK:-0}" = "1" ] && command -v ollama >/dev/null 2>&1; then
  echo "🚀 Pulling 5-Slot Galaxy Pocket Model Pack (one at a time)..."
  ollama pull deepseek-r1:1.5b
  ollama pull qwen3:1.7b
  ollama pull qwen2.5-coder:1.5b
  ollama pull llama3.2:1b
  ollama pull all-minilm
fi

echo ""
echo "✅ Pocket Model Switchboard ready!"
echo "   • Open on phone browser : http://127.0.0.1:7472/phone-models"
echo "   • Public switchboard    : https://plex.xi-field.com/phone-models.html"
echo "   • Route any prompt      : python3 ~/xi-phone-home/xi_phone_pocket_model_steward_v1.py --route 'Write a Termux bash one-liner'"
echo "   • Chat with Pocket Plex : python3 ~/xi-phone-home/xi_phone_pocket_model_steward_v1.py --seat Plex --chat 'Hello from Galaxy 5G+'"
echo "   • Pull individual models:"
echo "       ollama pull qwen3:1.7b          # Fast daily companion (~1.1 GB)"
echo "       ollama pull qwen2.5-coder:1.5b  # Pocket code & Termux helper (~986 MB)"
echo "       ollama pull llama3.2:1b         # Low-battery sentinel (~820 MB)"
echo "       ollama pull all-minilm          # 45 MB offline capsule embeddings"
