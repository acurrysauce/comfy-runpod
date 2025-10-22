"""
RunPod Queue Button - Custom ComfyUI Extension

Adds a "Queue on RunPod" button to the ComfyUI interface that sends
workflows to your RunPod serverless endpoint instead of running locally.
"""

import os
import json
import subprocess
import asyncio
from pathlib import Path
from aiohttp import web
import server
import requests

# Get the project root (3 levels up from custom_nodes directory)
# This file is at: docker/ComfyUI/custom_nodes/runpod-queue/__init__.py
# Project root is: /home/acurry/comfy-runpod
CUSTOM_NODE_DIR = Path(__file__).parent
COMFYUI_DIR = CUSTOM_NODE_DIR.parent.parent  # docker/ComfyUI
PROJECT_ROOT = COMFYUI_DIR.parent.parent  # /home/acurry/comfy-runpod

print(f"DEBUG: Custom node dir: {CUSTOM_NODE_DIR}")
print(f"DEBUG: ComfyUI dir: {COMFYUI_DIR}")
print(f"DEBUG: Project root: {PROJECT_ROOT}")

WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']


def calculate_node_depths(workflow):
    """Calculate the depth of each node in the workflow graph.

    Depth is the longest path from any input node to this node.
    This helps us order SaveImage outputs by execution order.
    """
    depths = {}

    def get_depth(node_id):
        if node_id in depths:
            return depths[node_id]

        node = workflow.get(str(node_id))
        if not node:
            return 0

        # Find maximum depth of all input nodes
        max_input_depth = 0
        inputs = node.get('inputs', {})
        for input_value in inputs.values():
            # Input can be a list like ["node_id", output_index]
            if isinstance(input_value, list) and len(input_value) >= 2:
                input_node_id = str(input_value[0])
                input_depth = get_depth(input_node_id)
                max_input_depth = max(max_input_depth, input_depth)

        # This node's depth is one more than its deepest input
        depths[node_id] = max_input_depth + 1
        return depths[node_id]

    # Calculate depth for all nodes
    for node_id in workflow.keys():
        get_depth(str(node_id))

    return depths


def get_image_depths(workflow):
    """Get a mapping of filename prefixes to their node depths."""
    depths = calculate_node_depths(workflow)
    image_depths = {}

    for node_id, node_data in workflow.items():
        if node_data.get('class_type') == 'SaveImage':
            filename_prefix = node_data.get('inputs', {}).get('filename_prefix', '')
            if filename_prefix:
                image_depths[filename_prefix] = depths.get(str(node_id), 0)

    return image_depths


# Store the most recent workflow's image depths
current_image_depths = {}


@server.PromptServer.instance.routes.post('/runpod/queue')
async def queue_on_runpod(request):
    """Handle workflow submission to RunPod.

    This endpoint is called by the frontend button.
    """
    global current_image_depths

    try:
        data = await request.json()
        workflow = data.get('workflow', {})

        # Calculate image depths for sorting
        current_image_depths = get_image_depths(workflow)

        # Save workflow to temp file
        temp_workflow = PROJECT_ROOT / "temp_workflow.json"
        with open(temp_workflow, 'w') as f:
            json.dump(workflow, f, indent=2)

        # Call send-to-runpod script
        script_path = PROJECT_ROOT / "scripts" / "send-to-runpod.py"
        log_file = PROJECT_ROOT / "send-to-runpod.log"

        # Run in background so we don't block the UI
        # Log output to file so we can debug issues
        # Set cwd to project root so ./output resolves correctly
        # Use --no-open since we'll display images in the browser
        with open(log_file, 'a') as log:
            subprocess.Popen(
                ['python3', str(script_path), '--workflow', str(temp_workflow), '--no-open'],
                stdout=log,
                stderr=log,
                cwd=str(PROJECT_ROOT)
            )

        return web.json_response({
            "status": "submitted",
            "message": "Workflow submitted to RunPod! Check terminal for progress."
        })

    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)


@server.PromptServer.instance.routes.get('/runpod/latest_images')
async def get_latest_images(request):
    """Get the latest images from output directory for display."""
    try:
        output_dir = PROJECT_ROOT / "output"

        if not output_dir.exists():
            return web.json_response({
                "status": "success",
                "images": []
            })

        # Get all PNG files sorted by modification time (newest first)
        images = sorted(
            output_dir.glob("*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        # Return the 10 most recent images with their URLs and depths
        recent_images = []
        for img_path in images[:10]:
            # Extract filename prefix (remove _00001_.png suffix)
            filename = img_path.name
            # Match pattern: prefix_NNNNN_.png
            import re
            match = re.match(r'(.+?)_\d+_\.png$', filename)
            prefix = match.group(1) if match else filename.replace('.png', '')

            # Look up depth for this prefix
            depth = current_image_depths.get(prefix, 999)  # Default to 999 if not found

            # ComfyUI serves output files via /view endpoint
            recent_images.append({
                "filename": filename,
                "url": f"/view?filename={filename}",
                "modified": img_path.stat().st_mtime,
                "depth": depth
            })

        return web.json_response({
            "status": "success",
            "images": recent_images
        })

    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)


@server.PromptServer.instance.routes.get('/runpod/worker_status')
async def get_worker_status(request):
    """Get the current worker status for the RunPod endpoint.

    Returns the current min_workers, max_workers, and endpoint configuration.
    """
    try:
        # Get credentials from environment
        api_key = os.getenv('RUNPOD_API_KEY')
        endpoint_id = os.getenv('RUNPOD_ENDPOINT_ID')

        if not api_key:
            return web.json_response({
                "status": "error",
                "message": "RUNPOD_API_KEY environment variable not set"
            }, status=500)

        if not endpoint_id:
            return web.json_response({
                "status": "error",
                "message": "RUNPOD_ENDPOINT_ID environment variable not set"
            }, status=500)

        # GraphQL endpoint
        url = "https://api.runpod.io/graphql"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Query current state
        query = """
        query {
            myself {
                endpoints {
                    id
                    name
                    workersMin
                    workersMax
                    idleTimeout
                }
            }
        }
        """

        response = requests.post(url, json={"query": query}, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Check for GraphQL errors
        if "errors" in data:
            error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
            return web.json_response({
                "status": "error",
                "message": f"GraphQL error: {error_msg}"
            }, status=500)

        # Find our specific endpoint
        endpoints = data.get("data", {}).get("myself", {}).get("endpoints", [])
        if not endpoints:
            return web.json_response({
                "status": "error",
                "message": "No endpoints found"
            }, status=404)

        endpoint_data = None
        for ep in endpoints:
            if ep.get("id") == endpoint_id:
                endpoint_data = ep
                break

        if not endpoint_data:
            return web.json_response({
                "status": "error",
                "message": f"Endpoint {endpoint_id} not found"
            }, status=404)

        # Return endpoint status
        return web.json_response({
            "status": "success",
            "endpoint_id": endpoint_data.get("id"),
            "endpoint_name": endpoint_data.get("name"),
            "workers_min": endpoint_data.get("workersMin", 0),
            "workers_max": endpoint_data.get("workersMax", 3),
            "idle_timeout": endpoint_data.get("idleTimeout", 5)
        })

    except requests.exceptions.Timeout:
        return web.json_response({
            "status": "error",
            "message": "Request to RunPod API timed out"
        }, status=504)
    except requests.exceptions.RequestException as e:
        return web.json_response({
            "status": "error",
            "message": f"Failed to communicate with RunPod API: {str(e)}"
        }, status=500)
    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }, status=500)


@server.PromptServer.instance.routes.post('/runpod/toggle_workers')
async def toggle_workers(request):
    """Toggle the RunPod endpoint's min_workers between 0 and 1.

    This allows users to easily switch between cost-saving mode (0 workers)
    and instant-response mode (1 worker) without going to the RunPod dashboard.
    """
    try:
        # Get credentials from environment
        api_key = os.getenv('RUNPOD_API_KEY')
        endpoint_id = os.getenv('RUNPOD_ENDPOINT_ID')

        if not api_key:
            return web.json_response({
                "status": "error",
                "message": "RUNPOD_API_KEY environment variable not set"
            }, status=500)

        if not endpoint_id:
            return web.json_response({
                "status": "error",
                "message": "RUNPOD_ENDPOINT_ID environment variable not set"
            }, status=500)

        # GraphQL endpoint
        url = "https://api.runpod.io/graphql"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # First, query current state
        query = """
        query {
            myself {
                endpoints {
                    id
                    workersMin
                    workersMax
                }
            }
        }
        """

        response = requests.post(url, json={"query": query}, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Check for GraphQL errors
        if "errors" in data:
            error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
            return web.json_response({
                "status": "error",
                "message": f"GraphQL error: {error_msg}"
            }, status=500)

        # Extract current workersMin for our endpoint
        endpoints = data.get("data", {}).get("myself", {}).get("endpoints", [])
        if not endpoints:
            return web.json_response({
                "status": "error",
                "message": "No endpoints found"
            }, status=404)

        # Find our specific endpoint
        endpoint_data = None
        for ep in endpoints:
            if ep.get("id") == endpoint_id:
                endpoint_data = ep
                break

        if not endpoint_data:
            return web.json_response({
                "status": "error",
                "message": f"Endpoint {endpoint_id} not found"
            }, status=404)

        current_workers_min = endpoint_data.get("workersMin", 0)
        workers_max = endpoint_data.get("workersMax", 3)

        # Toggle: 0 -> 1, 1 -> 0
        new_workers_min = 0 if current_workers_min >= 1 else 1

        # Update endpoint with mutation
        mutation = """
        mutation {
            updateEndpointWorkersMin(input: {
                endpointId: "%s",
                workerCount: %d
            }) {
                id
                workersMin
                workersMax
            }
        }
        """ % (endpoint_id, new_workers_min)

        response = requests.post(url, json={"query": mutation}, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Check for GraphQL errors
        if "errors" in data:
            error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
            return web.json_response({
                "status": "error",
                "message": f"GraphQL error: {error_msg}"
            }, status=500)

        # Success
        return web.json_response({
            "status": "success",
            "workers_min": new_workers_min,
            "workers_max": workers_max,
            "message": f"Updated min_workers from {current_workers_min} to {new_workers_min}"
        })

    except requests.exceptions.Timeout:
        return web.json_response({
            "status": "error",
            "message": "Request to RunPod API timed out"
        }, status=504)
    except requests.exceptions.RequestException as e:
        return web.json_response({
            "status": "error",
            "message": f"Failed to communicate with RunPod API: {str(e)}"
        }, status=500)
    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }, status=500)


print("\n" + "="*60)
print("RunPod Queue Extension Loaded")
print("="*60)
print("Added 'Queue on RunPod' button to ComfyUI interface")
print(f"Project root: {PROJECT_ROOT}")
print("="*60 + "\n")
