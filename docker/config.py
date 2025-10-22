"""
Configuration module for comfy-runpod project.

Provides centralized configuration with sensible defaults that can be
overridden via environment variables.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class DockerConfig:
    """Docker image configuration."""

    registry: str = os.getenv("DOCKER_REGISTRY", "curryberto")
    image: str = os.getenv("DOCKER_IMAGE", "comfyui-serverless")
    tag: str = os.getenv("DOCKER_TAG", "latest")

    @property
    def image_full(self) -> str:
        """Get full Docker image name with registry and tag."""
        return f"{self.registry}/{self.image}:{self.tag}"


@dataclass
class RunPodConfig:
    """RunPod API configuration."""

    api_key: str = os.getenv("RUNPOD_API_KEY", "")
    endpoint_id: str = os.getenv("RUNPOD_ENDPOINT_ID", "")

    @property
    def is_configured(self) -> bool:
        """Check if RunPod credentials are configured."""
        return bool(self.api_key and self.endpoint_id)


@dataclass
class PathConfig:
    """Path configuration for different environments."""

    # Serverless endpoint paths (production)
    models_path_serverless: str = "/runpod-volume/comfyui/models"

    # Pod paths (testing/development)
    models_path_pod: str = "/workspace/comfyui/models"

    # ComfyUI installation paths
    comfyui_path: str = "/comfyui"
    comfyui_python: str = "/comfyui/.venv/bin/python"

    # ComfyUI input/output directories (external to installation)
    # Docker: These are separate directories mounted in container
    # Local: Point to project root input/output via --input-directory flag
    comfyui_input: str = "/comfyui/input"
    comfyui_output: str = "/comfyui/output"

    # Local development paths (for launching ComfyUI with external dirs)
    local_input: str = "./input"
    local_output: str = "./output"

    # Model paths YAML config
    model_paths_config: str = "/model_paths.yaml"

    def get_models_path(self, environment: str = "serverless") -> str:
        """Get models path for the specified environment.

        Args:
            environment: Either 'serverless' (default) or 'pod'

        Returns:
            Path to models directory for the environment
        """
        if environment == "pod":
            return self.models_path_pod
        return self.models_path_serverless


@dataclass
class HandlerConfig:
    """Handler runtime configuration."""

    # Execution settings
    execution_timeout: int = int(os.getenv("EXECUTION_TIMEOUT", "300"))  # 5 minutes
    health_check_interval: int = int(os.getenv("HEALTH_CHECK_INTERVAL", "5"))  # 5 seconds
    health_check_timeout: int = int(os.getenv("HEALTH_CHECK_TIMEOUT", "30"))  # 30 seconds

    # Cleanup settings
    cleanup_age: int = int(os.getenv("CLEANUP_AGE", "3600"))  # 1 hour

    # Output settings
    return_base64: bool = os.getenv("RETURN_BASE64", "true").lower() == "true"

    # Logging settings
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_comfyui_output: bool = os.getenv("LOG_COMFYUI_OUTPUT", "true").lower() == "true"

    # ComfyUI server settings
    comfyui_host: str = "0.0.0.0"
    comfyui_port: int = 8188


@dataclass
class ProjectDefaults:
    """Complete project configuration with all defaults."""

    docker: DockerConfig
    runpod: RunPodConfig
    paths: PathConfig
    handler: HandlerConfig

    def __init__(self):
        """Initialize all configuration sections."""
        self.docker = DockerConfig()
        self.runpod = RunPodConfig()
        self.paths = PathConfig()
        self.handler = HandlerConfig()

    @classmethod
    def from_env(cls) -> "ProjectDefaults":
        """Create configuration from environment variables.

        This is the recommended way to instantiate configuration
        as it ensures all environment variables are read.
        """
        return cls()

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not self.runpod.api_key:
            errors.append("RUNPOD_API_KEY not set")

        if not self.runpod.endpoint_id:
            errors.append("RUNPOD_ENDPOINT_ID not set")

        if self.handler.execution_timeout < 30:
            errors.append("EXECUTION_TIMEOUT must be at least 30 seconds")

        if self.handler.health_check_timeout < 5:
            errors.append("HEALTH_CHECK_TIMEOUT must be at least 5 seconds")

        return errors


# Global configuration instance
# Use this throughout the application
config = ProjectDefaults.from_env()


# Convenience exports for common values
DOCKER_IMAGE_FULL = config.docker.image_full
MODELS_PATH = config.paths.models_path_serverless
COMFYUI_PATH = config.paths.comfyui_path
COMFYUI_INPUT = config.paths.comfyui_input
COMFYUI_OUTPUT = config.paths.comfyui_output
COMFYUI_PYTHON = config.paths.comfyui_python
