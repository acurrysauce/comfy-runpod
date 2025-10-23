# syntax=docker/dockerfile:1.4
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Install minimal system dependencies (using Python 3.10 from Ubuntu 22.04)
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    curl \
    git \
    wget \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy ComfyUI source code (without .venv - we'll create fresh)
COPY ComfyUI /comfyui

# Create fresh venv and install all dependencies in one layer
RUN cd /comfyui && \
    uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -r requirements.txt && \
    for req in custom_nodes/*/requirements.txt; do \
      if [ -f "$req" ]; then \
        echo "Installing requirements from $req" && \
        uv pip install -r "$req"; \
      fi \
    done && \
    uv pip install runpod>=1.6.0 boto3>=1.28.0 && \
    uv pip install numba opencv-python scikit-image matplotlib && \
    python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}')"

# Activate the venv
ENV VIRTUAL_ENV=/comfyui/.venv
ENV PATH="/comfyui/.venv/bin:$PATH"

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
