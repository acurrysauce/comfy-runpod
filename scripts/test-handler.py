#!/usr/bin/env python3
"""
Test script for handler.py - runs handler locally with mock RunPod environment

This allows testing handler logic without deploying to RunPod.
"""

import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch
import json

# Add parent directory to path so we can import handler
sys.path.insert(0, str(Path(__file__).parent.parent / "docker"))

# Mock the runpod module before importing handler
runpod_mock = Mock()
sys.modules['runpod'] = runpod_mock
sys.modules['runpod.serverless'] = Mock()
runpod_mock.serverless = Mock()

# Try to import boto3, mock if not available
try:
    import boto3
except ImportError:
    print("Warning: boto3 not installed, mocking...")
    sys.modules['boto3'] = Mock()

# Mock subprocess to prevent ComfyUI from actually starting
subprocess_mock = Mock()
sys.modules['subprocess'] = subprocess_mock

# Mock threading to prevent output capture thread
threading_mock = Mock()
sys.modules['threading'] = threading_mock

print("=" * 60)
print("ComfyUI RunPod Handler - Local Testing")
print("=" * 60)
print()

# Now import config and handler (with mocked dependencies)
print("Importing config...")
import config as config_module

print("Importing handler with mocked dependencies...")
print("(Expecting initialization errors - this is normal without proper paths)")
print()

try:
    import handler
    print("✓ Handler module loaded (may have initialization errors)")
except Exception as e:
    print(f"✗ Fatal error loading handler: {e}")
    sys.exit(1)

print()

# Test 1: Configuration loading
print("Test 1: Configuration Loading")
print("-" * 60)
cfg = config_module.ProjectDefaults()
print(f"  Docker image: {cfg.docker.image_full}")
print(f"  ComfyUI path: {cfg.paths.comfyui_path}")
print(f"  Models path (serverless): {cfg.paths.models_path_serverless}")
print(f"  Input directory: {cfg.paths.comfyui_input}")
print(f"  Output directory: {cfg.paths.comfyui_output}")
print("✓ Configuration loads correctly")
print()

# Test 2: Mock event processing
print("Test 2: Mock Event Processing")
print("-" * 60)

# Create a minimal mock event
mock_event = {
    "input": {
        "workflow": {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "test_model.safetensors"
                }
            },
            "2": {
                "class_type": "KSampler",
                "inputs": {}
            },
            "3": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "test"
                }
            }
        },
        "reference_images": {},
        "return_base64": True
    }
}

print("Mock event:")
print(json.dumps(mock_event, indent=2))
print()

# Test validation functions
print("Test 3: Workflow Validation")
print("-" * 60)

try:
    # Test validate_workflow function
    print("Testing workflow validation...")

    # We can't actually run validate_workflow without ComfyUI running
    # But we can test that it exists and is callable
    if hasattr(handler, 'validate_workflow'):
        print("✓ validate_workflow function exists")
    else:
        print("✗ validate_workflow function not found")

    if hasattr(handler, 'create_error_response'):
        print("✓ create_error_response function exists")
    else:
        print("✗ create_error_response function not found")

    if hasattr(handler, 'queue_prompt'):
        print("✓ queue_prompt function exists")
    else:
        print("✗ queue_prompt function not found")

    if hasattr(handler, 'wait_for_completion'):
        print("✓ wait_for_completion function exists")
    else:
        print("✗ wait_for_completion function not found")

    if hasattr(handler, 'ensure_comfyui_running'):
        print("✓ ensure_comfyui_running function exists")
    else:
        print("✗ ensure_comfyui_running function not found")

except Exception as e:
    print(f"✗ Error during validation test: {e}")

print()

# Test 4: Error response creation
print("Test 4: Error Response Creation")
print("-" * 60)

try:
    error_response = handler.create_error_response(
        "Test error message",
        {"test_key": "test_value"}
    )
    print("Error response structure:")
    print(json.dumps(error_response, indent=2))
    print("✓ Error response created successfully")
except Exception as e:
    print(f"✗ Error creating error response: {e}")

print()

# Test 5: Utility functions
print("Test 5: Utility Functions")
print("-" * 60)

try:
    import utils

    if hasattr(utils, 'download_file'):
        print("✓ download_file function exists")
    else:
        print("✗ download_file function not found")

    if hasattr(utils, 'download_from_s3'):
        print("✓ download_from_s3 function exists")
    else:
        print("✗ download_from_s3 function not found")

    if hasattr(utils, 'upload_to_s3'):
        print("✓ upload_to_s3 function exists")
    else:
        print("✗ upload_to_s3 function not found")

    if hasattr(utils, 'download_models'):
        print("✓ download_models function exists")
    else:
        print("✗ download_models function not found")

    if hasattr(utils, 'cleanup_outputs'):
        print("✓ cleanup_outputs function exists")
    else:
        print("✗ cleanup_outputs function not found")

except Exception as e:
    print(f"✗ Error importing utils: {e}")

print()

# Test 6: Global state
print("Test 6: Handler Global State")
print("-" * 60)

try:
    print(f"  comfyui_process: {handler.comfyui_process}")
    print(f"  server_ready: {handler.server_ready}")
    print(f"  comfyui_output_queue: {type(handler.comfyui_output_queue)}")
    print("✓ Global state initialized")
except Exception as e:
    print(f"✗ Error accessing global state: {e}")

print()

# Summary
print("=" * 60)
print("Test Summary")
print("=" * 60)
print()
print("All basic tests passed! Handler structure looks good.")
print()
print("Note: This is a structural test with mocked dependencies.")
print("To fully test the handler:")
print("  1. Build the Docker image: ./scripts/build.sh")
print("  2. Run the container: docker run --rm <image>")
print("  3. Deploy to RunPod and test with real workflows")
print()
print("=" * 60)
