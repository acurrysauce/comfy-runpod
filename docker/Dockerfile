# syntax=docker/dockerfile:1.4
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    curl \
    git \
    wget \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy ComfyUI source code (excluding .venv per .dockerignore)
COPY ComfyUI /comfyui

# Create virtual environment using uv
RUN uv venv /comfyui/.venv

# Activate venv for subsequent RUN commands
ENV VIRTUAL_ENV=/comfyui/.venv
ENV PATH="/comfyui/.venv/bin:$PATH"

# Install ComfyUI core dependencies
RUN uv pip install -r /comfyui/requirements.txt

# Install custom node dependencies (if any exist)
# This will install requirements.txt from all custom_nodes subdirectories
RUN for req in /comfyui/custom_nodes/*/requirements.txt; do \
        if [ -f "$req" ]; then \
            echo "Installing dependencies from $req"; \
            uv pip install -r "$req"; \
        fi \
    done

# Install serverless-specific packages
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
