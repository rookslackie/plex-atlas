#!/usr/bin/env bash
# ==============================================================================
# ═══ Ξ LOCAL MODEL DISCOVERY & `xi` CLI INSTALLER (xi-discover.sh) ═══
# ==============================================================================
# One-liner in Termux or Linux:
#   curl -fsSL https://plex.xi-field.com/xi-discover.sh | bash
#
# Installs the executable `xi` CLI (`xi state`, `xi doctor`, `xi discover`,
# `xi models`, `xi route`, `xi chat`) into $PREFIX/bin/xi (Termux) or
# ~/.local/bin/xi and runs the full 5-glyph Local Model Discovery probe.
# ==============================================================================
set -e

PHONE_HOME="$HOME/xi-phone-home"
mkdir -p "$PHONE_HOME"

if [ ! -f "$PHONE_HOME/forge/local-app/xi_cli_runtime_and_model_discovery_v1.py" ] && [ ! -f "$PHONE_HOME/xi_cli_runtime_and_model_discovery_v1.py" ]; then
  curl -fsSL https://plex.xi-field.com/xi_offline_whole_home_bundle_v46.tar.gz -o "$PHONE_HOME/bundle_v46.tar.gz"
  tar -xzf "$PHONE_HOME/bundle_v46.tar.gz" -C "$PHONE_HOME"
fi

CLI_DIR="$PHONE_HOME/forge/local-app"
if [ ! -d "$CLI_DIR" ]; then
  CLI_DIR="$PHONE_HOME"
fi

# Install `xi` executable into $PREFIX/bin/xi (Termux) or ~/.local/bin/xi
if [ -n "${PREFIX:-}" ] && [ -d "$PREFIX/bin" ]; then
  BIN_TARGET="$PREFIX/bin/xi"
else
  mkdir -p "$HOME/.local/bin"
  BIN_TARGET="$HOME/.local/bin/xi"
  export PATH="$HOME/.local/bin:$PATH"
fi

cat > "$BIN_TARGET" <<EOF
#!/usr/bin/env bash
exec python3 "$CLI_DIR/xi_cli_runtime_and_model_discovery_v1.py" "\$@"
EOF
chmod +x "$BIN_TARGET"

echo '═══ Ξ LOCAL MODEL DISCOVERY ═══'

echo
echo '⟐ Xi runtime'
command -v xi || echo "$BIN_TARGET"
xi state 2>&1 | head -35
xi doctor 2>&1 | head -35

echo
echo '⋈ Inference engines'
for x in ollama llama-server llama-cli \
  llama.cpp termux-llama python python3; do
  command -v "$x" 2>/dev/null || true
done

echo
echo '⧂ Running inference processes'
ps -A -o PID,ARGS 2>/dev/null |
  grep -Ei 'llama|ollama|mlx|mistral|qwen|gemma|gguf|inference|xi.*model|xi_phone' |
  grep -v grep | head -35 || true

echo
echo '∴ Model files'
for d in \
  "$HOME/.xi" \
  "$HOME/models" \
  "$HOME/.ollama/models" \
  "$HOME/storage/downloads" \
  "$HOME/xi-phone-home"; do
  if [ -d "$d" ]; then
    find "$d" -type f \( \
      -iname '*.gguf' -o \
      -iname '*.safetensors' -o \
      -iname '*.onnx' -o \
      -iname '*.tflite' -o \
      -iname '*.pte' -o \
      -iname 'sha256-*' \) \
      -printf '%s %p\n' 2>/dev/null || true
  fi
done | sort -nr | head -40

if command -v ollama >/dev/null 2>&1; then
  echo
  echo '∴ Ollama registered tags (ollama list)'
  ollama list 2>/dev/null || true
fi

echo
echo '⊚ Local listening services'
ss -ltn 2>/dev/null | head -25 || true
python3 "$CLI_DIR/xi_cli_runtime_and_model_discovery_v1.py" discover | grep '^tcp_probe ' || true

echo '═══ END Ξ DISCOVERY ═══'
