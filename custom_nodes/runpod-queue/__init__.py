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


@server.PromptServer.instance.routes.post('/runpod/queue')
async def queue_on_runpod(request):
    """Handle workflow submission to RunPod.

    This endpoint is called by the frontend button.
    """
    try:
        data = await request.json()
        workflow = data.get('workflow', {})

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

        # Return the 10 most recent images with their URLs
        recent_images = []
        for img_path in images[:10]:
            # ComfyUI serves output files via /view endpoint
            recent_images.append({
                "filename": img_path.name,
                "url": f"/view?filename={img_path.name}",
                "modified": img_path.stat().st_mtime
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


print("\n" + "="*60)
print("RunPod Queue Extension Loaded")
print("="*60)
print("Added 'Queue on RunPod' button to ComfyUI interface")
print(f"Project root: {PROJECT_ROOT}")
print("="*60 + "\n")
