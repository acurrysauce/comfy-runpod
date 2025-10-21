#!/usr/bin/env python3
"""
RunPod Serverless Handler for ComfyUI

This handler manages ComfyUI as a persistent server process, starting it
during worker initialization (not on first request) for consistent latency.
"""

import runpod
import json
import os
import sys
import time
import subprocess
import requests
import base64
import logging
import traceback
import threading
from pathlib import Path
from queue import Queue
from datetime import datetime
from typing import Optional, Dict, Any, List

from config import config, MODELS_PATH, COMFYUI_INPUT, COMFYUI_OUTPUT, COMFYUI_PATH, COMFYUI_PYTHON
from utils import download_models, upload_to_s3, cleanup_outputs

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.handler.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Global state for persistent ComfyUI process
comfyui_process: Optional[subprocess.Popen] = None
server_ready: bool = False
comfyui_output_queue: Queue = Queue(maxsize=1000)


def capture_comfyui_output(process: subprocess.Popen) -> threading.Thread:
    """Capture ComfyUI stdout/stderr and make available for logging.

    Args:
        process: The ComfyUI subprocess

    Returns:
        Thread that's capturing output
    """
    def reader_thread():
        """Read and log ComfyUI output line by line."""
        try:
            for line in iter(process.stdout.readline, b''):
                if line:
                    decoded_line = line.decode('utf-8').rstrip()
                    # Add to queue for error reporting
                    try:
                        comfyui_output_queue.put_nowait(decoded_line)
                    except:
                        # Queue full, drop oldest
                        try:
                            comfyui_output_queue.get_nowait()
                            comfyui_output_queue.put_nowait(decoded_line)
                        except:
                            pass

                    # Log with prefix
                    if config.handler.log_comfyui_output:
                        logger.info(f"[ComfyUI] {decoded_line}")
        except Exception as e:
            logger.error(f"Error in output capture thread: {e}")

    thread = threading.Thread(target=reader_thread, daemon=True)
    thread.start()
    return thread


def get_recent_comfyui_logs(max_lines: int = 50) -> List[str]:
    """Get recent ComfyUI log lines for error reporting.

    Args:
        max_lines: Maximum number of lines to retrieve

    Returns:
        List of recent log lines
    """
    logs = []
    try:
        while len(logs) < max_lines:
            logs.append(comfyui_output_queue.get_nowait())
    except:
        pass
    return logs


def wait_for_health_check(timeout: int = None) -> bool:
    """Wait for ComfyUI server to become healthy.

    Args:
        timeout: Timeout in seconds (uses config default if None)

    Returns:
        True if server is healthy, False if timeout
    """
    if timeout is None:
        timeout = config.handler.health_check_timeout

    logger.info(f"Waiting for ComfyUI health check (timeout: {timeout}s)...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = requests.get(
                f"http://localhost:{config.handler.comfyui_port}/system_stats",
                timeout=5
            )
            if response.status_code == 200:
                logger.info("✓ ComfyUI is healthy and ready")
                return True
        except requests.exceptions.RequestException:
            pass

        time.sleep(1)

    logger.error(f"✗ ComfyUI health check timeout after {timeout}s")
    return False


def start_comfyui_server() -> bool:
    """Start ComfyUI server in background.

    Returns:
        True if started successfully, False otherwise
    """
    global comfyui_process, server_ready

    if comfyui_process is not None and server_ready:
        logger.info("ComfyUI already running")
        return True

    logger.info("Starting ComfyUI server...")
    logger.info(f"Models path: {MODELS_PATH}")
    logger.info(f"Input path: {COMFYUI_INPUT}")
    logger.info(f"Output path: {COMFYUI_OUTPUT}")

    # Ensure directories exist
    os.makedirs(COMFYUI_INPUT, exist_ok=True)
    os.makedirs(COMFYUI_OUTPUT, exist_ok=True)

    try:
        # Start ComfyUI process
        comfyui_process = subprocess.Popen(
            [
                COMFYUI_PYTHON, "main.py",
                "--listen", config.handler.comfyui_host,
                "--port", str(config.handler.comfyui_port),
                "--input-directory", COMFYUI_INPUT,
                "--output-directory", COMFYUI_OUTPUT,
                "--extra-model-paths-config", config.paths.model_paths_config,
            ],
            cwd=COMFYUI_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1
        )

        # Start output capture thread
        capture_comfyui_output(comfyui_process)

        # Wait for health check
        server_ready = wait_for_health_check()

        if not server_ready:
            logger.error("Failed to start ComfyUI server")
            if comfyui_process:
                comfyui_process.kill()
                comfyui_process = None
            return False

        logger.info("✓ ComfyUI server started successfully")
        return True

    except Exception as e:
        logger.error(f"Error starting ComfyUI: {e}")
        logger.error(traceback.format_exc())
        if comfyui_process:
            comfyui_process.kill()
            comfyui_process = None
        server_ready = False
        return False


def ensure_comfyui_running() -> bool:
    """Ensure ComfyUI is running, restart if crashed.

    Returns:
        True if ComfyUI is running, False otherwise
    """
    global comfyui_process, server_ready

    # Check if process exists
    if comfyui_process is None:
        logger.warning("ComfyUI process not started, starting now...")
        return start_comfyui_server()

    # Check if process is alive
    if comfyui_process.poll() is not None:
        logger.error(f"ComfyUI process crashed with code {comfyui_process.returncode}")
        logger.error("Restarting ComfyUI...")
        comfyui_process = None
        server_ready = False
        return start_comfyui_server()

    # Check if server is responsive
    try:
        response = requests.get(
            f"http://localhost:{config.handler.comfyui_port}/system_stats",
            timeout=5
        )
        if response.status_code != 200:
            raise Exception(f"Unexpected status code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"ComfyUI not responsive: {e}")
        logger.error("Killing and restarting ComfyUI...")
        comfyui_process.kill()
        comfyui_process = None
        server_ready = False
        return start_comfyui_server()


def log_diagnostic_info():
    """Log extensive diagnostic information for debugging."""
    logger.info("=== DIAGNOSTIC INFO ===")

    # Log model availability
    model_types = ["checkpoints", "loras", "vae", "embeddings", "controlnet"]
    for model_type in model_types:
        path = os.path.join(MODELS_PATH, model_type)
        if os.path.exists(path):
            files = os.listdir(path)
            logger.info(f"{model_type}: {len(files)} files")
            for f in files[:5]:  # Log first 5
                try:
                    size_mb = os.path.getsize(os.path.join(path, f)) / (1024 * 1024)
                    logger.info(f"  - {f} ({size_mb:.1f} MB)")
                except:
                    logger.info(f"  - {f}")
            if len(files) > 5:
                logger.info(f"  ... and {len(files) - 5} more")
        else:
            logger.warning(f"{model_type}: DIRECTORY NOT FOUND")

    # Log input/output directories
    logger.info(f"Input directory: {len(os.listdir(COMFYUI_INPUT)) if os.path.exists(COMFYUI_INPUT) else 'N/A'} files")
    logger.info(f"Output directory: {len(os.listdir(COMFYUI_OUTPUT)) if os.path.exists(COMFYUI_OUTPUT) else 'N/A'} files")

    # Log ComfyUI status
    try:
        stats = requests.get(f"http://localhost:{config.handler.comfyui_port}/system_stats", timeout=5).json()
        logger.info(f"ComfyUI stats: {json.dumps(stats, indent=2)}")
    except Exception as e:
        logger.error(f"Failed to get ComfyUI stats: {e}")

    # Log process status
    if comfyui_process:
        logger.info(f"ComfyUI process alive: {comfyui_process.poll() is None}")


def validate_workflow(workflow: Dict[str, Any]) -> List[str]:
    """Validate workflow has all required models and images.

    Args:
        workflow: ComfyUI workflow JSON

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    for node_id, node in workflow.items():
        node_type = node.get("class_type")
        inputs = node.get("inputs", {})

        # Validate checkpoint models
        if node_type == "CheckpointLoaderSimple":
            ckpt_name = inputs.get("ckpt_name")
            if ckpt_name:
                ckpt_path = os.path.join(MODELS_PATH, "checkpoints", ckpt_name)
                if not os.path.exists(ckpt_path):
                    errors.append(f"Checkpoint not found: {ckpt_name}")

        # Validate LoRA models
        if node_type == "LoraLoader":
            lora_name = inputs.get("lora_name")
            if lora_name:
                lora_path = os.path.join(MODELS_PATH, "loras", lora_name)
                if not os.path.exists(lora_path):
                    errors.append(f"LoRA not found: {lora_name}")

        # Validate input images
        if node_type == "LoadImage":
            image_name = inputs.get("image")
            if image_name:
                image_path = os.path.join(COMFYUI_INPUT, image_name)
                if not os.path.exists(image_path):
                    errors.append(f"Input image not found: {image_name}")

    if errors:
        logger.warning(f"Workflow validation found {len(errors)} errors:")
        for error in errors:
            logger.warning(f"  - {error}")
    else:
        logger.info("✓ Workflow validation passed")

    return errors


def queue_prompt(workflow: Dict[str, Any]) -> str:
    """Queue workflow prompt to ComfyUI.

    Args:
        workflow: ComfyUI workflow JSON

    Returns:
        Prompt ID from ComfyUI
    """
    logger.info("Queuing workflow prompt...")

    response = requests.post(
        f"http://localhost:{config.handler.comfyui_port}/prompt",
        json={"prompt": workflow},
        timeout=30
    )
    response.raise_for_status()

    result = response.json()
    prompt_id = result.get("prompt_id")

    logger.info(f"✓ Workflow queued with prompt_id: {prompt_id}")
    return prompt_id


def wait_for_completion(prompt_id: str, timeout: int = None) -> Dict[str, Any]:
    """Wait for workflow execution to complete.

    Args:
        prompt_id: The prompt ID to wait for
        timeout: Timeout in seconds (uses config default if None)

    Returns:
        Execution result dictionary
    """
    if timeout is None:
        timeout = config.handler.execution_timeout

    logger.info(f"Waiting for completion (timeout: {timeout}s)...")
    start_time = time.time()
    last_health_check = time.time()

    while time.time() - start_time < timeout:
        # Periodic health check
        if time.time() - last_health_check > config.handler.health_check_interval:
            try:
                requests.get(f"http://localhost:{config.handler.comfyui_port}/system_stats", timeout=5)
                last_health_check = time.time()
            except:
                raise Exception("ComfyUI became unresponsive during execution")

        # Check execution status
        try:
            response = requests.get(
                f"http://localhost:{config.handler.comfyui_port}/history/{prompt_id}",
                timeout=10
            )
            history = response.json()

            if prompt_id in history:
                prompt_history = history[prompt_id]
                status = prompt_history.get("status", {})

                # Check for completion
                if status.get("completed", False):
                    logger.info("✓ Workflow execution completed")
                    return prompt_history

                # Check for errors
                if status.get("status_str") == "error":
                    error_msg = status.get("messages", ["Unknown error"])
                    raise Exception(f"Workflow execution failed: {error_msg}")

        except requests.exceptions.RequestException as e:
            logger.warning(f"Error checking status: {e}")

        time.sleep(2)

    raise Exception(f"Workflow execution timeout after {timeout}s")


def get_output_images(prompt_history: Dict[str, Any], return_base64: bool = True) -> List[Dict[str, Any]]:
    """Get output images from execution result.

    Args:
        prompt_history: Execution history from ComfyUI
        return_base64: Whether to return base64-encoded images

    Returns:
        List of output image dictionaries
    """
    images = []
    outputs = prompt_history.get("outputs", {})

    for node_id, node_output in outputs.items():
        if "images" in node_output:
            for img in node_output["images"]:
                filename = img.get("filename")
                if filename:
                    filepath = os.path.join(COMFYUI_OUTPUT, filename)

                    if return_base64:
                        with open(filepath, "rb") as f:
                            img_data = base64.b64encode(f.read()).decode("utf-8")
                            images.append({
                                "filename": filename,
                                "data": img_data
                            })
                    else:
                        images.append({
                            "filename": filename,
                            "path": filepath
                        })

    logger.info(f"✓ Collected {len(images)} output images")
    return images


def create_error_response(error_message: str, exception: Exception = None, diagnostic_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create detailed error response for debugging.

    Args:
        error_message: Main error message
        exception: Exception object (if any)
        diagnostic_info: Additional diagnostic information

    Returns:
        Error response dictionary
    """
    response = {
        "status": "error",
        "error": error_message,
        "timestamp": datetime.utcnow().isoformat()
    }

    if exception:
        response["traceback"] = traceback.format_exc()
        response["exception_type"] = type(exception).__name__

    if diagnostic_info:
        response["diagnostic_info"] = diagnostic_info

    # Always include system state
    response["system_state"] = {
        "comfyui_running": comfyui_process and comfyui_process.poll() is None,
        "comfyui_responsive": False,
        "recent_logs": get_recent_comfyui_logs(20)
    }

    # Try to get ComfyUI responsiveness
    try:
        requests.get(f"http://localhost:{config.handler.comfyui_port}/system_stats", timeout=5)
        response["system_state"]["comfyui_responsive"] = True
    except:
        pass

    return response


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """Main handler function for RunPod serverless requests.

    Args:
        event: RunPod event dictionary with 'input' key

    Returns:
        Response dictionary with status and results/errors
    """
    try:
        logger.info("=== NEW REQUEST ===")
        logger.info(f"Event keys: {list(event.keys())}")

        # Extract input
        input_data = event.get("input", {})
        workflow = input_data.get("workflow")
        reference_images = input_data.get("reference_images", {})
        return_base64 = input_data.get("return_base64", config.handler.return_base64)

        if not workflow:
            return create_error_response("Missing 'workflow' in input")

        # Ensure ComfyUI is running
        logger.info("Checking ComfyUI health...")
        if not ensure_comfyui_running():
            return create_error_response("Failed to start ComfyUI server")

        # Log diagnostic info
        log_diagnostic_info()

        # Save reference images to input directory
        if reference_images:
            logger.info(f"Saving {len(reference_images)} reference images...")
            for filename, base64_data in reference_images.items():
                # Support subdirectories
                full_path = os.path.join(COMFYUI_INPUT, filename)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                with open(full_path, 'wb') as f:
                    f.write(base64.b64decode(base64_data))
                logger.info(f"  ✓ Saved: {filename}")

        # Validate workflow
        validation_errors = validate_workflow(workflow)
        if validation_errors:
            return create_error_response(
                "Workflow validation failed",
                diagnostic_info={"validation_errors": validation_errors}
            )

        # Queue prompt
        prompt_id = queue_prompt(workflow)

        # Wait for completion
        prompt_history = wait_for_completion(prompt_id)

        # Get output images
        images = get_output_images(prompt_history, return_base64)

        # Cleanup old outputs
        cleanup_outputs(COMFYUI_OUTPUT, config.handler.cleanup_age)

        # Return success
        logger.info("=== REQUEST COMPLETED ===")
        return {
            "status": "success",
            "prompt_id": prompt_id,
            "images": images,
            "image_count": len(images)
        }

    except Exception as e:
        logger.error(f"Handler error: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(str(e), exception=e)


def initialize_worker():
    """Initialize worker - called once on worker start."""
    logger.info("=== WORKER INITIALIZATION ===")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Models path: {MODELS_PATH}")
    logger.info(f"ComfyUI path: {COMFYUI_PATH}")

    # Validate configuration
    errors = config.validate()
    if errors:
        logger.warning(f"Configuration validation warnings: {errors}")

    # Start ComfyUI immediately
    logger.info("Starting ComfyUI server during worker initialization...")
    success = start_comfyui_server()

    if success:
        logger.info("✓✓✓ Worker initialization complete - ComfyUI is ready ✓✓✓")
    else:
        logger.error("✗✗✗ Worker initialization failed - ComfyUI not ready ✗✗✗")
        # Don't raise exception - let handler attempt restart on first request


# Initialize worker when module loads (worker start)
try:
    initialize_worker()
except Exception as e:
    logger.error(f"Error during worker initialization: {e}")
    logger.error(traceback.format_exc())


# RunPod serverless entry point
if __name__ == "__main__":
    logger.info("Starting RunPod serverless handler...")
    runpod.serverless.start({"handler": handler})
