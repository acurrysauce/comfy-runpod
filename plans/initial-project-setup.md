# Initial Project Setup - Implementation Plan

## Overview

This feature establishes the foundational structure for the comfy-runpod project, implementing the core infrastructure needed for both local development and RunPod serverless deployment. The goal is to create a production-ready ComfyUI deployment system with:

- Complete project structure with uv dependency management
- Docker handler with worker initialization
- Configuration management with sensible defaults
- Build and deployment scripts
- Model sync utilities
- Local-to-RunPod API routing capability

This plan follows the architecture documented in CLAUDE.md and sets up the skeleton that all future features will build upon.

## Phases

### Phase 1: Project Foundation and Configuration

**Goal:** Set up basic project structure, uv initialization, and configuration module

**Files to Create:**
- `pyproject.toml` - uv project configuration
- `docker/config.py` - Configuration module with ProjectDefaults class
- `.gitignore` - Ignore venvs, outputs, etc.
- `README.md` - Basic project description and setup instructions

**Files to Modify:**
- None (initial setup)

**Technical Details:**

1. **Directory Structure:**
   ```
   /comfy-runpod/
   ├── pyproject.toml          # uv project config
   ├── .gitignore              # Git ignore patterns
   ├── README.md               # Project documentation
   ├── CLAUDE.md               # Already exists
   ├── docker/                 # Docker-related files
   ├── scripts/                # Utility scripts
   ├── workflows/              # ComfyUI workflow JSONs
   ├── plans/                  # Implementation plans
   ├── input/                  # Local input files
   └── output/                 # Local output files
   ```

2. **Configuration Module (`docker/config.py`):**
   - `ProjectDefaults` dataclass with all default values
   - Environment variable overrides for all settings
   - Properties for computed values (e.g., `docker_image_full`)
   - Separate configs for: Docker, RunPod, Paths, Handler settings
   - Type hints for all fields

3. **uv Initialization:**
   - Initialize project with `uv init`
   - Configure Python version (3.10+)
   - Set up basic dependencies: `runpod`, `requests`, `pillow`, `pyyaml`

**Integration Points:**
- Configuration module will be imported by all scripts and handler
- `.gitignore` prevents committing sensitive files and build artifacts

**Testing Strategy:**
- Verify uv project initializes correctly
- Import config.py and verify default values
- Override with environment variables and verify changes
- Check directory structure is created properly

**Testable State:**
- Project initializes with `uv sync`
- Can import and instantiate `ProjectDefaults`
- All directories exist
- No errors when running `uv pip list`

---

### Phase 2: Docker Handler with Worker Initialization

**Goal:** Create the RunPod serverless handler that starts ComfyUI on worker initialization

**Files to Create:**
- `docker/handler.py` - Main handler with worker initialization
- `docker/utils.py` - Utility functions (download, upload, cleanup)
- `docker/model_paths.yaml` - ComfyUI model path configuration

**Technical Details:**

1. **Handler Structure (`docker/handler.py`):**
   - Global variables: `comfyui_process`, `server_ready`, `comfyui_output_queue`
   - `initialize_worker()` - Called at module load to start ComfyUI
   - `start_comfyui_server()` - Subprocess management
   - `wait_for_health_check()` - Poll /system_stats until ready
   - `ensure_comfyui_running()` - Health check and restart logic
   - `capture_comfyui_output()` - Thread to capture stdout/stderr
   - `get_recent_comfyui_logs()` - Get last N log lines
   - `handler(event)` - Main request handler
   - `queue_prompt()` - POST workflow to ComfyUI API
   - `wait_for_completion()` - Poll for workflow completion
   - `validate_workflow()` - Check all required files exist
   - `log_diagnostic_info()` - Log models, status, directories
   - `create_error_response()` - Structured error responses

2. **Handler Flow:**
   ```
   Module load → initialize_worker() → start_comfyui_server() → wait_for_health_check()
                                                                         ↓
   Request arrives → handler(event) → ensure_comfyui_running() → validate_workflow()
                                                                         ↓
                                           queue_prompt() → wait_for_completion() → return results
   ```

3. **Utilities (`docker/utils.py`):**
   - `download_models()` - Download from URLs or S3
   - `download_file()` - HTTP file download with streaming
   - `download_from_s3()` - S3 file download
   - `upload_to_s3()` - Upload results to S3
   - `cleanup_outputs()` - Remove old output files

4. **Model Paths Configuration (`docker/model_paths.yaml`):**
   ```yaml
   comfyui:
     base_path: /runpod-volume/comfyui/models/
     checkpoints: checkpoints
     vae: vae
     loras: loras
     upscale_models: upscale_models
     embeddings: embeddings
     controlnet: controlnet
     clip_vision: clip_vision
   ```

**Integration Points:**
- Handler imports config.py for all path constants
- Handler imports utils.py for helper functions
- model_paths.yaml read by ComfyUI on startup

**Alternatives Considered:**

1. **Start ComfyUI on first request vs worker initialization:**
   - **First request**: Simpler, but adds 10-20s to first request
   - **Worker init** (chosen): Faster first request, more complex initialization
   - Decision: Worker init for better UX and consistent latency

2. **Logging approach:**
   - **Print statements**: Simple but unstructured
   - **Logging module** (chosen): Structured, filterable, production-ready
   - Decision: Use Python logging for better observability

3. **Error handling:**
   - **Generic exceptions**: Simple but loses context
   - **Custom exceptions**: More code but better debugging
   - **Detailed responses** (chosen): Include diagnostics in response
   - Decision: Return extensive diagnostics in error responses

**Testing Strategy:**
- Mock RunPod environment locally
- Test handler initialization without ComfyUI
- Test with ComfyUI running locally
- Verify health check retries and timeouts
- Test error responses include diagnostics
- Verify ComfyUI restart on crash

**Testable State:**
- Handler starts without errors (even if ComfyUI not present)
- Can call handler() with mock event
- Utilities can be imported and used independently
- model_paths.yaml is valid YAML
- All functions have proper error handling

---

### Phase 3: Dockerfile with uv and ComfyUI

**Goal:** Create production Dockerfile that bakes ComfyUI + custom nodes with uv

**Files to Create:**
- `docker/Dockerfile` - Multi-stage build with uv
- `docker/.dockerignore` - Exclude unnecessary files from build context

**Technical Details:**

1. **Dockerfile Structure:**
   ```dockerfile
   # Base image with CUDA support
   FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

   # Install system dependencies
   RUN apt-get update && apt-get install -y \
       python3 \
       python3-pip \
       curl \
       git \
       && rm -rf /var/lib/apt/lists/*

   # Install uv
   RUN curl -LsSf https://astral.sh/uv/install.sh | sh
   ENV PATH="/root/.local/bin:$PATH"

   # Clone ComfyUI (or COPY if pre-cloned)
   # This will need to be decided based on build strategy

   # Create venv and install dependencies
   RUN uv venv /comfyui/.venv
   ENV VIRTUAL_ENV=/comfyui/.venv
   ENV PATH="/comfyui/.venv/bin:$PATH"

   # Install ComfyUI dependencies
   COPY docker/ComfyUI/requirements.txt /tmp/comfyui-requirements.txt
   RUN uv pip install -r /tmp/comfyui-requirements.txt

   # Install custom node dependencies
   # Loop through custom_nodes/*/requirements.txt and install

   # Copy handler and utilities
   COPY docker/handler.py /handler.py
   COPY docker/utils.py /utils.py
   COPY docker/config.py /config.py
   COPY docker/model_paths.yaml /model_paths.yaml

   # Create directories
   RUN mkdir -p /comfyui/input /comfyui/output

   WORKDIR /
   CMD ["python", "-u", "/handler.py"]
   ```

2. **Build Strategy:**
   - **Option A**: Clone ComfyUI during build (always latest)
   - **Option B**: COPY pre-cloned ComfyUI (version controlled)
   - **Chosen**: Option B for reproducibility - we'll document cloning separately

3. **Layer Optimization:**
   - System deps (rarely change) → early layers
   - ComfyUI clone (occasionally changes) → middle layers
   - Dependencies (occasionally change) → middle layers
   - Handler code (frequently changes) → late layers

**Integration Points:**
- Dockerfile expects ComfyUI to be in docker/ComfyUI/
- Uses config.py, handler.py, utils.py from docker/
- Requires model_paths.yaml for model discovery

**Alternatives Considered:**

1. **Multi-stage build:**
   - **Single stage** (chosen): Simpler, acceptable size (~15GB)
   - **Multi-stage**: Smaller final image but more complex
   - Decision: Single stage - storage is cheap, complexity is expensive

2. **ComfyUI installation:**
   - **Clone during build**: Always latest, unpredictable
   - **COPY pre-cloned** (chosen): Version controlled, reproducible
   - **Git submodule**: Complex dependency management
   - Decision: COPY for reproducibility

**Testing Strategy:**
- Build locally without GPU (should succeed)
- Verify all files copied correctly
- Check uv is installed and on PATH
- Verify venv is created and activated
- Test with docker run locally
- Check handler.py can be executed

**Testable State:**
- `docker build` succeeds without errors
- Image size is reasonable (~10-15GB)
- Can run container and see handler initialization logs
- Handler starts even if ComfyUI missing (for testing)

---

### Phase 4: Build and Deployment Scripts

**Goal:** Create automated scripts for building, tagging, and pushing Docker images

**Files to Create:**
- `scripts/build.sh` - Build Docker image with defaults
- `scripts/push.sh` - Tag and push to registry
- `scripts/test-handler.py` - Local handler testing with mocks

**Technical Details:**

1. **Build Script (`scripts/build.sh`):**
   ```bash
   #!/bin/bash
   # Parse arguments: --tag, --no-cache, --registry, --image
   # Defaults from config.py:
   #   REGISTRY=curryberto
   #   IMAGE=comfyui-serverless
   #   TAG=latest

   # Build command:
   docker build \
     -t ${REGISTRY}/${IMAGE}:${TAG} \
     -f docker/Dockerfile \
     ${NO_CACHE} \
     .
   ```

2. **Push Script (`scripts/push.sh`):**
   ```bash
   #!/bin/bash
   # Parse arguments: --tag, --registry, --image
   # Defaults from config.py

   # Tag if different from build tag
   # Push to registry
   docker push ${REGISTRY}/${IMAGE}:${TAG}

   # Print success message with full image URL
   ```

3. **Test Handler (`scripts/test-handler.py`):**
   ```python
   # Mock runpod module
   # Import handler
   # Create mock event
   # Call handler and verify response structure
   # Test error conditions
   ```

**Integration Points:**
- Scripts read defaults from config.py
- Scripts use same Docker image naming convention
- Test script can run without RunPod environment

**Testing Strategy:**
- Run build.sh and verify image is created
- Test with custom tags and registries
- Verify push.sh works with Docker Hub credentials
- Run test-handler.py and verify all tests pass
- Test error handling in scripts

**Testable State:**
- `./scripts/build.sh` creates Docker image
- `./scripts/build.sh --tag v1.0.0` creates tagged image
- `./scripts/push.sh` (dry-run mode works)
- `python scripts/test-handler.py` passes all tests

---

### Phase 5: Model Sync Utilities

**Goal:** Create automated scripts for syncing models to RunPod network storage

**Files to Create:**
- `scripts/sync-models.py` - Automated zip, transfer, extract
- `scripts/extract-models.py` - Extraction script (generated by sync)

**Technical Details:**

1. **Sync Script (`scripts/sync-models.py`):**
   ```python
   # Args: local_dir, volume_id
   # 1. Create zip from local directory
   # 2. Run runpodctl send and capture code
   # 3. Generate extract-models.py script
   # 4. Include extract script in instructions
   # 5. Print receive command and instructions
   ```

2. **Extract Script (generated):**
   ```python
   # Runs from any location
   # Uses absolute paths
   # Extracts to /runpod-volume/comfyui/models/
   # Verifies extraction
   # Cleans up zip file
   ```

3. **Workflow:**
   ```
   Local: python scripts/sync-models.py /local/models VOLUME_ID
     ↓
   Creates models.zip
     ↓
   Runs: runpodctl send models.zip
     ↓
   Outputs: "Transfer code: 1234-alpha-bravo-charlie"
     ↓
   Generates extract-models.py
     ↓
   Prints instructions for RunPod side

   RunPod: runpodctl receive 1234-alpha-bravo-charlie
     ↓
   RunPod: python extract-models.py
     ↓
   Models extracted to /runpod-volume/comfyui/models/
   ```

**Integration Points:**
- Uses runpodctl CLI tool
- Expects specific directory structure on both sides
- Works with network volume paths from config.py

**Alternatives Considered:**

1. **Transfer method:**
   - **Individual files**: Simple but slow
   - **Zip archive** (chosen): Fast, atomic
   - **rsync over SSH**: Complex setup
   - Decision: Zip for simplicity and speed

2. **Extraction location:**
   - **Relative paths**: Fragile, location-dependent
   - **Absolute paths** (chosen): Robust, works from anywhere
   - Decision: Absolute paths for reliability

**Testing Strategy:**
- Test zip creation from local directory
- Mock runpodctl send command
- Verify extract script generation
- Test extract script with sample zip
- Verify directory structure preserved

**Testable State:**
- Can create zip from local models directory
- Zip preserves directory structure
- Extract script can be generated
- Instructions are clear and complete
- Can test extraction locally (to temp dir)

---

### Phase 6: RunPod API Client

**Goal:** Create client script for submitting workflows to RunPod endpoint

**Files to Create:**
- `scripts/send-to-runpod.py` - Client for submitting workflows
- `scripts/test-local.py` - Test handler locally before RunPod

**Technical Details:**

1. **Client Script (`scripts/send-to-runpod.py`):**
   ```python
   # Args: --workflow, --images, --output
   # Uses RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID from env

   # 1. Read workflow JSON
   # 2. Encode reference images as base64
   # 3. Assemble request payload
   # 4. POST to RunPod API /run endpoint
   # 5. Get job ID
   # 6. Poll /status endpoint
   # 7. Download results
   # 8. Save to output directory
   # 9. Open images
   ```

2. **Request Format:**
   ```json
   {
     "input": {
       "workflow": {...},
       "reference_images": {
         "image1.png": "base64...",
         "masks/mask1.png": "base64..."
       },
       "return_base64": true
     }
   }
   ```

3. **Polling Logic:**
   - Poll every 2 seconds
   - Check for status: COMPLETED, FAILED, CANCELLED
   - Timeout after 10 minutes
   - Show progress indicator

**Integration Points:**
- Uses config.py for endpoint ID and API key
- Reads workflows from workflows/ directory
- Reads images from input/ directory
- Saves outputs to output/ directory

**Testing Strategy:**
- Mock RunPod API endpoints
- Test with sample workflow JSON
- Test with reference images (including subdirs)
- Test error handling (timeout, failure)
- Verify base64 encoding/decoding

**Testable State:**
- Can read workflow and encode images
- Request payload is correctly formatted
- Can parse successful response
- Can parse error response
- Images saved to correct output location

---

### Phase 7: Local ComfyUI API Routing (Optional for Initial Setup)

**Goal:** Create launcher that routes local ComfyUI queue button to RunPod

**Files to Create:**
- `scripts/launch_comfy_with_api.py` - ComfyUI launcher with patching

**Technical Details:**

1. **Launcher Script:**
   ```python
   # Import ComfyUI modules
   # Monkey-patch queue handler
   # Start ComfyUI server
   # Intercept /prompt POST requests
   # Route to RunPod API
   # Download and open results
   ```

2. **Two Implementation Approaches:**
   - **Approach A**: Custom node with route override
   - **Approach B**: Reverse proxy server
   - **Decision for initial setup**: Document approach, implement later

**Note:** This is advanced functionality and may be deferred to a separate feature. For the initial setup, we'll document the approach but implementation is optional.

**Testing Strategy:**
- If implemented: Test with local ComfyUI
- Verify queue button triggers API call
- Verify results are downloaded and opened

**Testable State:**
- Documentation complete for implementation approach
- (If implemented) Can launch ComfyUI with routing enabled

---

## Implementation Progress

### Phase 1: Project Foundation and Configuration
- [x] Implementation Complete
- [x] Testing Complete

### Phase 2: Docker Handler with Worker Initialization
- [x] Implementation Complete
- [x] Testing Complete

### Phase 3: Dockerfile with uv and ComfyUI
- [x] Implementation Complete
- [x] Testing Complete

### Phase 4: Build and Deployment Scripts
- [x] Implementation Complete
- [x] Testing Complete

### Phase 5: Model Sync Utilities
- [x] Implementation Complete
- [x] Testing Complete

### Phase 6: RunPod API Client
- [x] Implementation Complete
- [x] Testing Complete

### Phase 7: Local ComfyUI API Routing (Optional)
- [x] Implementation Complete
- [x] Testing Complete

---

## Notes

- Phase 7 (Local ComfyUI API Routing) is marked as optional and can be implemented as a separate feature
- Testing for phases 2-3 requires ComfyUI to be cloned into docker/ComfyUI/ first
- Docker builds will initially fail until ComfyUI is present, but handler can be tested independently
- Each phase builds on the previous, so order matters
- We need to decide on ComfyUI version/commit to use before Phase 3
