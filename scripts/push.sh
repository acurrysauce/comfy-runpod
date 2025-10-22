#!/bin/bash
set -e

# ComfyUI RunPod Docker Image Push Script
# Tags and pushes the Docker image to a registry

# Default values from config.py
REGISTRY="${DOCKER_REGISTRY:-curryberto}"
IMAGE="${DOCKER_IMAGE:-comfyui-serverless}"
TAG="${DOCKER_TAG:-latest}"
ADDITIONAL_TAGS=()
DRY_RUN=false

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
        --also-tag)
            ADDITIONAL_TAGS+=("$2")
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Push ComfyUI RunPod Docker image to registry"
            echo ""
            echo "Options:"
            echo "  --registry REGISTRY    Docker registry (default: curryberto)"
            echo "  --image IMAGE          Image name (default: comfyui-serverless)"
            echo "  --tag TAG             Image tag to push (default: latest)"
            echo "  --also-tag TAG        Additional tag to apply and push"
            echo "  --dry-run             Show what would be pushed without actually pushing"
            echo "  -h, --help            Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  DOCKER_REGISTRY       Override default registry"
            echo "  DOCKER_IMAGE          Override default image name"
            echo "  DOCKER_TAG            Override default tag"
            echo ""
            echo "Examples:"
            echo "  $0                                          # Push latest"
            echo "  $0 --tag v1.0.0                             # Push specific tag"
            echo "  $0 --tag v1.0.0 --also-tag latest           # Push and also tag as latest"
            echo "  $0 --dry-run                                # Preview without pushing"
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

# Print push configuration
echo "======================================"
echo "ComfyUI RunPod Docker Push"
echo "======================================"
echo "Registry:  $REGISTRY"
echo "Image:     $IMAGE"
echo "Tag:       $TAG"
echo "Full name: $FULL_IMAGE"
echo ""
if [ ${#ADDITIONAL_TAGS[@]} -gt 0 ]; then
    echo "Additional tags:"
    for additional_tag in "${ADDITIONAL_TAGS[@]}"; do
        echo "  - ${REGISTRY}/${IMAGE}:${additional_tag}"
    done
    echo ""
fi
if [ "$DRY_RUN" = true ]; then
    echo "Mode:      DRY RUN (no actual push)"
fi
echo "======================================"
echo ""

# Check if image exists locally
if ! docker image inspect "$FULL_IMAGE" > /dev/null 2>&1; then
    echo "ERROR: Image $FULL_IMAGE not found locally"
    echo "Please build the image first using ./scripts/build.sh"
    exit 1
fi

# Get image size and ID
IMAGE_SIZE=$(docker image inspect "$FULL_IMAGE" --format='{{.Size}}' | awk '{printf "%.2f GB", $1/1024/1024/1024}')
IMAGE_ID=$(docker image inspect "$FULL_IMAGE" --format='{{.Id}}' | cut -d: -f2 | cut -c1-12)

echo "Image details:"
echo "  ID:   $IMAGE_ID"
echo "  Size: $IMAGE_SIZE"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "DRY RUN - Would execute:"
    echo "  docker push $FULL_IMAGE"
    for additional_tag in "${ADDITIONAL_TAGS[@]}"; do
        additional_full="${REGISTRY}/${IMAGE}:${additional_tag}"
        echo "  docker tag $FULL_IMAGE $additional_full"
        echo "  docker push $additional_full"
    done
    echo ""
    echo "Run without --dry-run to actually push"
    exit 0
fi

# Check if logged in to registry (try to get auth token)
echo "Checking Docker registry authentication..."
if ! docker info | grep -q "Username"; then
    echo "WARNING: You may not be logged in to Docker registry"
    echo "If push fails, run: docker login"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted"
        exit 1
    fi
fi

# Push main tag
echo "Pushing $FULL_IMAGE..."
docker push "$FULL_IMAGE"

# Push additional tags
for additional_tag in "${ADDITIONAL_TAGS[@]}"; do
    additional_full="${REGISTRY}/${IMAGE}:${additional_tag}"
    echo ""
    echo "Tagging as $additional_full..."
    docker tag "$FULL_IMAGE" "$additional_full"

    echo "Pushing $additional_full..."
    docker push "$additional_full"
done

# Success message
echo ""
echo "======================================"
echo "Push successful!"
echo "======================================"
echo "Image: $FULL_IMAGE"
if [ ${#ADDITIONAL_TAGS[@]} -gt 0 ]; then
    echo ""
    echo "Also pushed as:"
    for additional_tag in "${ADDITIONAL_TAGS[@]}"; do
        echo "  - ${REGISTRY}/${IMAGE}:${additional_tag}"
    done
fi
echo ""
echo "Next steps:"
echo "  - Deploy on RunPod using: $FULL_IMAGE"
echo "  - Update endpoint configuration if needed"
echo "======================================"
