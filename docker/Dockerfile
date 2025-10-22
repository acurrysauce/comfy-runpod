# syntax=docker/dockerfile:1.4
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
# Note: Using Ubuntu 22.04 package names (base image is 22.04)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    curl \
    git \
    wget \
    libgl1-mesa-glx \
    libglib2.0-0 \
    pkg-config \
    libcairo2-dev \
    python3-cairo \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy ComfyUI source code with all custom nodes AND venv already installed
# This is a "fat" image strategy - everything is pre-installed locally
COPY ComfyUI /comfyui

# Copy our custom nodes (tracked in git)
COPY ../custom_nodes/runpod-queue /comfyui/custom_nodes/runpod-queue

# Activate the copied venv for subsequent RUN commands
ENV VIRTUAL_ENV=/comfyui/.venv
ENV PATH="/comfyui/.venv/bin:$PATH"

# Install only serverless-specific packages (everything else already in venv)
RUN uv pip install \
    runpod>=1.6.0 \
    boto3>=1.28.0

# Copy handler, utilities, and configuration
COPY handler.py /handler.py
COPY utils.py /utils.py
COPY config.py /config.py
COPY model_paths.yaml /model_paths.yaml

# Create input and output directories (external to ComfyUI installation)
RUN mkdir -p /comfyui/input /comfyui/output

# Set working directory
WORKDIR /

# Run handler with unbuffered output
CMD ["python", "-u", "/handler.py"]
