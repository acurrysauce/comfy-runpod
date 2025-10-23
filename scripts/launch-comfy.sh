#!/bin/bash
set -e

# Launch ComfyUI with project-specific configuration
# - Input/output directories at project root
# - Models from project root models directory
# - Extra model paths configuration

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMFY_DIR="$PROJECT_ROOT/docker/ComfyUI"

echo "======================================"
echo "Launching ComfyUI"
echo "======================================"
echo "Project root:  $PROJECT_ROOT"
echo "ComfyUI dir:   $COMFY_DIR"
echo "Input dir:     $PROJECT_ROOT/input"
echo "Output dir:    $PROJECT_ROOT/output"
echo "Models dir:    $PROJECT_ROOT/models"
echo "======================================"
echo ""

# Check if ComfyUI exists
if [ ! -d "$COMFY_DIR" ]; then
    echo "ERROR: ComfyUI not found at $COMFY_DIR"
    echo "Please clone ComfyUI first:"
    echo "  cd docker"
    echo "  git clone https://github.com/comfyanonymous/ComfyUI.git"
    exit 1
fi

# Check if extra_model_paths.yaml exists
if [ ! -f "$COMFY_DIR/extra_model_paths.yaml" ]; then
    echo "WARNING: extra_model_paths.yaml not found"
    echo "Models will only be loaded from docker/ComfyUI/models/"
    echo ""
fi

# Change to ComfyUI directory
cd "$COMFY_DIR"

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "ERROR: Virtual environment not found at $COMFY_DIR/.venv"
    echo "Please create it first:"
    echo "  cd docker/ComfyUI"
    echo "  uv venv"
    echo "  uv pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

echo "Starting ComfyUI..."
echo ""

python main.py \
    --input-directory "$PROJECT_ROOT/input" \
    --output-directory "$PROJECT_ROOT/output" \
    --listen 0.0.0.0 \
    --port 8188 \
    "$@"
