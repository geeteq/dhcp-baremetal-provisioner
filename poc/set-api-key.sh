#!/bin/bash
# set-api-key.sh — open Anthropic console and write ANTHROPIC_API_KEY into .env

ENV_FILE="${1:-.env}"

echo "Opening Anthropic API keys page..."
open "https://console.anthropic.com/settings/keys" 2>/dev/null \
  || xdg-open "https://console.anthropic.com/settings/keys" 2>/dev/null \
  || echo "  → https://console.anthropic.com/settings/keys"

echo ""
printf "Paste your API key (sk-ant-...): "
read -r API_KEY

if [[ -z "$API_KEY" ]]; then
  echo "No key entered. Aborting."
  exit 1
fi

if [[ "$API_KEY" != sk-ant-* ]]; then
  echo "Warning: key doesn't look like an Anthropic key (expected sk-ant-...)"
  printf "Continue anyway? [y/N] "
  read -r confirm
  [[ "$confirm" == "y" ]] || exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "✗ $ENV_FILE not found. Run 'make setup' first."
  exit 1
fi

if grep -q "^ANTHROPIC_API_KEY=" "$ENV_FILE"; then
  sed -i.bak "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$API_KEY|" "$ENV_FILE" \
    && rm -f "${ENV_FILE}.bak"
  echo "✓ Updated ANTHROPIC_API_KEY in $ENV_FILE"
else
  echo "" >> "$ENV_FILE"
  echo "ANTHROPIC_API_KEY=$API_KEY" >> "$ENV_FILE"
  echo "✓ Added ANTHROPIC_API_KEY to $ENV_FILE"
fi
