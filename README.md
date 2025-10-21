# comfy-runpod

Production-ready ComfyUI deployment system for local development and RunPod serverless infrastructure.

## Features

- 🚀 **Fast cold starts** - Pre-built Docker images with all dependencies (<5s startup)
- 💰 **Cost efficient** - Models stored on network volumes, shared across workers
- 🔍 **Extensive debugging** - Comprehensive logging and error diagnostics
- 🔄 **Local/remote parity** - Local setup mirrors production exactly
- 🛠️ **uv-powered** - Fast, reproducible dependency management
- 🎯 **Worker initialization** - ComfyUI starts before first request for consistent latency

## Quick Start

### Prerequisites

- Python 3.10+
- Docker (for building images)
- [uv](https://github.com/astral-sh/uv) package manager
- [runpodctl](https://github.com/runpod/runpodctl) (for syncing models)
- RunPod account with API key

### Installation

```bash
# Clone repository
git clone https://github.com/acurrysauce/comfy-runpod.git
cd comfy-runpod

# Install dependencies
uv sync

# Set up environment variables
export RUNPOD_API_KEY="your-api-key"
export RUNPOD_ENDPOINT_ID="your-endpoint-id"
```

### Configuration

The project uses sensible defaults that can be overridden via environment variables:

```bash
# Docker configuration
export DOCKER_REGISTRY="curryberto"          # Default registry
export DOCKER_IMAGE="comfyui-serverless"      # Default image name
export DOCKER_TAG="latest"                     # Default tag

# RunPod configuration (required)
export RUNPOD_API_KEY="your-api-key"
export RUNPOD_ENDPOINT_ID="your-endpoint-id"

# Handler configuration (optional)
export EXECUTION_TIMEOUT="300"                 # Workflow timeout (seconds)
export HEALTH_CHECK_INTERVAL="5"               # Health check interval (seconds)
export LOG_LEVEL="INFO"                        # Logging level
```

## Project Structure

```
comfy-runpod/
├── docker/              # Docker-related files
│   ├── config.py        # Configuration module
│   ├── handler.py       # RunPod serverless handler
│   ├── utils.py         # Utility functions
│   ├── model_paths.yaml # ComfyUI model configuration
│   └── Dockerfile       # Container build definition
├── scripts/             # Utility scripts
│   ├── build.sh         # Build Docker image
│   ├── push.sh          # Push to registry
│   ├── sync-models.py   # Sync models to RunPod
│   └── send-to-runpod.py# Submit workflows to API
├── workflows/           # ComfyUI workflow JSONs
├── input/               # Local input files
├── output/              # Local output files
└── plans/               # Implementation plans
```

## Development

See [CLAUDE.md](./CLAUDE.md) for comprehensive development documentation, including:

- Architecture decisions and trade-offs
- Development commands
- Testing procedures
- Implementation patterns
- Feature development workflow

## Building and Deploying

```bash
# Build Docker image
./scripts/build.sh

# Push to registry (Docker Hub)
./scripts/push.sh

# Sync models to RunPod network volume
python scripts/sync-models.py /path/to/local/models VOLUME_ID
```

## Usage

```bash
# Submit workflow to RunPod endpoint
python scripts/send-to-runpod.py \
  --workflow workflows/my-workflow.json \
  --images input/ \
  --output output/
```

## Architecture

This project implements a "fat images, fast starts" strategy:

- **Docker images** contain pre-installed ComfyUI and custom nodes
- **Models** are stored on RunPod network volumes (shared across workers)
- **Handler** starts ComfyUI on worker initialization (not first request)
- **Configuration** is centralized with environment variable overrides

See [CLAUDE.md](./CLAUDE.md) for detailed architecture documentation.

## Contributing

This project follows a structured feature development workflow:

1. Create feature branch
2. Write detailed implementation plan in `/plans/`
3. Review and refine plan
4. Implement one phase at a time
5. Test each phase before moving forward
6. Commit and merge when complete

See the "Feature Development Workflow" section in [CLAUDE.md](./CLAUDE.md) for details.

## License

MIT

## Support

For issues or questions, please open an issue on GitHub.
