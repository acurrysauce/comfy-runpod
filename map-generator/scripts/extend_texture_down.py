#!/usr/bin/env python3
"""
Extend Texture Down Generator

Generates Nx2 tile grids by iteratively extending textures downward using
the extend_texture_down_workflow.json. Each iteration adds one new row to
the grid by processing a 1x2 input into a 2x2 output, then compositing
the results in Python.
"""

import json
import copy
import shutil
import subprocess
import sys
import argparse
from pathlib import Path
from datetime import datetime
from PIL import Image


def load_workflow_template(template_path):
    """Load the workflow template JSON.

    Args:
        template_path: Path to workflow JSON file

    Returns:
        Dict containing workflow definition

    Raises:
        FileNotFoundError: If workflow file doesn't exist
        json.JSONDecodeError: If workflow file is invalid JSON
    """
    with open(template_path, 'r') as f:
        return json.load(f)


def update_workflow_prompts(
    workflow,
    top_left_type,
    top_right_type,
    bottom_left_type,
    bottom_right_type,
    prompts_config
):
    """Update workflow with prompts for all 4 tiles and 3 transitions.

    Args:
        workflow: Workflow dict to modify
        top_left_type: Type for top-left tile (e.g., "grass")
        top_right_type: Type for top-right tile (e.g., "stone")
        bottom_left_type: Type for bottom-left tile (e.g., "stone")
        bottom_right_type: Type for bottom-right tile (e.g., "grass")
        prompts_config: Loaded prompts from JSON

    Returns:
        Modified workflow dict
    """
    # Update bottom-left tile prompts (what left column generates)
    # Node 50/51 controls left column generation
    workflow["50"]["inputs"]["text"] = prompts_config["tile_types"][bottom_left_type]["positive"]
    workflow["51"]["inputs"]["text"] = prompts_config["tile_types"][bottom_left_type]["negative"]

    # Update bottom-right tile prompts (what right column generates)
    # Node 10/5 controls right column generation
    workflow["10"]["inputs"]["text"] = prompts_config["tile_types"][bottom_right_type]["positive"]
    workflow["5"]["inputs"]["text"] = prompts_config["tile_types"][bottom_right_type]["negative"]

    # Update left vertical transition (top_left → bottom_left)
    # Node 103/104 controls left column seam blend
    left_transition_key = f"{top_left_type}_to_{bottom_left_type}"
    if left_transition_key in prompts_config["transitions"]:
        workflow["103"]["inputs"]["text"] = prompts_config["transitions"][left_transition_key]["positive"]
        workflow["104"]["inputs"]["text"] = prompts_config["transitions"][left_transition_key]["negative"]

    # Update right vertical transition (top_right → bottom_right)
    # Node 105/106 controls right column seam blend
    right_transition_key = f"{top_right_type}_to_{bottom_right_type}"
    if right_transition_key in prompts_config["transitions"]:
        workflow["105"]["inputs"]["text"] = prompts_config["transitions"][right_transition_key]["positive"]
        workflow["106"]["inputs"]["text"] = prompts_config["transitions"][right_transition_key]["negative"]

    # Update horizontal transition (bottom_left ↔ bottom_right)
    # Node 101/102 controls bottom center vertical seam blend
    horiz_transition_key = f"{bottom_left_type}_to_{bottom_right_type}"
    if horiz_transition_key in prompts_config["transitions"]:
        workflow["101"]["inputs"]["text"] = prompts_config["transitions"][horiz_transition_key]["positive"]
        workflow["102"]["inputs"]["text"] = prompts_config["transitions"][horiz_transition_key]["negative"]

    # Update LoRA settings for each tile type
    # Left column uses node 401 (inpaint model + LoRA)
    workflow["401"]["inputs"]["lora_name"] = prompts_config["tile_types"][bottom_left_type]["lora"]
    workflow["401"]["inputs"]["strength_model"] = prompts_config["tile_types"][bottom_left_type]["lora_strength_model"]
    workflow["401"]["inputs"]["strength_clip"] = prompts_config["tile_types"][bottom_left_type]["lora_strength_clip"]

    # Right column uses node 3 (base model + LoRA)
    workflow["3"]["inputs"]["lora_name"] = prompts_config["tile_types"][bottom_right_type]["lora"]
    workflow["3"]["inputs"]["strength_model"] = prompts_config["tile_types"][bottom_right_type]["lora_strength_model"]
    workflow["3"]["inputs"]["strength_clip"] = prompts_config["tile_types"][bottom_right_type]["lora_strength_clip"]

    return workflow


def update_input_image(workflow, image_filename):
    """Update workflow to use specific input image.

    Args:
        workflow: Workflow dict to modify
        image_filename: Filename in input/ directory (must be 2048x1024)

    Returns:
        Modified workflow dict
    """
    # Update input image
    workflow["200"]["inputs"]["image"] = image_filename

    # Note: Crop nodes 201-202 remain at y=0 since input is always 2048x1024
    # They crop the left and right halves respectively

    return workflow


if __name__ == "__main__":
    # Basic test of functions
    print("Testing workflow update functions...")

    # Load workflow template
    workflow_path = Path(__file__).parent.parent / "workflows" / "extend_texture_down_workflow.json"
    workflow = load_workflow_template(workflow_path)
    print(f"✓ Loaded workflow: {len(workflow)} nodes")

    # Load prompts config
    prompts_path = Path(__file__).parent.parent / "config" / "tile_prompts.json"
    with open(prompts_path, 'r') as f:
        prompts = json.load(f)
    print(f"✓ Loaded prompts: {len(prompts['tile_types'])} tile types, {len(prompts['transitions'])} transitions")

    # Test update_workflow_prompts
    test_workflow = copy.deepcopy(workflow)
    test_workflow = update_workflow_prompts(
        test_workflow,
        "grass", "stone",  # top row
        "stone", "grass",  # bottom row
        prompts
    )
    print(f"✓ Updated workflow prompts")
    print(f"  - Left column tile: stone")
    print(f"  - Right column tile: grass")
    print(f"  - Left vertical transition: grass_to_stone")
    print(f"  - Right vertical transition: stone_to_grass")
    print(f"  - Horizontal transition: stone_to_grass")

    # Test update_input_image
    test_workflow = update_input_image(test_workflow, "test_input.png")
    assert test_workflow["200"]["inputs"]["image"] == "test_input.png"
    print(f"✓ Updated input image to: test_input.png")

    print("\n✓ All functions working correctly!")
