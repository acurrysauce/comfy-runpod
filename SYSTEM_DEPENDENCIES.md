# System Dependencies for Custom Nodes

Some custom nodes require system packages to be installed before their Python dependencies can be installed.

## Required System Packages

All required system packages are listed in `system_requirements.txt`.

### Quick Install (Ubuntu/Debian)

```bash
# Option 1: Install from file
xargs -a system_requirements.txt sudo apt-get install -y

# Option 2: Manual install
sudo apt-get update && sudo apt-get install -y \
    pkg-config \
    libcairo2-dev \
    python3-cairo \
    cmake \
    libgl1-mesa-glx \
    libglib2.0-0
```

## Which Nodes Need These?

- **comfyui_controlnet_aux**: Requires `pkg-config`, `libcairo2-dev`, `cmake` for pycairo and other dependencies
- **ComfyUI_LayerStyle**: May require cairo for image processing
- **ComfyUI-Impact-Pack**: Requires OpenGL and glib

## Installation Order

1. **First**: Install system dependencies (above)
2. **Then**: Run `./scripts/install-custom-nodes.sh docker/ComfyUI`

## For Docker

These dependencies are already included in the Dockerfile.
