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


def submit_workflow_to_runpod(workflow, input_image_path, timeout=1800):
    """Submit workflow to RunPod and wait for completion.

    Args:
        workflow: Updated workflow dict
        input_image_path: Path to input 1x2 image file (2048x1024)
        timeout: Timeout in seconds (default: 1800 = 30 minutes for first run with model loading)

    Returns:
        Path to downloaded 2x2 output image (2048x2048)

    Raises:
        RuntimeError: If workflow submission fails or no output found
    """
    # Save workflow to temp file
    workflow_path = Path("temp_extend_texture_workflow.json")
    with open(workflow_path, 'w') as f:
        json.dump(workflow, f, indent=2)

    # Call send-to-runpod.py
    cmd = [
        'python3',
        'scripts/send-to-runpod.py',
        '--workflow', str(workflow_path),
        '--images', str(input_image_path),
        '--no-open',
        '--timeout', str(timeout)
    ]

    # Run and wait for completion
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Workflow submission failed: {result.stderr}")

    # Find most recent output image
    # send-to-runpod.py downloads to output/ directory
    output_files = sorted(
        Path("output").glob("phase3_bottom_center_blended_*.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    if not output_files:
        raise RuntimeError("No output image found after workflow execution")

    return output_files[0]


def extract_bottom_1x2(image_2x2_path):
    """Extract bottom 1x2 row from 2x2 workflow output.

    Args:
        image_2x2_path: Path to 2048x2048 image

    Returns:
        PIL Image of bottom 1024 pixels (2048x1024)

    Raises:
        ValueError: If image dimensions are incorrect
    """
    from PIL import Image

    img = Image.open(image_2x2_path)

    # Verify dimensions
    if img.size != (2048, 2048):
        raise ValueError(f"Expected 2048x2048, got {img.size}")

    # Crop bottom 1024 pixels
    bottom_1x2 = img.crop((0, 1024, 2048, 2048))

    return bottom_1x2


def composite_accumulated_grid(previous_grid_path, new_row_image):
    """Composite new row onto accumulated grid.

    NOTE: Do not call this for the first iteration (iteration 0).
    For iteration 0, use the full 2x2 workflow output directly as the accumulated grid.

    Args:
        previous_grid_path: Path to previous accumulated grid (must not be None)
        new_row_image: PIL Image of new 1x2 row (2048x1024)

    Returns:
        PIL Image of new accumulated grid
    """
    from PIL import Image

    # Load previous grid
    previous_grid = Image.open(previous_grid_path)

    # Create new canvas
    prev_height = previous_grid.size[1]
    new_height = prev_height + 1024

    accumulated = Image.new('RGB', (2048, new_height))

    # Paste previous grid at top
    accumulated.paste(previous_grid, (0, 0))

    # Paste new row at bottom
    accumulated.paste(new_row_image, (0, prev_height))

    return accumulated


def save_iteration_outputs(iteration_num, workflow_output_2x2, accumulated_grid, next_input_1x2, output_dir):
    """Save all three output images for an iteration.

    Args:
        iteration_num: Iteration number (0-indexed)
        workflow_output_2x2: PIL Image (2048x2048)
        accumulated_grid: PIL Image (2048 x N*1024)
        next_input_1x2: PIL Image (2048x1024)
        output_dir: Base output directory

    Returns:
        dict with paths to all saved images
    """
    # Create iteration directory
    iter_dir = output_dir / f"iteration_{iteration_num}"
    iter_dir.mkdir(parents=True, exist_ok=True)

    # Save three outputs
    paths = {
        'workflow_2x2': iter_dir / "workflow_output_2x2.png",
        'accumulated': iter_dir / "accumulated_grid.png",
        'next_input': iter_dir / "next_input_1x2.png"
    }

    workflow_output_2x2.save(paths['workflow_2x2'])
    accumulated_grid.save(paths['accumulated'])
    next_input_1x2.save(paths['next_input'])

    print(f"  Saved to {iter_dir}/")
    print(f"    - workflow_output_2x2.png (2048x2048)")
    print(f"    - accumulated_grid.png ({accumulated_grid.size[0]}x{accumulated_grid.size[1]})")
    print(f"    - next_input_1x2.png (2048x1024)")

    return paths


def generate_texture_grid(
    grid_spec,
    initial_image_path,
    workflow_template,
    prompts_config,
    output_base_dir,
    timeout=1800
):
    """Main generator loop: iteratively extend texture downward to build Nx2 grid.

    Args:
        grid_spec: List of [left_type, right_type] pairs, e.g. [["grass", "stone"], ["stone", "grass"]]
        initial_image_path: Path to initial 2048x1024 image (row 0)
        workflow_template: Loaded workflow dict
        prompts_config: Loaded prompts config
        output_base_dir: Base directory for outputs
        timeout: RunPod timeout in seconds (default: 1800)

    Returns:
        Path to final accumulated grid
    """
    # Create timestamped output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(output_base_dir) / f"grid_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🎨 Starting grid generation: {len(grid_spec)} rows x 2 columns")
    print(f"📁 Output directory: {output_dir}")
    print(f"🖼️  Initial image: {initial_image_path}\n")

    # Copy initial image to input/ directory for ComfyUI
    input_dir = Path("input")
    input_dir.mkdir(exist_ok=True)
    input_filename = f"grid_input_{timestamp}.png"
    input_path = input_dir / input_filename
    shutil.copy(initial_image_path, input_path)

    # Track state across iterations
    accumulated_grid_path = None
    current_input_path = input_path

    # Iterate through grid rows
    for iteration_num in range(len(grid_spec) - 1):
        row_idx = iteration_num + 1  # We're generating row 1, 2, 3, etc.
        print(f"📐 Iteration {iteration_num}: Generating row {row_idx}")

        # Get tile types for current iteration
        top_left, top_right = grid_spec[iteration_num]
        bottom_left, bottom_right = grid_spec[row_idx]

        print(f"  Top row: [{top_left}, {top_right}]")
        print(f"  Bottom row: [{bottom_left}, {bottom_right}]")

        # Update workflow with prompts for this iteration
        workflow = copy.deepcopy(workflow_template)
        workflow = update_workflow_prompts(
            workflow,
            top_left, top_right,
            bottom_left, bottom_right,
            prompts_config
        )

        # Update workflow with current input image
        workflow = update_input_image(workflow, current_input_path.name)

        # Submit to RunPod
        print(f"  ⏳ Submitting to RunPod (timeout: {timeout}s)...")
        workflow_output_2x2_path = submit_workflow_to_runpod(workflow, current_input_path, timeout)
        print(f"  ✓ Workflow complete: {workflow_output_2x2_path}")

        # Load the 2x2 output
        workflow_output_2x2_img = Image.open(workflow_output_2x2_path)

        # Extract bottom 1x2 for next iteration
        bottom_1x2_img = extract_bottom_1x2(workflow_output_2x2_path)

        # Build accumulated grid
        if accumulated_grid_path is None:
            # First iteration: use full 2x2 workflow output
            accumulated_grid_img = workflow_output_2x2_img
        else:
            # Subsequent iterations: composite new row onto previous grid
            accumulated_grid_img = composite_accumulated_grid(accumulated_grid_path, bottom_1x2_img)

        # Save iteration outputs
        paths = save_iteration_outputs(
            iteration_num,
            workflow_output_2x2_img,
            accumulated_grid_img,
            bottom_1x2_img,
            output_dir
        )

        # Update state for next iteration
        accumulated_grid_path = paths['accumulated']

        # Save next input to input/ directory for ComfyUI
        next_input_filename = f"grid_input_{timestamp}_iter{iteration_num + 1}.png"
        current_input_path = input_dir / next_input_filename
        bottom_1x2_img.save(current_input_path)

        print(f"  ✓ Iteration {iteration_num} complete\n")

    # Copy final accumulated grid to output directory root
    final_output = output_dir / "final_grid.png"
    shutil.copy(accumulated_grid_path, final_output)

    print(f"✅ Grid generation complete!")
    print(f"📊 Final grid: {accumulated_grid_img.size[0]}x{accumulated_grid_img.size[1]}")
    print(f"🎯 Final output: {final_output}")

    return final_output


def generate_from_grid_config(config_path, workflow_template, prompts_config, output_base_dir, timeout=1800):
    """Generate texture grid from JSON config file.

    Args:
        config_path: Path to grid config JSON
        workflow_template: Loaded workflow dict
        prompts_config: Loaded prompts config
        output_base_dir: Base directory for outputs
        timeout: RunPod timeout in seconds (default: 1800)

    Returns:
        Path to final accumulated grid
    """
    # Load grid config
    with open(config_path, 'r') as f:
        config = json.load(f)

    print(f"📋 Loaded config: {config.get('name', 'Unnamed')}")
    if 'description' in config:
        print(f"   {config['description']}")

    # Validate grid spec
    grid = config['grid']
    if not grid or not all(len(row) == 2 for row in grid):
        raise ValueError("Grid must be list of [left, right] pairs")

    # Resolve initial image path
    initial_image = config['initial_image']
    if not Path(initial_image).exists():
        # Try relative to config file
        config_dir = Path(config_path).parent
        initial_image = config_dir.parent / initial_image
        if not initial_image.exists():
            raise FileNotFoundError(f"Initial image not found: {config['initial_image']}")

    # Generate grid
    return generate_texture_grid(
        grid,
        initial_image,
        workflow_template,
        prompts_config,
        output_base_dir,
        timeout
    )


def parse_tile_pattern(pattern_str):
    """Parse CLI tile pattern string into grid spec.

    Args:
        pattern_str: Comma-separated pattern like "grass,stone,stone,grass"

    Returns:
        List of [left, right] pairs

    Examples:
        "grass,stone,stone,grass" → [["grass", "stone"], ["stone", "grass"]]
    """
    tiles = [t.strip() for t in pattern_str.split(',')]

    if len(tiles) % 2 != 0:
        raise ValueError(f"Pattern must have even number of tiles, got {len(tiles)}")

    # Group into pairs
    grid = []
    for i in range(0, len(tiles), 2):
        grid.append([tiles[i], tiles[i + 1]])

    return grid


def main():
    """Main entry point with dual-mode CLI."""
    parser = argparse.ArgumentParser(
        description="Generate Nx2 texture grids by iteratively extending textures downward",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate from config file
  python extend_texture_down.py --config config/example_map_simple.json

  # Generate from CLI pattern
  python extend_texture_down.py \\
    --pattern "grass,stone,stone,grass,grass,stone" \\
    --initial-image input/grass_stone_initial.png

  # Custom output directory
  python extend_texture_down.py \\
    --config config/example_map_complex.json \\
    --output output/my_maps
        """
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '--config',
        type=str,
        help='Path to grid config JSON file'
    )
    mode_group.add_argument(
        '--pattern',
        type=str,
        help='Comma-separated tile pattern (e.g., "grass,stone,stone,grass")'
    )

    # Required for pattern mode
    parser.add_argument(
        '--initial-image',
        type=str,
        help='Path to initial 2048x1024 image (required for --pattern mode)'
    )

    # Optional arguments
    parser.add_argument(
        '--output',
        type=str,
        default='output',
        help='Output directory (default: output/)'
    )
    parser.add_argument(
        '--workflow',
        type=str,
        default=None,
        help='Path to workflow JSON (default: workflows/extend_texture_down_workflow.json)'
    )
    parser.add_argument(
        '--prompts',
        type=str,
        default=None,
        help='Path to prompts config JSON (default: config/tile_prompts.json)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=1800,
        help='RunPod timeout in seconds (default: 1800 = 30 min for first run with model loading)'
    )

    args = parser.parse_args()

    # Validate pattern mode requirements
    if args.pattern and not args.initial_image:
        parser.error("--pattern mode requires --initial-image")

    # Resolve paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    workflow_path = Path(args.workflow) if args.workflow else project_root / "workflows" / "extend_texture_down_workflow.json"
    prompts_path = Path(args.prompts) if args.prompts else project_root / "config" / "tile_prompts.json"

    # Load workflow and prompts
    print("📂 Loading configuration...")
    workflow_template = load_workflow_template(workflow_path)
    print(f"  ✓ Workflow: {workflow_path.name} ({len(workflow_template)} nodes)")

    with open(prompts_path, 'r') as f:
        prompts_config = json.load(f)
    print(f"  ✓ Prompts: {len(prompts_config['tile_types'])} tile types, {len(prompts_config['transitions'])} transitions")

    # Execute in appropriate mode
    try:
        if args.config:
            # Config file mode
            final_output = generate_from_grid_config(
                args.config,
                workflow_template,
                prompts_config,
                args.output,
                args.timeout
            )
        else:
            # Pattern mode
            grid_spec = parse_tile_pattern(args.pattern)
            final_output = generate_texture_grid(
                grid_spec,
                args.initial_image,
                workflow_template,
                prompts_config,
                args.output,
                args.timeout
            )

        print(f"\n🎉 Success! Final grid saved to: {final_output}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # If run with arguments, execute main()
    if len(sys.argv) > 1:
        main()
    else:
        # Basic test of functions (backward compatibility)
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
        print("\nRun with --help to see usage for grid generation.")
