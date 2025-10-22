#!/usr/bin/env python3
"""
RunPod API Client for ComfyUI Workflows

Submits ComfyUI workflows to RunPod serverless endpoint and retrieves results.

Usage:
    python scripts/send-to-runpod.py --workflow workflow.json
    python scripts/send-to-runpod.py --workflow workflow.json --images image1.png image2.png
    python scripts/send-to-runpod.py --workflow workflow.json --images-dir input/
"""

import argparse
import os
import sys
import json
import base64
import time
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from docker.config import config
except ImportError:
    # Fallback if running without proper installation
    class MockConfig:
        class RunPod:
            api_key = os.getenv("RUNPOD_API_KEY", "")
            endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID", "")
        class Paths:
            local_input = "./input"
            local_output = "./output"
        runpod = RunPod()
        paths = Paths()
    config = MockConfig()


RUNPOD_API_BASE = "https://api.runpod.ai/v2"


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Submit ComfyUI workflows to RunPod serverless endpoint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  RUNPOD_API_KEY       RunPod API key (required)
  RUNPOD_ENDPOINT_ID   RunPod endpoint ID (required)

Examples:
  # Submit workflow without reference images
  python scripts/send-to-runpod.py --workflow workflows/txt2img.json

  # Submit with reference images
  python scripts/send-to-runpod.py --workflow workflows/img2img.json --images input/ref.png

  # Submit with multiple images
  python scripts/send-to-runpod.py --workflow workflows/inpaint.json --images input/image.png input/mask.png

  # Submit all images from directory
  python scripts/send-to-runpod.py --workflow workflows/batch.json --images-dir input/

  # Custom output directory
  python scripts/send-to-runpod.py --workflow workflows/txt2img.json --output output/results/

  # Disable auto-open
  python scripts/send-to-runpod.py --workflow workflows/txt2img.json --no-open
        """
    )

    parser.add_argument(
        "--workflow",
        type=str,
        required=True,
        help="Path to ComfyUI workflow JSON file"
    )

    parser.add_argument(
        "--images",
        nargs="*",
        help="Reference image files to include"
    )

    parser.add_argument(
        "--images-dir",
        type=str,
        help="Directory containing reference images (includes subdirectories)"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=config.paths.local_output,
        help=f"Output directory for results (default: {config.paths.local_output})"
    )

    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't automatically open result images"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout in seconds (default: 600 = 10 minutes)"
    )

    parser.add_argument(
        "--poll-interval",
        type=int,
        default=2,
        help="Status polling interval in seconds (default: 2)"
    )

    parser.add_argument(
        "--api-key",
        type=str,
        help="RunPod API key (overrides RUNPOD_API_KEY env var)"
    )

    parser.add_argument(
        "--endpoint-id",
        type=str,
        help="RunPod endpoint ID (overrides RUNPOD_ENDPOINT_ID env var)"
    )

    return parser.parse_args()


def check_credentials(api_key: str, endpoint_id: str) -> bool:
    """Validate that credentials are provided.

    Args:
        api_key: RunPod API key
        endpoint_id: RunPod endpoint ID

    Returns:
        bool: True if credentials are valid
    """
    if not api_key:
        print("ERROR: RUNPOD_API_KEY not set")
        print("Set it via environment variable or --api-key argument")
        return False

    if not endpoint_id:
        print("ERROR: RUNPOD_ENDPOINT_ID not set")
        print("Set it via environment variable or --endpoint-id argument")
        return False

    return True


def read_workflow(workflow_path: str) -> Optional[dict]:
    """Read and parse workflow JSON file.

    Args:
        workflow_path: Path to workflow JSON file

    Returns:
        dict: Workflow data or None if error
    """
    try:
        with open(workflow_path, 'r') as f:
            workflow = json.load(f)
        return workflow
    except FileNotFoundError:
        print(f"ERROR: Workflow file not found: {workflow_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in workflow file: {e}")
        return None
    except Exception as e:
        print(f"ERROR: Failed to read workflow: {e}")
        return None


def encode_image_base64(image_path: str) -> Optional[str]:
    """Encode image file as base64 string.

    Args:
        image_path: Path to image file

    Returns:
        str: Base64 encoded image or None if error
    """
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
        encoded = base64.b64encode(image_data).decode('utf-8')
        return encoded
    except Exception as e:
        print(f"ERROR: Failed to encode image {image_path}: {e}")
        return None


def collect_images(image_paths: Optional[List[str]], images_dir: Optional[str]) -> Dict[str, str]:
    """Collect and encode all reference images.

    Args:
        image_paths: List of individual image paths
        images_dir: Directory to scan for images

    Returns:
        dict: Mapping of relative paths to base64 encoded images
    """
    reference_images = {}

    # Process individual images
    if image_paths:
        for image_path in image_paths:
            if not os.path.exists(image_path):
                print(f"WARNING: Image not found: {image_path}")
                continue

            encoded = encode_image_base64(image_path)
            if encoded:
                # Use just the filename as key
                filename = os.path.basename(image_path)
                reference_images[filename] = encoded
                print(f"  Encoded: {filename}")

    # Process images directory
    if images_dir:
        if not os.path.exists(images_dir):
            print(f"WARNING: Images directory not found: {images_dir}")
        else:
            images_path = Path(images_dir)
            # Find all image files recursively
            image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}

            for image_file in images_path.rglob('*'):
                if image_file.is_file() and image_file.suffix.lower() in image_extensions:
                    encoded = encode_image_base64(str(image_file))
                    if encoded:
                        # Use relative path from images_dir as key
                        rel_path = image_file.relative_to(images_path)
                        reference_images[str(rel_path)] = encoded
                        print(f"  Encoded: {rel_path}")

    return reference_images


def submit_job(api_key: str, endpoint_id: str, workflow: dict, reference_images: dict) -> Optional[str]:
    """Submit job to RunPod API.

    Args:
        api_key: RunPod API key
        endpoint_id: RunPod endpoint ID
        workflow: ComfyUI workflow data
        reference_images: Dict of base64 encoded images

    Returns:
        str: Job ID or None if error
    """
    url = f"{RUNPOD_API_BASE}/{endpoint_id}/run"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "input": {
            "workflow": workflow,
            "reference_images": reference_images,
            "return_base64": True
        }
    }

    try:
        print("\nSubmitting job to RunPod...")
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code == 200:
            data = response.json()
            job_id = data.get("id")
            print(f"✓ Job submitted: {job_id}")
            return job_id
        else:
            print(f"✗ Failed to submit job: {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except requests.exceptions.Timeout:
        print("✗ Request timed out")
        return None
    except Exception as e:
        print(f"✗ Error submitting job: {e}")
        return None


def poll_status(api_key: str, endpoint_id: str, job_id: str, timeout: int, poll_interval: int) -> Optional[dict]:
    """Poll job status until completion or timeout.

    Args:
        api_key: RunPod API key
        endpoint_id: RunPod endpoint ID
        job_id: Job ID to poll
        timeout: Maximum time to wait in seconds
        poll_interval: Time between polls in seconds

    Returns:
        dict: Job result or None if error/timeout
    """
    url = f"{RUNPOD_API_BASE}/{endpoint_id}/status/{job_id}"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    start_time = time.time()
    dots = 0

    print("\nWaiting for job completion...")

    while True:
        elapsed = time.time() - start_time

        if elapsed > timeout:
            print(f"\n✗ Timeout after {timeout} seconds")
            return None

        try:
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                status = data.get("status")

                # Show progress
                dots = (dots + 1) % 4
                print(f"\r  Status: {status}" + "." * dots + " " * (3 - dots), end="", flush=True)

                if status == "COMPLETED":
                    print("\n✓ Job completed!")
                    return data

                elif status == "FAILED":
                    print("\n✗ Job failed")
                    print(f"Error: {data.get('error', 'Unknown error')}")
                    return None

                elif status == "CANCELLED":
                    print("\n✗ Job cancelled")
                    return None

                elif status in ["IN_QUEUE", "IN_PROGRESS"]:
                    # Continue polling
                    time.sleep(poll_interval)

                else:
                    print(f"\n⚠ Unknown status: {status}")
                    time.sleep(poll_interval)

            else:
                print(f"\n✗ Failed to get status: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            print("\n⚠ Status check timed out, retrying...")
            time.sleep(poll_interval)
        except Exception as e:
            print(f"\n✗ Error polling status: {e}")
            return None


def save_results(result_data: dict, output_dir: str) -> List[str]:
    """Save result images to output directory.

    Args:
        result_data: Job result data from RunPod
        output_dir: Directory to save images

    Returns:
        list: Paths to saved images
    """
    os.makedirs(output_dir, exist_ok=True)

    saved_files = []
    output_data = result_data.get("output", {})

    # Handle different output formats
    if isinstance(output_data, dict):
        images = output_data.get("images", [])
    elif isinstance(output_data, list):
        images = output_data
    else:
        print("⚠ Unexpected output format")
        return []

    if not images:
        print("⚠ No images in result")
        return []

    print(f"\nSaving {len(images)} image(s)...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for i, image_data in enumerate(images):
        # Image data might be base64 string or dict with base64 data
        if isinstance(image_data, str):
            base64_data = image_data
            filename = f"output_{timestamp}_{i:03d}.png"
        elif isinstance(image_data, dict):
            base64_data = image_data.get("data") or image_data.get("image")
            filename = image_data.get("filename", f"output_{timestamp}_{i:03d}.png")
        else:
            print(f"  ⚠ Skipping image {i}: unexpected format")
            continue

        try:
            # Decode base64
            image_bytes = base64.b64decode(base64_data)

            # Save to file
            output_path = os.path.join(output_dir, filename)
            with open(output_path, 'wb') as f:
                f.write(image_bytes)

            saved_files.append(output_path)
            file_size = len(image_bytes) / 1024  # KB
            print(f"  ✓ Saved: {filename} ({file_size:.1f} KB)")

        except Exception as e:
            print(f"  ✗ Failed to save image {i}: {e}")

    return saved_files


def open_images(image_paths: List[str]):
    """Open images in default viewer.

    Args:
        image_paths: List of image file paths
    """
    if not image_paths:
        return

    print(f"\nOpening {len(image_paths)} image(s)...")

    import platform
    system = platform.system()

    for image_path in image_paths:
        try:
            if system == "Darwin":  # macOS
                os.system(f'open "{image_path}"')
            elif system == "Windows":
                os.system(f'start "" "{image_path}"')
            else:  # Linux
                os.system(f'xdg-open "{image_path}"')
        except Exception as e:
            print(f"  ⚠ Failed to open {image_path}: {e}")


def main():
    """Main execution function."""
    args = parse_args()

    print("=" * 60)
    print("RunPod ComfyUI Workflow Client")
    print("=" * 60)
    print()

    # Get credentials
    api_key = args.api_key or config.runpod.api_key
    endpoint_id = args.endpoint_id or config.runpod.endpoint_id

    # Validate credentials
    if not check_credentials(api_key, endpoint_id):
        sys.exit(1)

    print(f"Endpoint ID: {endpoint_id}")
    print(f"Workflow: {args.workflow}")
    print(f"Output: {args.output}")
    print()

    # Read workflow
    print("Reading workflow...")
    workflow = read_workflow(args.workflow)
    if not workflow:
        sys.exit(1)

    node_count = len(workflow)
    print(f"✓ Workflow loaded: {node_count} nodes")

    # Collect reference images
    reference_images = {}
    if args.images or args.images_dir:
        print("\nEncoding reference images...")
        reference_images = collect_images(args.images, args.images_dir)
        print(f"✓ Encoded {len(reference_images)} image(s)")

    # Submit job
    job_id = submit_job(api_key, endpoint_id, workflow, reference_images)
    if not job_id:
        sys.exit(1)

    # Poll for completion
    result = poll_status(api_key, endpoint_id, job_id, args.timeout, args.poll_interval)
    if not result:
        sys.exit(1)

    # Save results
    saved_files = save_results(result, args.output)

    if saved_files:
        print()
        print("=" * 60)
        print("SUCCESS")
        print("=" * 60)
        print(f"Saved {len(saved_files)} image(s) to: {args.output}")

        # Open images if requested
        if not args.no_open:
            open_images(saved_files)
    else:
        print("\n⚠ No images saved")

    print()


if __name__ == "__main__":
    main()
