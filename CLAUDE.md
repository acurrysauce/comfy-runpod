# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project implements a production-ready ComfyUI deployment system that works both locally and on RunPod serverless infrastructure. The system:

- Maintains a **local ComfyUI installation** mirroring the production environment
- Packages ComfyUI + custom nodes into **Docker images** for fast cold starts
- Stores **models on network storage** (RunPod volumes) for cost efficiency
- Provides an **API handler** for serverless inference with comprehensive debugging
- Uses **runpodctl** for syncing files between local and network storage
- Uses **uv** for all Python dependency management (local and Docker)
- Automatically routes local ComfyUI queue button to RunPod API endpoint

**Key Design Goals:**
- **Fast startup**: Pre-install all dependencies and custom nodes in Docker image (no runtime cloning/pip installs)
- **Cost efficiency**: Store models on network storage shared across workers
- **Debuggability**: Extensive logging and error reporting for production debugging
- **Local/remote parity**: Local setup mirrors production configuration exactly
- **Non-invasive**: ComfyUI modifications done via runtime patching, not code edits

**Reference Implementation:** `~/comfy-serverless` contains a working but poorly structured implementation. This project is a comprehensive refactor with best practices.

## Architecture

### High-Level System Design

```
┌─────────────────────────────────────────────────────────────────┐
│                      LOCAL ENVIRONMENT                           │
├─────────────────────────────────────────────────────────────────┤
│  ComfyUI Installation (managed by uv)                           │
│  ├── /path/to/comfyui/                                          │
│  ├── custom_nodes/ (each with requirements.txt)                 │
│  ├── input/ (all inputs, including subdirs like input/masks/)   │
│  └── .venv/ (shared venv for ComfyUI + all custom nodes)        │
│                                                                   │
│  Models (External Directory)                                     │
│  └── /external/models/                                           │
│      ├── checkpoints/                                            │
│      ├── loras/                                                  │
│      └── ...                                                     │
│                                                                   │
│  Proxy Launcher (runtime patching)                              │
│  └── launch_comfy_with_api.py                                   │
│      ├── Starts ComfyUI                                          │
│      ├── Patches queue execution                                 │
│      └── Routes to RunPod API when "Queue Prompt" clicked       │
│                                                                   │
│  File Sync (runpodctl)                                           │
│  └── Syncs to RunPod network storage                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓ sync via runpodctl
┌─────────────────────────────────────────────────────────────────┐
│                        RUNPOD DEPLOYMENT                         │
├─────────────────────────────────────────────────────────────────┤
│  Docker Container                                                │
│  ├── ComfyUI (baked into image, managed by uv)                  │
│  ├── custom_nodes/ (pre-installed with deps via uv)             │
│  ├── input/ (runtime inputs from requests)                      │
│  ├── handler.py (API endpoint - starts ComfyUI on init)         │
│  └── model_paths.yaml -> points to network volume               │
│                                                                   │
│  Network Volume (mounted at /runpod-volume)                     │
│  └── /runpod-volume/comfyui/models/                             │
│      ├── checkpoints/                                            │
│      ├── loras/                                                  │
│      └── ... (shared across all workers)                        │
└─────────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

#### 1. Docker Image Strategy: "Fat Images, Fast Starts"

**Problem:** Cloning repos and running pip install during container startup adds 30-60s of latency.

**Solution:** Pre-bake everything into the Docker image at build time using uv:
- Clone ComfyUI and all custom nodes during `docker build`
- Run `uv pip install -r requirements.txt` for ComfyUI and all custom nodes in Dockerfile
- Copy handler and utilities into image
- Result: Container starts in <5s (only ComfyUI server startup needed)

**Trade-off Analysis:**
- ✅ **Faster cold starts:** 30-60s → <5s startup time
- ✅ **More reliable:** No network failures during startup
- ✅ **Reproducible:** Same dependencies every time
- ⚠️ **Larger images:** ~10-15GB (acceptable for serverless)
- ⚠️ **Rebuild to update:** Must rebuild image to change custom nodes

**Verdict:** Correct choice for production serverless - cold start time is critical, storage is cheap.

#### 2. Model Storage Strategy: Network Volumes

**Problem:** Models are large (2-10GB each). Baking into image makes deploys slow and wastes storage.

**Solution:** Store models on RunPod network volumes:
- **Serverless endpoints**: Network volume mounted at `/runpod-volume/comfyui/models/`
- **Pods (for testing)**: Network volume mounted at `/workspace/comfyui/models/`
- `model_paths.yaml` configures ComfyUI to discover models there
- Models persist across worker restarts
- Multiple workers share the same volume

**Important Path Difference:**
```yaml
# For serverless endpoints (production):
base_path: /runpod-volume/comfyui/models/

# For pods (testing/development):
base_path: /workspace/comfyui/models/
```

**Local Mirroring:**
- Local ComfyUI uses `extra_model_paths.yaml` pointing to external directory
- Same structure as production (`/external/models/checkpoints/`, etc.)
- Use runpodctl to sync local models to network storage

#### 3. Handler Design: Start ComfyUI on Worker Initialization

**Problem:** Starting ComfyUI server on first request adds 10-20s overhead to the first request.

**Solution:** Start ComfyUI during worker initialization, not on first request:
- Handler starts ComfyUI subprocess immediately when worker starts
- ComfyUI is ready before first request arrives
- Server stays running for the lifetime of the worker
- Requests queue workflows via HTTP to localhost:8188
- Handler monitors health and restarts ComfyUI if crashed

**Implementation Pattern:**
```python
# Start ComfyUI immediately on worker start, not on first request
comfyui_process = None

def initialize_worker():
    """Called once when worker starts - before any requests."""
    global comfyui_process
    print("Initializing worker - starting ComfyUI...")
    start_comfyui_server()
    wait_for_health_check()
    print("Worker ready - ComfyUI is running")

def handler(event):
    """Handle incoming requests - ComfyUI already running."""
    ensure_comfyui_running()  # Check health, restart if crashed
    queue_prompt(workflow)
    return wait_for_completion()

# Call initialize on module load (worker start)
initialize_worker()
```

**Benefits:**
- ✅ First request has zero ComfyUI startup overhead
- ✅ Models pre-loaded in VRAM (if min_workers > 0)
- ✅ Consistent request latency (no "cold" first request)

#### 4. Debugging Strategy: Comprehensive Logging + Error Returns

**Problem:** RunPod logs are hard to access (web UI only, no streaming). When workflows fail, debugging is painful.

**Solution:** Multi-layered debugging approach:

1. **Extensive logging to stdout:**
   - ComfyUI stdout/stderr redirected to handler logs
   - Log directory contents (verify models present)
   - Log health checks and API responses
   - Log workflow validation (check files exist)
   - Log execution progress from ComfyUI

2. **Return errors in response:**
   - Don't just log errors - include in JSON response
   - Return full tracebacks in error responses
   - Include diagnostic info (loaded models, directory listings)

3. **Health monitoring:**
   - Poll ComfyUI `/system_stats` endpoint
   - Detect server crashes and report
   - Timeout detection with informative errors

4. **ComfyUI restart capability:**
   - Detect if ComfyUI process crashed
   - Automatically restart server if not responding
   - Log restart events with diagnostic info

**Example Error Response Structure:**
```python
{
  "status": "error",
  "error": "Workflow execution failed",
  "details": "Model not found: model.safetensors",
  "diagnostic_info": {
    "available_models": ["model1.safetensors", "model2.safetensors"],
    "comfyui_status": "running",
    "last_log_lines": ["...", "..."]
  },
  "traceback": "..."
}
```

#### 5. File Transfer Strategy: Zip + Sync Scripts

**Problem:** Transferring many small files via runpodctl is slow (each file is a separate transfer).

**Solution:** Batch transfer with zip archives and automated extraction:

**runpodctl Correct Syntax:**
```bash
# Generate transfer code
runpodctl send /local/path/to/file.zip

# This outputs a transfer code like: "1234-alpha-bravo-charlie"
# On the receiving end (RunPod pod/worker):
runpodctl receive 1234-alpha-bravo-charlie
```

**Automated Zip-Extract Pattern:**
```bash
# Local: Create zip that extracts from root, preserving structure
cd /local/models
zip -r models.zip checkpoints/ loras/ vae/

# Transfer and extract via Python script
python scripts/sync-models.py /local/models NETWORK_VOLUME_ID

# Script handles:
# 1. Zipping from local directory
# 2. Transferring via runpodctl
# 3. Extracting to correct location on remote
# 4. Verification
```

**Unzip from Root Requirement:**
The sync script will create a Python extraction script that can be run from any location and will automatically extract to the correct absolute paths, preserving directory structure.

#### 6. Input File Management Strategy

**Problem:** ComfyUI needs to access reference images, masks, and other inputs. How to organize them?

**Solution:** Use ComfyUI's `input/` directory with subdirectories:

**Directory Structure:**
```
/comfyui/input/
├── reference_image_1.png
├── reference_image_2.png
├── masks/
│   ├── irregular_horizontal.png
│   └── stone_patches.png
└── textures/
    └── base_texture.png
```

**Loading from Subdirectories:**
ComfyUI's standard `LoadImage` node doesn't support subdirectories by default, but:
- **Workaround 1**: Use custom nodes like `comfyui-loadimagewithsubfolder` that add subfolder support
- **Workaround 2**: Use relative paths like `masks/irregular_horizontal.png` (works with some custom nodes)
- **Recommended**: Install a subfolder-aware LoadImage custom node in the Docker image

**Handler Implementation:**
```python
# Save all input images to /comfyui/input/
for filename, base64_data in reference_images.items():
    # Support subdirectories: "masks/mask1.png" -> /comfyui/input/masks/mask1.png
    full_path = os.path.join(COMFYUI_INPUT, filename)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'wb') as f:
        f.write(base64.b64decode(base64_data))
```

**Local Environment:**
Local ComfyUI should mirror this structure - all inputs in `input/` directory with same subdirectory organization.

#### 7. Virtual Environment Strategy: Single Shared venv

**Problem:** Should each custom node have its own venv, or one shared venv for all?

**Solution:** Use single shared virtual environment for ComfyUI + all custom nodes:
- Standard ComfyUI practice: one venv per ComfyUI installation
- All custom nodes install requirements into the shared venv
- Managed by `uv` for fast, reproducible installs

**Why Not Per-Node venvs:**
- ComfyUI doesn't support isolated per-node environments
- Dependency conflicts must be resolved manually
- Trade-off: easier management vs potential version conflicts

**uv Project Structure:**
```
/comfy-runpod/
├── pyproject.toml          # Main project config (uv init here)
├── uv.lock                  # Lock file for reproducible builds
└── docker/
    ├── ComfyUI/
    │   ├── requirements.txt
    │   └── custom_nodes/
    │       ├── node1/
    │       │   └── requirements.txt
    │       └── node2/
    │           └── requirements.txt
    └── Dockerfile           # Uses uv for all installs
```

**Note:** The ComfyUI installation itself doesn't need a separate `uv init` - it uses the venv created by the main project's uv environment.

#### 8. Local ComfyUI Queue Button → RunPod API

**Problem:** Want to use local ComfyUI UI but execute on RunPod API without modifying ComfyUI installation.

**Solution:** Launch ComfyUI via wrapper script that patches execution at runtime:

**Architecture:**
```
User clicks "Queue Prompt" in ComfyUI UI
    ↓
Patched queue handler (injected at runtime)
    ↓
POST workflow to RunPod API endpoint
    ↓
Poll for completion
    ↓
Download results to local output/
    ↓
Auto-open images
```

**Implementation Approach:**
Create `scripts/launch_comfy_with_api.py` that:
1. Imports ComfyUI modules
2. Monkey-patches the queue handler before starting server
3. Intercepts `/prompt` POST requests
4. Routes to RunPod API instead of local execution
5. Polls for results and saves to local `output/` directory
6. Opens results automatically

**Key Pattern (Custom Node with Server Hook):**
```python
# In scripts/launch_comfy_with_api.py or as a custom node
from server import PromptServer

@PromptServer.instance.routes.post('/prompt')
async def custom_prompt_handler(request):
    """Intercept queue requests and route to RunPod."""
    workflow = await request.json()

    # Send to RunPod API instead of local execution
    result = send_to_runpod_api(workflow)

    # Download and open results
    download_and_open_results(result)

    return web.json_response({"status": "submitted_to_runpod"})
```

**Alternative Approach (Proxy Server):**
Run a local proxy server on port 8188 that:
- Accepts ComfyUI UI connections
- Forwards `/prompt` requests to RunPod API
- Proxies all other requests to ComfyUI on different port (e.g., 8189)

**Benefits:**
- ✅ No modification to ComfyUI installation (survives upgrades)
- ✅ Can toggle between local and remote execution
- ✅ Seamless UI experience
- ✅ Automatic result handling

### Component Breakdown

#### Docker Container Components

1. **ComfyUI Server** (`/comfyui/`)
   - Full ComfyUI installation managed by uv
   - Pre-installed custom nodes in `/comfyui/custom_nodes/`
   - Runs via: `python main.py --listen 0.0.0.0 --port 8188 --extra-model-paths-config /model_paths.yaml`
   - Started immediately on worker initialization

2. **Handler** (`/handler.py`)
   - RunPod serverless entry point
   - Starts ComfyUI on worker initialization (not first request)
   - Queues workflows via HTTP API
   - Monitors execution and collects outputs
   - Returns results or detailed errors

3. **Configuration** (`/model_paths.yaml`)
   - ComfyUI model discovery configuration
   - Points to network volume mount point (`/runpod-volume/comfyui/models/`)
   - Structured by model type (checkpoints, loras, etc.)

4. **Utilities** (`/utils.py`)
   - Model download helpers (HTTP, S3)
   - S3 upload for results
   - Cleanup utilities
   - Reusable helper functions

#### Local Environment

1. **ComfyUI Installation**
   - Standard ComfyUI clone
   - Custom nodes installed (must match production)
   - Uses `extra_model_paths.yaml` pointing to external directory
   - Managed by uv virtual environment

2. **Models Directory** (external to ComfyUI)
   - Same structure as RunPod network volume
   - Synced via runpodctl
   - Example: `/home/user/models/` with subdirs

3. **Launcher Script** (`scripts/launch_comfy_with_api.py`)
   - Starts ComfyUI with runtime patches
   - Routes queue button to RunPod API
   - Handles result downloading and opening

4. **Sync Scripts**
   - `scripts/sync-models.py` - Automated zip, transfer, extract
   - Uses runpodctl for transfer
   - Python-based for cross-platform compatibility

## Development Commands

### Setup

#### Project Initialization
```bash
# Initialize uv project at root
cd /home/acurry/comfy-runpod
uv init

# Install project dependencies
uv sync
```

#### Local ComfyUI Installation
```bash
# Clone ComfyUI
git clone https://github.com/comfyanonymous/ComfyUI.git local-comfy
cd local-comfy

# Create virtual environment with uv
uv venv

# Install ComfyUI dependencies
uv pip install -r requirements.txt

# Install custom nodes
cd custom_nodes
git clone <custom-node-repo>
cd <custom-node-name>
uv pip install -r requirements.txt

# Configure model paths
cp /path/to/extra_model_paths.yaml .
# Edit extra_model_paths.yaml to point to your local models directory
```

#### Docker Environment Setup
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install runpodctl
wget https://github.com/runpod/runpodctl/releases/latest/download/runpodctl-linux-amd64
chmod +x runpodctl-linux-amd64
sudo mv runpodctl-linux-amd64 /usr/local/bin/runpodctl

# Authenticate runpodctl (uses RUNPOD_API_KEY from environment)
runpodctl config
```

### Running

#### Run ComfyUI Locally (Standard)
```bash
cd local-comfy
source .venv/bin/activate
python main.py --listen 127.0.0.1 --port 8188 --extra-model-paths-config extra_model_paths.yaml

# Access UI at http://localhost:8188
```

#### Run ComfyUI Locally (with RunPod API Routing)
```bash
# Launch ComfyUI with API routing enabled
python scripts/launch_comfy_with_api.py

# Now clicking "Queue Prompt" in UI will:
# 1. Send workflow to RunPod API
# 2. Poll for completion
# 3. Download results
# 4. Open images automatically
```

#### Run Handler Locally (in Docker)
```bash
# Build image (uses defaults: curryberto/comfyui-serverless:latest)
./scripts/build.sh

# Run with mounted models
docker run --rm -it \
  --gpus all \
  -v /path/to/local/models:/runpod-volume/comfyui/models:ro \
  -p 8188:8188 \
  curryberto/comfyui-serverless:latest
```

#### Test Handler with Mock Input
```bash
# Run container interactively
docker run --rm -it \
  --gpus all \
  -v /path/to/local/models:/runpod-volume/comfyui/models:ro \
  --entrypoint /bin/bash \
  curryberto/comfyui-serverless:latest

# Inside container
python -c "
from handler import handler
import json

event = {
  'input': {
    'workflow': json.load(open('/path/to/workflow.json')),
    'return_base64': False
  }
}
result = handler(event)
print(result)
"
```

### Testing

#### Validate Handler Locally
```bash
# Run test script with mock RunPod environment
python scripts/test-handler.py
```

#### Test Workflow Execution
```bash
# Submit workflow to local handler
python scripts/test-local.py \
  --workflow workflows/test.json \
  --images input/ \
  --output ./outputs/
```

#### Test on RunPod
```bash
# Submit to RunPod endpoint (uses RUNPOD_ENDPOINT_ID from environment)
python scripts/send-to-runpod.py \
  --workflow workflows/test.json \
  --images input/ \
  --output ./outputs/
```

### Building

#### Build Docker Image
```bash
# Build with defaults (curryberto/comfyui-serverless:latest)
./scripts/build.sh

# Build with custom tag
./scripts/build.sh --tag v1.0.0

# Build without cache (clean build)
./scripts/build.sh --no-cache
```

**Script defaults:**
- Registry: `curryberto`
- Image name: `comfyui-serverless`
- Default tag: `latest`
- All are parameterizable but these are the defaults

#### Push to Registry
```bash
# Push with defaults (curryberto/comfyui-serverless:latest)
./scripts/push.sh

# Push with custom tag
./scripts/push.sh --tag v1.0.0

# Push to different registry (override default)
./scripts/push.sh --registry myregistry --tag v1.0.0
```

### Syncing Models to RunPod

#### Automated Sync (Recommended)
```bash
# Sync all models with automatic zipping, transfer, and extraction
python scripts/sync-models.py /local/models NETWORK_VOLUME_ID

# Process:
# 1. Creates zip from local models directory
# 2. Generates runpodctl send code
# 3. Provides receive command for RunPod side
# 4. (On RunPod) Extracts to correct location automatically
# 5. Verifies files transferred correctly
# 6. Cleans up temporary zip file
```

**Implementation Details:**
The sync script will:
- Accept local directory and RunPod volume ID as arguments
- Create zip with `cd /local/models && zip -r models.zip ./*`
- Run `runpodctl send models.zip` and capture transfer code
- Generate extraction script that can run from any location
- Extraction script uses absolute paths: `/runpod-volume/comfyui/models/`
- Print instructions for receiving and extracting on RunPod side

**Example output:**
```
Creating zip archive from /home/user/models...
Compressed 17 files (17.5 GB) → models.zip (16.8 GB)

Initiating transfer...
Transfer code: 1234-alpha-bravo-charlie

On your RunPod pod/worker, run:
  runpodctl receive 1234-alpha-bravo-charlie
  python extract_models.py

Files will be extracted to: /runpod-volume/comfyui/models/
```

#### Manual Sync
```bash
# Create zip
cd /local/models
zip -r models.zip checkpoints/ loras/ vae/

# Transfer (generates code)
runpodctl send models.zip
# Output: "Transfer code: 1234-alpha-bravo-charlie"

# On RunPod pod (via SSH)
runpodctl receive 1234-alpha-bravo-charlie
cd /runpod-volume/comfyui/models
unzip -o models.zip
```

## Key Patterns and Conventions

### Configuration Management

**All project defaults should be parameterizable but have these defaults:**

```python
# config.py
import os
from dataclasses import dataclass

@dataclass
class ProjectDefaults:
    """Project-wide defaults."""
    # Docker
    DOCKER_REGISTRY: str = os.getenv("DOCKER_REGISTRY", "curryberto")
    DOCKER_IMAGE: str = os.getenv("DOCKER_IMAGE", "comfyui-serverless")
    DOCKER_TAG: str = os.getenv("DOCKER_TAG", "latest")

    # RunPod
    RUNPOD_API_KEY: str = os.getenv("RUNPOD_API_KEY", "")
    RUNPOD_ENDPOINT_ID: str = os.getenv("RUNPOD_ENDPOINT_ID", "")

    # Paths
    MODELS_PATH_SERVERLESS: str = "/runpod-volume/comfyui/models"
    MODELS_PATH_POD: str = "/workspace/comfyui/models"
    COMFYUI_INPUT: str = "/comfyui/input"
    COMFYUI_OUTPUT: str = "/comfyui/output"

    @property
    def docker_image_full(self):
        return f"{self.DOCKER_REGISTRY}/{self.DOCKER_IMAGE}:{self.DOCKER_TAG}"

# Usage in scripts
config = ProjectDefaults()
print(f"Building {config.docker_image_full}")
```

**All scripts should use these defaults:**
- `scripts/build.sh` - uses `curryberto/comfyui-serverless:latest`
- `scripts/push.sh` - uses `curryberto/comfyui-serverless:latest`
- `scripts/send-to-runpod.py` - uses `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID` from env

### Handler Implementation Patterns

#### 1. Worker Initialization Pattern
```python
# Global state
comfyui_process = None
server_ready = False

def initialize_worker():
    """Initialize worker - called once on worker start."""
    global comfyui_process, server_ready

    print("=== WORKER INITIALIZATION ===")
    print(f"Models path: {MODELS_PATH}")

    # Start ComfyUI immediately
    comfyui_process = subprocess.Popen([...])

    # Wait for health check
    server_ready = wait_for_health_check(timeout=30)

    if server_ready:
        print("Worker ready - ComfyUI is running")
    else:
        raise RuntimeError("Failed to start ComfyUI during initialization")

def handler(event):
    """Handle requests - ComfyUI already running."""
    ensure_comfyui_running()  # Health check, restart if needed
    queue_prompt(workflow)
    return wait_for_completion()

# Initialize immediately on module load
initialize_worker()
```

#### 2. Comprehensive Logging Pattern
```python
import logging
import sys

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def log_diagnostic_info():
    """Log extensive diagnostic information."""
    logger.info("=== DIAGNOSTIC INFO ===")

    # Log model availability
    logger.info("Available checkpoints:")
    for model in os.listdir(f"{MODELS_PATH}/checkpoints"):
        size_mb = os.path.getsize(os.path.join(MODELS_PATH, "checkpoints", model)) / (1024 * 1024)
        logger.info(f"  - {model} ({size_mb:.1f} MB)")

    # Log ComfyUI status
    try:
        stats = requests.get("http://localhost:8188/system_stats").json()
        logger.info(f"ComfyUI stats: {json.dumps(stats, indent=2)}")
    except Exception as e:
        logger.error(f"Failed to get ComfyUI stats: {e}")
```

#### 3. Error Response Pattern

**DO NOT include raw code in CLAUDE.md for complex patterns.**

Instead, reference the implementation:
- See `docker/handler.py` for error response structure
- See `docker/utils.py` for error handling utilities
- Key requirement: Return detailed diagnostic info in error responses

**Pattern description:**
Error responses must include:
- Error message and exception type
- Full traceback
- Diagnostic info: available models, directory listings, ComfyUI status
- System state: disk usage, memory usage, process status
- Recent ComfyUI log lines (last 50 lines)

#### 4. ComfyUI Output Capture Pattern

**Implementation reference:** See `docker/handler.py:capture_comfyui_output()`

**Pattern description:**
- Capture stdout/stderr from ComfyUI subprocess
- Use threading to read output without blocking
- Store recent lines in queue for error reporting
- Log all output with `[ComfyUI]` prefix
- Make last N lines available for diagnostic responses

### Workflow Validation Pattern

**Implementation reference:** See `docker/handler.py:validate_workflow()`

**Pattern description:**
Before executing workflows:
1. Parse workflow JSON and extract all node types
2. For each node, check required files exist:
   - CheckpointLoaderSimple → verify checkpoint in models/checkpoints/
   - LoraLoader → verify lora in models/loras/
   - LoadImage → verify image in input/
   - ControlNet → verify controlnet model exists
3. Log all validation checks
4. Raise ValidationError with list of missing files if any not found
5. Include available files in error message for debugging

### ComfyUI Restart Capability

**Implementation reference:** See `docker/handler.py:ensure_comfyui_running()`

**Pattern description:**
Check ComfyUI health on every request:
1. Verify process exists (`comfyui_process is not None`)
2. Verify process is alive (`poll() returns None`)
3. Verify server responds to health check (`GET /system_stats`)
4. If any check fails:
   - Log failure reason with diagnostics
   - Kill process if still running
   - Restart ComfyUI
   - Wait for health check
   - Return success/failure

### Local ComfyUI API Routing

**Implementation reference:** See `scripts/launch_comfy_with_api.py`

**Pattern description:**
Two possible approaches:

**Approach 1: Custom Node with Route Override**
- Create custom node that loads early
- Use `PromptServer.instance.routes.post('/prompt')` decorator
- Override default prompt handler
- Send workflow to RunPod API instead of local queue
- Poll for completion and download results
- Open images automatically

**Approach 2: Reverse Proxy**
- Start nginx/Python proxy on port 8188
- ComfyUI runs on different port (8189)
- Proxy intercepts `/prompt` POST → send to RunPod API
- All other requests → forward to local ComfyUI
- More complex but doesn't require custom node

**Recommended:** Approach 1 (custom node) - simpler, no additional services

## Critical Implementation Requirements

### 1. Use uv for All Python Dependency Management

**Local environment:**
```bash
# Initialize project
uv init

# Install dependencies
uv pip install package-name

# Sync from requirements
uv pip install -r requirements.txt
```

**Docker environment:**
```dockerfile
# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Create venv and install dependencies
RUN uv venv /comfyui/.venv
ENV VIRTUAL_ENV=/comfyui/.venv
ENV PATH="/comfyui/.venv/bin:$PATH"

# Install ComfyUI requirements
RUN uv pip install -r /comfyui/requirements.txt

# Install custom node requirements
RUN for req in /comfyui/custom_nodes/*/requirements.txt; do \
      if [ -f "$req" ]; then uv pip install -r "$req"; fi \
    done
```

### 2. ComfyUI Restart Capability

**Requirement:** Handler must detect and recover from ComfyUI crashes.

**Implementation:** See `docker/handler.py:ensure_comfyui_running()`

### 3. ComfyUI Output Capture

**Requirement:** All ComfyUI stdout/stderr must be logged and available for error diagnostics.

**Implementation:** See `docker/handler.py:capture_comfyui_output()`

### 4. Model Directory Verification

**Requirement:** Log all available models on every request for debugging.

**Implementation:** See `docker/handler.py:log_model_directory()`

### 5. Start ComfyUI on Worker Initialization

**Requirement:** ComfyUI must be running before first request arrives.

**Implementation:** Call `initialize_worker()` at module level, not in handler function.

### 6. Input Subdirectory Support

**Requirement:** Support organizing inputs in subdirectories like `input/masks/`.

**Implementation:**
- Install custom node with subfolder support (e.g., `comfyui-loadimagewithsubfolder`)
- Handler creates subdirectories when saving input files
- Workflows reference files with relative paths: `masks/mask1.png`

## Important Notes

### Docker Best Practices for Production

1. **Use uv instead of pip**: Faster, more reproducible builds
2. **Layer caching**: Order Dockerfile instructions from least to most frequently changed
3. **Dependency pinning**: Use `uv pip compile` to generate lock file
4. **BuildKit**: Use Docker BuildKit for faster builds
5. **Multi-stage builds**: Consider if final image size matters

**Example Dockerfile structure:**
```dockerfile
# syntax=docker/dockerfile:1.4
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

# Install system dependencies (changes rarely)
RUN apt-get update && apt-get install -y python3 curl

# Install uv (changes rarely)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy ComfyUI and custom nodes (changes occasionally)
COPY docker/ComfyUI /comfyui

# Install dependencies with uv (changes occasionally)
RUN uv venv /comfyui/.venv && \
    . /comfyui/.venv/bin/activate && \
    uv pip install -r /comfyui/requirements.txt && \
    for req in /comfyui/custom_nodes/*/requirements.txt; do \
        [ -f "$req" ] && uv pip install -r "$req"; \
    done

# Copy handler code (changes frequently)
COPY docker/handler.py /handler.py
COPY docker/utils.py /utils.py
COPY docker/config.py /config.py
COPY docker/model_paths.yaml /model_paths.yaml

ENV VIRTUAL_ENV=/comfyui/.venv
ENV PATH="/comfyui/.venv/bin:$PATH"

WORKDIR /
CMD ["python", "-u", "/handler.py"]
```

### Reference Implementation Analysis

The `~/comfy-serverless` project demonstrates a working implementation but has areas for improvement:

**What Works Well:**
- Network volume strategy for models
- Persistent ComfyUI server pattern
- Reference image upload via base64
- Comprehensive workflow collection

**Areas to Improve in This Refactor:**
- **Configuration**: Hardcoded paths → centralize to config module with environment variable overrides
- **Logging**: Print statements → structured logging with Python logging module
- **Error handling**: Generic exceptions → custom exception types with detailed context
- **Type safety**: No type hints → full type annotations
- **Testing**: Limited coverage → pytest suite
- **Code organization**: Monolithic handler.py → modular structure
- **Documentation**: Sparse docstrings → comprehensive documentation
- **Dependency management**: pip → uv for speed and reproducibility
- **Initialization timing**: First request → worker initialization
- **Project defaults**: Scattered → centralized with consistent defaults

### Environment Variables

**Required:**
- `RUNPOD_API_KEY` - RunPod API key for authentication
- `RUNPOD_ENDPOINT_ID` - RunPod endpoint ID for API calls

**Optional with Defaults:**
- `DOCKER_REGISTRY` - Docker registry (default: `curryberto`)
- `DOCKER_IMAGE` - Docker image name (default: `comfyui-serverless`)
- `DOCKER_TAG` - Docker image tag (default: `latest`)
- `EXECUTION_TIMEOUT` - Workflow execution timeout in seconds (default: `300`)
- `HEALTH_CHECK_INTERVAL` - Health check interval in seconds (default: `5`)
- `CLEANUP_AGE` - Output cleanup age in seconds (default: `3600`)

### Performance Considerations

1. **Cold Start Time**: Target <5 seconds
   - Pre-install all dependencies in Docker image ✅
   - Start ComfyUI on worker initialization ✅
   - Use uv for faster installs ✅
   - Consider min_workers=1 for zero cold starts

2. **Model Loading**: First request per worker loads models into VRAM (10-30s)
   - Keep workers alive between requests (min_workers=1)
   - Models pre-loaded if ComfyUI starts on worker init ✅
   - Consider model quantization for faster loading

3. **Request Latency**: Typical 5-60 seconds depending on:
   - Image resolution, sampling steps, ControlNet usage, LoRA usage

4. **Cost Optimization**:
   - Use network volumes (don't bake models) ✅
   - Set appropriate idle timeout (30-60 seconds)
   - Use min_workers=0 if latency tolerance allows cold starts
   - Use spot instances when available

### Security Considerations

1. **Input Validation**: Validate all workflow inputs
2. **File Access**: Restrict file access to designated directories
3. **Resource Limits**: Set memory and disk limits
4. **Secrets Management**: Use environment variables for API keys ✅
5. **Image Scanning**: Scan Docker images for vulnerabilities

## Feature Development Workflow

When adding a new feature to this project, follow this structured process:

### 1. Create a Feature Branch

```bash
git checkout -b feature/descriptive-feature-name
```

### 2. Create a Detailed Implementation Plan

Write an extremely detailed plan and save it to `/plans/feature-name.md`. The plan must include:

#### Plan Structure Requirements:

- **Overview**: Brief description of the feature and its goals
- **Phases**: Break down implementation into distinct phases
  - Each phase must end in a **testable state**
  - Each phase should be independently verifiable
  - Phases should build incrementally on each other
- **Technical Details**: For each phase, document:
  - Files to be created/modified
  - Functions/methods to implement
  - Data structures and their purposes
  - Integration points with existing systems
- **Alternatives Considered**: Document alternative approaches with pros/cons
- **Testing Strategy**: How each phase will be tested
- **Progress Tracking**: Checkboxes at the bottom (see format below)

#### Plan Review Process:

After writing the initial plan, engage in iterative back-and-forth to:
- Carefully review and solidify the approach
- Propose alternative implementations with trade-offs
- Refine phase boundaries and test criteria
- Ensure all edge cases are considered

The user will iteratively ask you to improve the plan. Do not proceed to implementation until the plan is approved.

#### Progress Tracking Format:

```markdown
## Implementation Progress

### Phase 1: [Phase Name]
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 2: [Phase Name]
- [ ] Implementation Complete
- [ ] Testing Complete

[... continue for all phases ...]
```

### 3. Implement One Phase at a Time

Follow this cycle for each phase:

#### 3a. Implementation
- Implement the current phase according to the plan
- Update the implementation checkbox in `/plans/feature-name.md` when complete

#### 3b. Testing Discussion
- Engage in back-and-forth about testing the phase
- Claude should explain:
  - What functionality to test
  - Expected behavior
  - Edge cases to verify
  - How to test it (locally, in Docker, on RunPod)
- User will perform manual testing and report results

#### 3c. Mark Testing Complete
- When user confirms testing is complete, update the testing checkbox
- Move to the next phase

### 4. Complete the Feature

After all phases are implemented and tested:
- Commit all changes with a descriptive message
- Create a pull request (if working with a team)
- Merge the feature branch into main when approved

### Important Notes

- **Never skip the planning phase** - it prevents rework and ensures thoughtful design
- **Each phase must be testable** - if you can't test it, the phase is poorly defined
- **Update checkboxes immediately** - don't batch updates, they track real-time progress
- **Testing is mandatory** - every phase must be tested before moving forward
- **Plans are living documents** - update them if implementation reveals needed changes
