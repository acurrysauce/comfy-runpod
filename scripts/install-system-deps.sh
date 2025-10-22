#!/bin/bash
# Install system-level dependencies for ComfyUI custom nodes

set -e

REQUIREMENTS_FILE="system_requirements.txt"

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "Error: $REQUIREMENTS_FILE not found"
    exit 1
fi

echo "Installing system dependencies for ComfyUI custom nodes..."
echo "==========================================="
echo "This requires sudo access."
echo ""

# Read packages from file and install
sudo apt-get update
sudo apt-get install -y $(cat "$REQUIREMENTS_FILE")

echo ""
echo "==========================================="
echo "✓ System dependencies installed successfully"
echo ""
echo "Next step: Run ./scripts/install-custom-nodes.sh docker/ComfyUI"
