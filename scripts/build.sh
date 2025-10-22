#!/bin/bash
set -e

# ComfyUI RunPod Docker Image Build Script
# Builds the Docker image with configurable parameters

# Default values from config.py
REGISTRY="${DOCKER_REGISTRY:-curryberto}"
IMAGE="${DOCKER_IMAGE:-comfyui-serverless}"
TAG="${DOCKER_TAG:-latest}"
NO_CACHE=""
PLATFORM=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --registry)
            REGISTRY="$2"
            shift 2
            ;;
        --image)
            IMAGE="$2"
            shift 2
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --platform)
            PLATFORM="--platform $2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Build ComfyUI RunPod Docker image"
            echo ""
            echo "Options:"
            echo "  --registry REGISTRY    Docker registry (default: curryberto)"
            echo "  --image IMAGE          Image name (default: comfyui-serverless)"
            echo "  --tag TAG             Image tag (default: latest)"
            echo "  --no-cache            Build without using cache"
            echo "  --platform PLATFORM   Target platform (e.g., linux/amd64)"
            echo "  -h, --help            Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  DOCKER_REGISTRY       Override default registry"
            echo "  DOCKER_IMAGE          Override default image name"
            echo "  DOCKER_TAG            Override default tag"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Build with defaults"
            echo "  $0 --tag v1.0.0                       # Build with custom tag"
            echo "  $0 --no-cache                         # Build without cache"
            echo "  $0 --registry myuser --tag dev        # Custom registry and tag"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Construct full image name
FULL_IMAGE="${REGISTRY}/${IMAGE}:${TAG}"

# Print build configuration
echo "======================================"
echo "ComfyUI RunPod Docker Build"
echo "======================================"
echo "Registry:  $REGISTRY"
echo "Image:     $IMAGE"
echo "Tag:       $TAG"
echo "Full name: $FULL_IMAGE"
echo ""
if [ -n "$NO_CACHE" ]; then
    echo "Cache:     DISABLED"
fi
if [ -n "$PLATFORM" ]; then
    echo "Platform:  ${PLATFORM#--platform }"
fi
echo "======================================"
echo ""

# Check if ComfyUI exists in docker directory
if [ ! -d "docker/ComfyUI" ]; then
    echo "ERROR: docker/ComfyUI directory not found"
    echo "Please clone ComfyUI into docker/ComfyUI before building"
    echo ""
    echo "Example:"
    echo "  cd docker"
    echo "  git clone https://github.com/comfyanonymous/ComfyUI.git"
    echo "  cd .."
    exit 1
fi

# Check if Dockerfile exists
if [ ! -f "docker/Dockerfile" ]; then
    echo "ERROR: docker/Dockerfile not found"
    exit 1
fi

# Start build
echo "Starting Docker build..."
echo ""

# Build command
docker build \
    -t "$FULL_IMAGE" \
    -f docker/Dockerfile \
    $NO_CACHE \
    $PLATFORM \
    docker/

# Check build status
if [ $? -eq 0 ]; then
    echo ""
    echo "======================================"
    echo "Build successful!"
    echo "======================================"
    echo "Image: $FULL_IMAGE"
    echo ""
    echo "Next steps:"
    echo "  - Test locally:  docker run --rm $FULL_IMAGE"
    echo "  - Push to registry: ./scripts/push.sh --tag $TAG"
    echo "======================================"
else
    echo ""
    echo "======================================"
    echo "Build failed!"
    echo "======================================"
    exit 1
fi
