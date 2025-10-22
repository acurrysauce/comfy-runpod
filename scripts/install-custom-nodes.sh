#!/bin/bash
# Install custom node dependencies for ComfyUI
# Usage: ./scripts/install-custom-nodes.sh [path/to/ComfyUI]

set -e

COMFYUI_PATH="${1:-docker/ComfyUI}"
CUSTOM_NODES_DIR="$COMFYUI_PATH/custom_nodes"
REQUIREMENTS_FILE="custom_nodes_requirements.txt"

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "Error: $REQUIREMENTS_FILE not found"
    exit 1
fi

if [ ! -d "$COMFYUI_PATH" ]; then
    echo "Error: ComfyUI not found at $COMFYUI_PATH"
    exit 1
fi

echo "Installing custom nodes to: $CUSTOM_NODES_DIR"
echo "==========================================="

# Read requirements file and clone repos
while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue

    # Extract git URL (first word)
    git_url=$(echo "$line" | awk '{print $1}')

    # Extract repo name from URL
    repo_name=$(basename "$git_url" .git)

    target_dir="$CUSTOM_NODES_DIR/$repo_name"

    if [ -d "$target_dir" ]; then
        echo "✓ $repo_name already exists, pulling updates..."
        cd "$target_dir"
        git pull
        cd - > /dev/null
    else
        echo "→ Cloning $repo_name..."
        git clone "$git_url" "$target_dir"
    fi

    # Install requirements if present
    if [ -f "$target_dir/requirements.txt" ]; then
        echo "  Installing Python dependencies for $repo_name..."
        if ! uv pip install -r "$target_dir/requirements.txt"; then
            echo "  ⚠️  Warning: Failed to install dependencies for $repo_name"
            echo "      The node may require system packages. See error above."
        fi
    fi

    echo ""
done < "$REQUIREMENTS_FILE"

echo "==========================================="
echo "✓ All custom nodes installed successfully"
