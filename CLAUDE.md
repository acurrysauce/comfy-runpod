# CLAUDE.md

Project guidance for Claude Code when working with this repository.

## Project Overview

Production-ready ComfyUI deployment system for local development and RunPod serverless infrastructure:

- Local ComfyUI installation mirroring production
- Docker images with pre-installed ComfyUI + custom nodes (fast cold starts)
- Models on network storage (RunPod volumes) for cost efficiency
- API handler for serverless inference with comprehensive debugging
- **runpodctl** for file syncing between local and network storage
- **uv** for all Python dependency management
- Custom node routes local ComfyUI queue button to RunPod API

**Design Goals:** Fast startup, cost efficiency, debuggability, local/remote parity, non-invasive ComfyUI modifications

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

Pre-bake everything at build time using uv:
- Clone ComfyUI and custom nodes during `docker build`
- Run `uv pip install -r requirements.txt` for all components
- Result: <5s container startup vs 30-60s runtime installation
- Trade-off: ~10-15GB images, must rebuild to update nodes (acceptable for serverless)

#### 2. Model Storage Strategy: Network Volumes

Store models on RunPod network volumes (shared across workers):
- **Serverless**: `/runpod-volume/comfyui/models/`
- **Pods**: `/workspace/comfyui/models/`
- `model_paths.yaml` configures ComfyUI discovery
- **Local**: `extra_model_paths.yaml` points to external directory, sync via runpodctl

#### 3. Handler Design: Start ComfyUI on Worker Initialization

Start ComfyUI during worker init (not first request):
- Call `initialize_worker()` at module load
- ComfyUI subprocess starts immediately, waits for health check
- Server stays running for worker lifetime
- Handler monitors health and restarts if crashed
- Result: Zero startup overhead on first request, models pre-loaded in VRAM

#### 4. Debugging Strategy: Comprehensive Logging + Error Returns

Multi-layered debugging (RunPod logs are hard to access):
- **Extensive stdout logging**: ComfyUI output, directory contents, health checks, validation
- **Return errors in response**: Include full tracebacks, diagnostic info (models, directories), last log lines
- **Health monitoring**: Poll `/system_stats`, detect crashes, auto-restart if needed

#### 5. File Transfer Strategy: Zip + Sync Scripts

Batch transfer via `scripts/sync-models.py` to avoid slow file-by-file transfer:
```bash
python scripts/sync-models.py /local/models NETWORK_VOLUME_ID
# 1. Creates zip, 2. runpodctl send, 3. Generates extraction script, 4. Verifies
```

#### 6. Input File Management Strategy

Use `input/` directory with subdirectories (e.g., `input/masks/`, `input/textures/`):
- **Local**: Use `--input-directory` and `--output-directory` flags (keeps ComfyUI installation clean)
- **Docker**: Directories at `/comfyui/input/` and `/comfyui/output/` (external to ComfyUI installation)
- **Handler**: Creates subdirectories via `os.makedirs(os.path.dirname(full_path), exist_ok=True)`
- **LoadImage**: Install subfolder-aware custom node (e.g., `comfyui-loadimagewithsubfolder`)

#### 7. Virtual Environment Strategy: Single Shared venv

Single shared venv for ComfyUI + all custom nodes (managed by uv):
- Standard ComfyUI practice: one venv per installation
- Main project has `pyproject.toml` and `uv.lock`
- ComfyUI uses venv created by main project (no separate `uv init`)

#### 8. Workflow Storage Strategy: Symlinked Outside Docker

Symlink ComfyUI's workflow directory to project directory:
- **Real directory**: `/comfy-runpod/workflows/` (git tracked, outside docker)
- **Symlink**: `docker/ComfyUI/user/default/workflows` → points to real directory
- **Benefit**: Workflows saved in ComfyUI go directly to project directory
- **Docker safety**: Symlink is local-only, doesn't affect Docker builds (broken symlink in image is harmless)

#### 9. Local ComfyUI Queue Button → RunPod API

Custom node intercepts queue button to execute on RunPod:
- Uses `@PromptServer.instance.routes.post('/prompt')` to override handler
- Workflow → RunPod API → poll completion → download → auto-open images
- Non-invasive (survives ComfyUI upgrades)

#### Custom Node Development Workflow

**Two-copy approach** (source vs active):
- `custom_nodes/runpod-queue/` - Source of truth (git tracked)
- `docker/ComfyUI/custom_nodes/runpod-queue/` - Active copy (gitignored, loaded by ComfyUI)
- **Workflow**: Edit source → commit → copy to active → restart ComfyUI

**Custom Node Features:**
- Backend: `/runpod/queue` (submit), `/runpod/latest_images` (with depth sorting)
- Frontend: "Queue on RunPod" button, polls completion, browser overlay
- Image sorting: Calculates node depth from workflow graph (deepest first = final result)

### Component Breakdown

**Docker Components:**
1. **ComfyUI Server** - Full installation (uv-managed), started on worker init
2. **Handler** - RunPod entry point, starts ComfyUI, queues workflows, monitors execution
3. **Configuration** - `model_paths.yaml` points to network volume
4. **Utilities** - Model download/upload, cleanup helpers

**Local Components:**
1. **ComfyUI Installation** - Standard clone, matches production, uses `extra_model_paths.yaml`
2. **Models Directory** - External, synced via runpodctl
3. **Scripts** - `sync-models.py` (zip/transfer), `launch_comfy_with_api.py` (runtime patching)
4. **Workflows Directory** - Symlinked from `docker/ComfyUI/user/default/workflows` → `/workflows/` (keeps workflows outside docker directory)

## Development Commands

### Setup
```bash
# Project initialization
uv init && uv sync

# Local ComfyUI
git clone https://github.com/comfyanonymous/ComfyUI.git docker/ComfyUI
cd docker/ComfyUI && uv venv && uv pip install -r requirements.txt
# Install custom nodes: cd custom_nodes && git clone <repo> && uv pip install -r requirements.txt

# Symlink workflows directory (keeps workflows outside docker directory)
rm -rf docker/ComfyUI/user/default/workflows
ln -s /absolute/path/to/comfy-runpod/workflows docker/ComfyUI/user/default/workflows

# Docker tools
curl -fsSL https://get.docker.com | sudo sh
wget https://github.com/runpod/runpodctl/releases/latest/download/runpodctl-linux-amd64
sudo mv runpodctl-linux-amd64 /usr/local/bin/runpodctl && runpodctl config
```

### Running
```bash
# Local ComfyUI (standard)
python main.py --input-directory /path/to/input --output-directory /path/to/output --extra-model-paths-config extra_model_paths.yaml

# Local ComfyUI (with RunPod routing)
python scripts/launch_comfy_with_api.py

# Docker handler
./scripts/build.sh
docker run --rm -it --gpus all -v /path/to/models:/runpod-volume/comfyui/models:ro -p 8188:8188 curryberto/comfyui-serverless:latest
```

### Testing
```bash
python scripts/test-handler.py                        # Local handler test
python scripts/test-local.py --workflow test.json    # Local workflow test
python scripts/send-to-runpod.py --workflow test.json # RunPod test
```

### Building & Deployment
```bash
./scripts/build.sh [--tag v1.0.0] [--no-cache]
./scripts/push.sh [--tag v1.0.0] [--registry myregistry]
```

### Model Sync
```bash
# Automated (recommended)
python scripts/sync-models.py /local/models NETWORK_VOLUME_ID

# Manual
cd /local/models && zip -r models.zip ./*
runpodctl send models.zip  # Get transfer code
# On RunPod: runpodctl receive <code> && unzip -o models.zip
```

## Key Patterns and Conventions

### Configuration Management

Centralized config with environment variable overrides:
- Docker: `curryberto/comfyui-serverless:latest` (configurable via env)
- Paths: `/runpod-volume/comfyui/models/` (serverless), `/workspace/comfyui/models/` (pods)
- API keys: `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID` from environment

### Handler Implementation Patterns

**Key patterns** (see `docker/handler.py` for implementations):

1. **Worker Initialization**: Call `initialize_worker()` at module load to start ComfyUI subprocess
2. **Logging**: Structured logging with diagnostic info (models, directories, ComfyUI status, last N log lines)
3. **Error Responses**: Include traceback, diagnostic info, system state in JSON responses
4. **Output Capture**: Thread-based ComfyUI stdout/stderr capture for error reporting
5. **Workflow Validation**: Pre-execution checks for required files (checkpoints, loras, images)
6. **Health Monitoring**: Check process exists, alive, and responds to `/system_stats`; auto-restart if failed

## Critical Requirements

1. **Use uv**: All dependency management (local: `uv init && uv pip install`, Docker: install uv → create venv → install deps)
2. **Worker Init**: Call `initialize_worker()` at module load (see `handler.py`)
3. **Crash Recovery**: Detect and restart ComfyUI (see `handler.py:ensure_comfyui_running()`)
4. **Output Capture**: Thread-based stdout/stderr logging (see `handler.py:capture_comfyui_output()`)
5. **Model Logging**: Log available models on every request (see `handler.py:log_model_directory()`)
6. **Subdirectory Support**: Install `comfyui-loadimagewithsubfolder`, create subdirs with `os.makedirs()`

## Important Notes

### Docker Best Practices
- Order layers from least to most frequently changed (system deps → uv → ComfyUI → handler code)
- Use `uv pip compile` for dependency pinning
- Enable BuildKit for faster builds

### Environment Variables
**Required**: `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`
**Optional**: `DOCKER_REGISTRY`, `DOCKER_IMAGE`, `DOCKER_TAG`, `EXECUTION_TIMEOUT`, `HEALTH_CHECK_INTERVAL`, `CLEANUP_AGE`

### Performance
- **Cold start**: <5s (pre-install deps, start on worker init, use uv)
- **Model loading**: 10-30s first request per worker (use min_workers=1 to keep alive)
- **Request latency**: 5-60s depending on workflow complexity
- **Cost optimization**: Network volumes, appropriate idle timeout, min_workers=0 for low traffic

### Security
Input validation, file access restrictions, resource limits, env vars for secrets, image scanning

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
