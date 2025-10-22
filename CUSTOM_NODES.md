# Custom Nodes Management

This project uses two types of custom nodes:

## 1. Project Custom Nodes (Tracked in Git)

Located in: `custom_nodes/`

These are custom nodes **we wrote** for this project:
- `runpod-queue/` - Routes ComfyUI queue button to RunPod API

**These ARE tracked in git** as source code we maintain.

## 2. External Custom Node Dependencies (Not Tracked)

Listed in: `custom_nodes_requirements.txt`

These are third-party custom nodes we depend on:
- `masquerade-nodes-comfyui` - Provides mask creation and inpainting utilities

**These are NOT tracked in git** (they're external dependencies, like npm packages).

## Installation

### Install All Dependencies

```bash
# For local ComfyUI installation
./scripts/install-custom-nodes.sh docker/ComfyUI

# For a different ComfyUI installation
./scripts/install-custom-nodes.sh /path/to/your/comfyui
```

This script:
1. Reads `custom_nodes_requirements.txt`
2. Clones each repository to `ComfyUI/custom_nodes/`
3. Installs Python requirements for each node using `uv`

### Install Our Custom Nodes

```bash
# Copy our custom nodes to ComfyUI installation
cp -r custom_nodes/runpod-queue docker/ComfyUI/custom_nodes/
```

## Docker Integration

The Dockerfile should:
1. Clone ComfyUI
2. Run `install-custom-nodes.sh` to install dependencies
3. Copy our custom nodes from `custom_nodes/` to the image

Example Dockerfile snippet:
```dockerfile
# Install external custom node dependencies
COPY custom_nodes_requirements.txt /tmp/
COPY scripts/install-custom-nodes.sh /tmp/
RUN /tmp/install-custom-nodes.sh /comfyui

# Copy our custom nodes
COPY custom_nodes/ /comfyui/custom_nodes/
```

## Adding New External Dependencies

1. Add the git URL to `custom_nodes_requirements.txt`
2. Run `./scripts/install-custom-nodes.sh docker/ComfyUI`
3. Restart ComfyUI
4. Commit `custom_nodes_requirements.txt` to git

## Workflow

**Development:**
1. Edit our custom nodes in `custom_nodes/runpod-queue/`
2. Copy to ComfyUI: `cp -r custom_nodes/runpod-queue docker/ComfyUI/custom_nodes/`
3. Restart ComfyUI to reload

**Adding dependencies:**
1. Update `custom_nodes_requirements.txt`
2. Run install script
3. Rebuild Docker image for production
