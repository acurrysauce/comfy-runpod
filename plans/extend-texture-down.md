# Extend Texture Down Generator Plan

> **Note:** Branch is currently named `feature/parameterized-checkerboard-generator` but should be renamed to `feature/extend-texture-down` to match updated terminology.

## Overview

Create a Python script that parameterizes the `checkerboard_phase3_bottom_blend_api.json` workflow to generate [nx2] tile grids of any height. The workflow currently creates a 2x2 grid from a 1x2 input by extending downward. This script will run the workflow iteratively, using each iteration's output as the next iteration's input, building progressively taller grids.

**Goals:**
- Generate tile grids of arbitrary height (n rows x 2 columns)
- Parameterize tile types and their prompts (any combination of types)
- Support 3 different transition prompts (left vertical, right vertical, horizontal)
- Store all prompts and models in a JSON configuration file
- **Store complete grid layouts in a grid configuration JSON**
- **Support both grid config file mode and CLI pattern mode**
- Create a reusable script for generating texture maps

**Use Case Examples:**

1. **Alternating pattern:**
```
[[grass,  stone],   ← input (existing image)
 [stone,  grass],   ← iteration 1 output
 [grass,  stone],   ← iteration 2 output
 [stone,  grass]]   ← iteration 3 output
```

2. **Uniform tiles:**
```
[[grass,  grass],
 [grass,  grass],
 [grass,  grass]]
```

3. **Complex patterns:**
```
[[dirt,   stone],
 [grass,  sand],
 [mud,    gravel]]
```

## Architecture

### Data Flow
```
Grid Config (my_map.json) ──┐
                              ├→ Orchestration Function
Tile Prompts (tile_prompts.json) ─┘
    ↓
Python Script (extend_texture_down.py)
    ↓
Workflow Copy (extend_texture_down_workflow.json)
    ↓
[Loop for n-1 iterations]
    ├→ Update workflow with 4 tile types + 3 transitions
    ├→ Update input image filename
    ├→ Submit to RunPod via send-to-runpod.py
    ├→ Wait for completion and download 2x2 output
    ├→ Extract bottom 1x2 row from 2x2 output
    ├→ Composite onto accumulated grid (Python)
    ├→ Save 3 outputs: accumulated grid, 2x2 debug, next 1x2 input
    └→ Use extracted 1x2 as next iteration's input
    ↓
Final [nx2] Grid
```

### Directory Structure
```
/home/acurry/comfy-runpod/
└── map-generator/
    ├── config/
    │   ├── tile_prompts.json          (tile definitions & transitions)
    │   ├── example_map_simple.json    (grid config example)
    │   ├── example_map_complex.json   (grid config example)
    │   └── my_custom_map.json         (user grid configs)
    ├── scripts/
    │   └── extend_texture_down.py
    ├── workflows/
    │   └── extend_texture_down_workflow.json  (modified copy)
    └── outputs/
        └── my_map_20250124_143022/    (timestamped run directory)
            ├── iteration_0/
            │   ├── accumulated_grid.png
            │   ├── workflow_output_2x2.png
            │   └── next_input_1x2.png
            ├── iteration_1/
            │   └── ... (same structure)
            ├── final_grid.png         (symlink)
            └── generation_progress.json
```

### Key Concept: Four Tile Grid
Each iteration creates a 2x2 grid where all 4 tiles can be different types:
```
[top_left,    top_right]     ← Top row (from input)
[bottom_left, bottom_right]  ← Bottom row (generated)
```

**Three Transitions:**
1. **Left vertical:** top_left → bottom_left
2. **Right vertical:** top_right → bottom_right
3. **Horizontal seam:** bottom_left ↔ bottom_right

## Phases

### Phase 0: Modify Workflow Copy (Split Transition Prompts)

**Files to create:**
- `map-generator/workflows/extend_texture_down_workflow.json` - Modified workflow copy

**Current Issue:**
The workflow uses the same prompt node (101/102) for all 3 transitions. We need 3 separate prompt nodes.

**Implementation:**

1. **Copy original workflow:**
```bash
cp workflows/checkerboard_phase3_bottom_blend_api.json \
   map-generator/workflows/extend_texture_down_workflow.json
```

2. **Create new prompt nodes for vertical transitions:**

**Add nodes 103/104 for left vertical transition:**
```json
"103": {
  "inputs": {
    "text": "natural transition between grass and stone, grass growing between stone cracks, moss on stones, weathered stone edges with grass, organic boundary, small grass tufts emerging from stone gaps, stone fragments scattered in grass, seamless blend, hand painted game texture",
    "clip": ["401", 1]
  },
  "class_type": "CLIPTextEncode",
  "_meta": {
    "title": "Prompt - Left Vertical Transition"
  }
},
"104": {
  "inputs": {
    "text": "blurry, low quality, hard edge, sharp boundary, visible seam, cut line, abrupt change",
    "clip": ["401", 1]
  },
  "class_type": "CLIPTextEncode",
  "_meta": {
    "title": "Negative - Left Vertical Transition"
  }
}
```

**Add nodes 105/106 for right vertical transition:**
```json
"105": {
  "inputs": {
    "text": "natural transition between stone and grass, grass growing between stone cracks, moss on stones, weathered stone edges with grass, organic boundary, small grass tufts emerging from stone gaps, stone fragments scattered in grass, seamless blend, hand painted game texture",
    "clip": ["3", 1]
  },
  "class_type": "CLIPTextEncode",
  "_meta": {
    "title": "Prompt - Right Vertical Transition"
  }
},
"106": {
  "inputs": {
    "text": "blurry, low quality, hard edge, sharp boundary, visible seam, cut line, abrupt change",
    "clip": ["3", 1]
  },
  "class_type": "CLIPTextEncode",
  "_meta": {
    "title": "Negative - Right Vertical Transition"
  }
}
```

**Important wiring:**
- Nodes 103/104 (left column): Connect to node 401 CLIP output (left column inpaint LoRA loader)
- Nodes 105/106 (right column): Connect to node 3 CLIP output (right column base LoRA loader)
- This ensures each transition uses the correct LoRA's CLIP encoder

3. **Update KSampler nodes to use new prompts:**
- Node 229a (left vertical blend): Change positive from `["101", 0]` to `["103", 0]`, negative from `["102", 0]` to `["104", 0]`
- Node 239a (right vertical blend): Change positive from `["101", 0]` to `["105", 0]`, negative from `["102", 0]` to `["106", 0]`
- Node 304 (horizontal blend): Keep using `["101", 0]` and `["102", 0]`

4. **Update titles for clarity:**
- Node 101: "Prompt - Horizontal Transition"
- Node 102: "Negative - Horizontal Transition"

**Testing:**
- Load modified workflow in Python
- Verify all nodes have valid connections
- Test workflow submission (should produce identical output to original)

### Phase 1: Extract Prompts and Create JSON Configs

**Prerequisites:** Phase 0 must be complete (modified workflow with nodes 103-106 created)

**Files to create:**
- `map-generator/config/tile_prompts.json` - All prompts and models
- `map-generator/config/example_map_simple.json` - Example grid config
- `map-generator/config/example_map_complex.json` - Complex grid config example

**Implementation:**

1. **Extract prompts from the MODIFIED workflow nodes:**
   - Node 10/5: Grass tile prompts (from original)
   - Node 50/51: Stone tile prompts (from original)
   - Node 103/104: Left vertical transition (grass→stone) - **NEW in Phase 0**
   - Node 105/106: Right vertical transition (stone→grass) - **NEW in Phase 0**
   - Node 101/102: Horizontal transition (stone↔grass) - **REPURPOSED in Phase 0**

2. **Design JSON structure:**
```json
{
  "tile_types": {
    "grass": {
      "positive": "hand painted grass texture, stylized grass patch, painted grass clumps, green grass tufts, varied grass colors, light and dark green grass, painterly grass texture, game texture, top-down flat view, seamless, textured grass surface",
      "negative": "blurry, low quality, photorealistic, 3d render, realistic grass blades, detailed grass strands, individual blades, modern brick wall",
      "lora": "Hand-Painted_2d_Seamless_Textures-000007.safetensors",
      "lora_strength_model": 0.6,
      "lora_strength_clip": 0.6
    },
    "stone": {
      "positive": "hand painted stone floor texture, light grey medieval stone blocks, pale grey cobblestone pavement, square cut stone tiles, clean light stone, castle courtyard floor, fantasy game texture, top-down flat view, light grey and pale beige stones, simple painted blocks, artisan stonework, seamless",
      "negative": "blurry, low quality, photorealistic, modern brick wall, grout lines, uniform tiles, polished surface, shiny, pristine, grass, plants, dirt, mud, green, dark grey, dark brown, black rocks",
      "lora": "Hand-Painted_2d_Seamless_Textures-000007.safetensors",
      "lora_strength_model": 0.6,
      "lora_strength_clip": 0.6
    }
  },
  "transitions": {
    "grass_to_stone": {
      "positive": "natural transition between grass and stone, grass growing between stone cracks, moss on stones, weathered stone edges with grass, organic boundary, small grass tufts emerging from stone gaps, stone fragments scattered in grass, seamless blend, hand painted game texture",
      "negative": "blurry, low quality, hard edge, sharp boundary, visible seam, cut line, abrupt change"
    },
    "stone_to_grass": {
      "positive": "natural transition between stone and grass, grass growing between stone cracks, moss on stones, weathered stone edges with grass, organic boundary, small grass tufts emerging from stone gaps, stone fragments scattered in grass, seamless blend, hand painted game texture",
      "negative": "blurry, low quality, hard edge, sharp boundary, visible seam, cut line, abrupt change"
    },
    "grass_to_grass": {
      "positive": "seamless grass texture continuation, uniform grass pattern, consistent grass coverage, smooth grass blend, hand painted game texture",
      "negative": "blurry, low quality, hard edge, sharp boundary, visible seam, cut line, abrupt change"
    },
    "stone_to_stone": {
      "positive": "seamless stone texture continuation, uniform stone pattern, consistent stone coverage, smooth stone blend, hand painted game texture",
      "negative": "blurry, low quality, hard edge, sharp boundary, visible seam, cut line, abrupt change"
    }
  },
  "global": {
    "base_checkpoint": "sd_xl_base_1.0.safetensors",
    "inpaint_checkpoint": "sd_xl_base_1.0_inpainting_0.1.safetensors",
    "vae": "sdxl_vae.safetensors"
  }
}
```

**Note:** Same-to-same transitions (grass_to_grass, stone_to_stone) use simplified prompts since there's no material change.

3. **Design grid configuration JSON structure:**

**Simple example (`example_map_simple.json`):**
```json
{
  "name": "Simple Alternating Grass-Stone Map",
  "description": "4x2 grid alternating between grass and stone",
  "initial_image": "input/grass_stone_initial.png",
  "grid": [
    ["grass", "stone"],
    ["stone", "grass"],
    ["grass", "stone"],
    ["stone", "grass"]
  ]
}
```

**Complex example (`example_map_complex.json`):**
```json
{
  "name": "Multi-Terrain Map",
  "description": "Large varied terrain with multiple tile types",
  "initial_image": "input/dirt_sand_initial.png",
  "grid": [
    ["dirt", "sand"],
    ["grass", "stone"],
    ["stone", "stone"],
    ["grass", "grass"],
    ["dirt", "grass"],
    ["stone", "sand"],
    ["sand", "dirt"]
  ],
  "metadata": {
    "created": "2025-01-24",
    "author": "user",
    "tile_size_px": 1024,
    "total_dimensions": "2048x7168"
  }
}
```

**Grid Config Specification:**
- `name` (string, required): Human-readable name for this map
- `description` (string, optional): Description of the map
- `initial_image` (string, required): Path to initial 1x2 image (relative to project root)
- `grid` (array, required): Array of [left, right] tile type pairs, one per row
  - First row: Describes the initial image content (for validation)
  - Subsequent rows: What to generate
- `metadata` (object, optional): Additional metadata

**Testing:**
- Validate JSON syntax
- Verify all prompts match workflow exactly
- Test loading JSON in Python
- Verify all required transition combinations exist
- Validate grid config structure
- Test that grid tiles reference existing tile types

### Phase 2: Create Workflow Update Functions

**Files to create:**
- `map-generator/scripts/extend_texture_down.py` - Main generator script

**Required imports:**
```python
import json
import copy
import shutil
import subprocess
import sys
import argparse
from pathlib import Path
from datetime import datetime
from PIL import Image
```

**Implementation:**

1. **Create function to load and parse workflow:**
```python
def load_workflow_template(template_path):
    """Load the workflow template JSON."""
    with open(template_path, 'r') as f:
        return json.load(f)
```

2. **Create function to update workflow prompts:**
```python
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
```

3. **Create function to update input image:**
```python
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
```

**Technical Details:**

**Node Mapping (from modified workflow):**
- Node 200: Load input image (always 2048x1024)
- Node 201/202: Crop left and right tiles from input (y=0, never changes)
- Node 10/5: Bottom-right tile prompts
- Node 50/51: Bottom-left tile prompts
- Node 103/104: Left vertical transition prompts (NEW)
- Node 105/106: Right vertical transition prompts (NEW)
- Node 101/102: Horizontal transition prompts (MODIFIED purpose)
- Node 3: Right column LoRA
- Node 401: Left column LoRA (inpaint)
- Node 307: Final output SaveImage (always 2048x2048)

**Why 4 tile types needed:**
- Bottom tiles determine what to generate (obvious)
- Top tiles determine transitions (vertical seam blending)
- All 3 transitions can use different prompts

**Testing:**
- Load workflow template successfully
- Update with all 4 tile types
- Verify all 3 transitions use correct prompts
- Verify LoRA settings updated for both columns
- Test with same tile types (grass/grass/grass/grass)
- Test with mixed types (grass/stone/stone/grass)

### Phase 3: Implement RunPod Submission and Image Processing

**Implementation:**

1. **Create function to submit workflow to RunPod:**
```python
def submit_workflow_to_runpod(workflow, input_image_path):
    """Submit workflow to RunPod and wait for completion.

    Args:
        workflow: Updated workflow dict
        input_image_path: Path to input 1x2 image file (2048x1024)

    Returns:
        Path to downloaded 2x2 output image (2048x2048)
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
        '--no-open'
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
```

2. **Create function to extract bottom 1x2 row:**
```python
def extract_bottom_1x2(image_2x2_path):
    """Extract bottom 1x2 row from 2x2 workflow output.

    Args:
        image_2x2_path: Path to 2048x2048 image

    Returns:
        PIL Image of bottom 1024 pixels (2048x1024)
    """
    from PIL import Image

    img = Image.open(image_2x2_path)

    # Verify dimensions
    if img.size != (2048, 2048):
        raise ValueError(f"Expected 2048x2048, got {img.size}")

    # Crop bottom 1024 pixels
    bottom_1x2 = img.crop((0, 1024, 2048, 2048))

    return bottom_1x2
```

3. **Create function to composite accumulated grid:**
```python
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
```

4. **Create function to save three outputs:**
```python
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
```

**Testing:**
- Submit a single workflow with 1x2 input
- Verify 2x2 output downloaded correctly
- Test extracting bottom 1x2 from 2x2 output
- Test compositing accumulated grid
- Verify all three images saved to correct locations

### Phase 4: Implement Main Generator Loop

**Implementation:**

1. **Create grid config orchestration function:**
```python
def generate_from_grid_config(
    grid_config_path,
    prompts_config_path,
    workflow_template_path,
    output_dir
):
    """Generate texture grid from a grid configuration file.

    This is the high-level orchestration function that reads a complete
    grid specification and calls the lower-level iteration function.

    Args:
        grid_config_path: Path to grid config JSON (e.g., my_map.json)
        prompts_config_path: Path to tile prompts JSON
        workflow_template_path: Path to workflow template
        output_dir: Directory for outputs

    Returns:
        Path to final output image
    """
    # Load grid configuration
    with open(grid_config_path, 'r') as f:
        grid_config = json.load(f)

    # Extract parameters
    grid = grid_config["grid"]
    num_rows = len(grid)
    initial_image = Path(grid_config["initial_image"])

    # Convert grid to tile pattern format
    tile_pattern = [(row[0], row[1]) for row in grid]

    # Validate initial image exists
    if not initial_image.exists():
        raise FileNotFoundError(f"Initial image not found: {initial_image}")

    # Log grid info
    print(f"=== Grid Configuration: {grid_config.get('name', 'Unnamed')} ===")
    if 'description' in grid_config:
        print(f"Description: {grid_config['description']}")
    print(f"Total rows: {num_rows}")
    print(f"Grid layout:")
    for i, (left, right) in enumerate(tile_pattern):
        marker = "→" if i == 0 else " "
        print(f"  {marker} Row {i}: [{left:10s}, {right:10s}]")
    print()

    # Call the main generator
    return generate_texture_grid(
        num_rows=num_rows,
        initial_image=initial_image,
        tile_pattern=tile_pattern,
        prompts_config_path=prompts_config_path,
        workflow_template_path=workflow_template_path,
        output_dir=output_dir
    )
```

2. **Create main generator function:**
```python
def generate_texture_grid(
    num_rows,
    initial_image,
    tile_pattern,
    prompts_config_path,
    workflow_template_path,
    base_output_dir
):
    """Generate n x 2 tile grid by iteratively extending downward.

    Args:
        num_rows: Total rows in output (including initial row)
        initial_image: Path to starting 1x2 image (2048x1024)
        tile_pattern: List of tuples [(left_type, right_type), ...] for each row
                      e.g., [("grass", "stone"), ("stone", "grass"), ("grass", "stone")]
        prompts_config_path: Path to prompts JSON
        workflow_template_path: Path to workflow template
        base_output_dir: Base output directory (will create timestamped subdirectory)

    Returns:
        Path to final accumulated grid
    """
    from PIL import Image
    from datetime import datetime

    # Load configuration
    with open(prompts_config_path, 'r') as f:
        prompts = json.load(f)

    workflow_template = load_workflow_template(workflow_template_path)

    # Validate pattern length
    if len(tile_pattern) != num_rows:
        raise ValueError(f"Pattern length ({len(tile_pattern)}) must match num_rows ({num_rows})")

    # Validate initial image dimensions
    initial_img = Image.open(initial_image)
    if initial_img.size != (2048, 1024):
        raise ValueError(f"Initial image must be 2048x1024, got {initial_img.size}")

    # Create timestamped run directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    grid_name = base_output_dir.name if hasattr(base_output_dir, 'name') else 'grid'
    run_dir = base_output_dir / f"{grid_name}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\\n=== Starting Grid Generation ===")
    print(f"Output directory: {run_dir}")
    print(f"Total rows to generate: {num_rows} (initial + {num_rows - 1} iterations)")

    # Copy initial image to input directory for workflow access
    input_dir = Path("input")
    current_input_1x2_path = input_dir / f"iter_0_input.png"
    shutil.copy(initial_image, current_input_1x2_path)

    # Track accumulated grid path (None for first iteration)
    accumulated_grid_path = None

    # Generate n-1 additional rows (initial image is row 0)
    for iteration in range(num_rows - 1):
        print(f"\\n=== Iteration {iteration}/{num_rows - 1} ===")

        # Get tile types for current and next row
        current_row_index = iteration
        next_row_index = iteration + 1

        top_left, top_right = tile_pattern[current_row_index]
        bottom_left, bottom_right = tile_pattern[next_row_index]

        print(f"  Input row {current_row_index}: [{top_left:10s}, {top_right:10s}]")
        print(f"  Generating row {next_row_index}: [{bottom_left:10s}, {bottom_right:10s}]")

        # Update workflow with all 4 tile types
        workflow = copy.deepcopy(workflow_template)
        workflow = update_input_image(workflow, current_input_1x2_path.name)
        workflow = update_workflow_prompts(
            workflow,
            top_left, top_right,
            bottom_left, bottom_right,
            prompts
        )

        # Submit to RunPod and wait for 2x2 output
        print("  Submitting to RunPod...")
        workflow_output_2x2_path = submit_workflow_to_runpod(workflow, current_input_1x2_path)
        print(f"  Workflow complete: {workflow_output_2x2_path.name}")

        # Extract bottom 1x2 row from 2x2 output
        workflow_output_2x2_img = Image.open(workflow_output_2x2_path)
        bottom_1x2_img = extract_bottom_1x2(workflow_output_2x2_path)

        # Composite accumulated grid
        if accumulated_grid_path is None:
            # First iteration: use full 2x2 workflow output as accumulated grid
            accumulated_grid_img = workflow_output_2x2_img
        else:
            # Subsequent iterations: composite new row onto previous grid
            accumulated_grid_img = composite_accumulated_grid(accumulated_grid_path, bottom_1x2_img)

        # Save all three outputs
        saved_paths = save_iteration_outputs(
            iteration_num=iteration,
            workflow_output_2x2=workflow_output_2x2_img,
            accumulated_grid=accumulated_grid_img,
            next_input_1x2=bottom_1x2_img,
            output_dir=run_dir
        )

        # Update tracking variables for next iteration
        accumulated_grid_path = saved_paths['accumulated']
        current_input_1x2_path = saved_paths['next_input']

        print(f"  Accumulated grid: {accumulated_grid_img.size[0]}x{accumulated_grid_img.size[1]}")

    # Create symlink to final grid
    final_grid_link = run_dir / "final_grid.png"
    if final_grid_link.exists():
        final_grid_link.unlink()
    final_grid_link.symlink_to(accumulated_grid_path.relative_to(run_dir))

    print(f"\\n=== Generation Complete ===")
    print(f"Generated {num_rows}x2 grid ({2048}x{num_rows * 1024})")
    print(f"Final output: {accumulated_grid_path}")
    print(f"Quick access: {final_grid_link}")

    return accumulated_grid_path
```

3. **Create CLI interface with dual modes:**
```python
def parse_tile_pattern(pattern_str):
    """Parse tile pattern from string.

    Examples:
        "grass,stone" -> [("grass", "stone")] (single row)
        "grass,stone;stone,grass" -> [("grass", "stone"), ("stone", "grass")]
        "grass,stone;*3" -> [("grass", "stone"), ("stone", "grass"), ("grass", "stone")]
                            (alternates automatically)

    Args:
        pattern_str: Pattern string with rows separated by ';'

    Returns:
        List of (left_type, right_type) tuples
    """
    if ';' not in pattern_str:
        # Single row pattern - generate alternating
        left, right = pattern_str.split(',')
        return lambda n: [(left, right) if i % 2 == 0 else (right, left) for i in range(n)]

    # Explicit pattern
    rows = pattern_str.split(';')
    pattern = []
    for row in rows:
        left, right = row.strip().split(',')
        pattern.append((left.strip(), right.strip()))
    return pattern

def main():
    parser = argparse.ArgumentParser(
        description="Generate nx2 tile grids by extending textures downward",
        epilog="""
Examples:
  # Grid config mode (recommended for complex layouts):
  %(prog)s --grid-config config/my_map.json

  # CLI pattern mode (quick testing):
  %(prog)s --rows 5 --input input/start.png --pattern "grass,stone"
        """
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '--grid-config', '-g',
        type=Path,
        help='Path to grid configuration JSON (contains grid, initial image, etc.)'
    )
    mode_group.add_argument(
        '--pattern', '-p',
        type=str,
        help='Tile pattern for CLI mode: "left,right" for alternating or "left,right;left,right;..." for explicit'
    )

    # CLI pattern mode arguments (only used when --pattern is specified)
    parser.add_argument(
        '--rows', '-n',
        type=int,
        help='Number of rows in output grid (required with --pattern)'
    )
    parser.add_argument(
        '--input', '-i',
        type=Path,
        help='Path to initial 1x2 image (required with --pattern)'
    )
    parser.add_argument(
        '--prompts',
        type=Path,
        default=Path('map-generator/config/tile_prompts.json'),
        help='Path to prompts configuration JSON'
    )
    parser.add_argument(
        '--template',
        type=Path,
        default=Path('map-generator/workflows/extend_texture_down_workflow.json'),
        help='Path to workflow template'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('map-generator/outputs'),
        help='Output directory'
    )

    args = parser.parse_args()

    # Validate mode-specific arguments
    if args.pattern and (not args.rows or not args.input):
        print("Error: --pattern mode requires --rows and --input")
        sys.exit(1)

    # Validate common configs exist
    if not args.prompts.exists():
        print(f"Error: Prompts config not found: {args.prompts}")
        sys.exit(1)

    if not args.template.exists():
        print(f"Error: Workflow template not found: {args.template}")
        sys.exit(1)

    # Execute based on mode
    try:
        if args.grid_config:
            # Grid config mode
            if not args.grid_config.exists():
                print(f"Error: Grid config not found: {args.grid_config}")
                sys.exit(1)

            print(f"=== Grid Config Mode ===")
            print(f"Loading: {args.grid_config}")
            final_output = generate_from_grid_config(
                grid_config_path=args.grid_config,
                prompts_config_path=args.prompts,
                workflow_template_path=args.template,
                output_dir=args.output_dir
            )
        else:
            # CLI pattern mode
            print(f"=== CLI Pattern Mode ===")

            # Validate input image
            if not args.input.exists():
                print(f"Error: Input image not found: {args.input}")
                sys.exit(1)

            # Parse tile pattern
            pattern = parse_tile_pattern(args.pattern)
            if callable(pattern):
                # Generate alternating pattern
                tile_pattern = pattern(args.rows)
            else:
                # Use explicit pattern
                tile_pattern = pattern
                if len(tile_pattern) != args.rows:
                    print(f"Error: Pattern has {len(tile_pattern)} rows but --rows is {args.rows}")
                    sys.exit(1)

            print(f"Tile pattern:")
            for i, (left, right) in enumerate(tile_pattern):
                print(f"  Row {i}: [{left}, {right}]")

            # Generate grid
            final_output = generate_texture_grid(
                num_rows=args.rows,
                initial_image=args.input,
                tile_pattern=tile_pattern,
                prompts_config_path=args.prompts,
                workflow_template_path=args.template,
                output_dir=args.output_dir
            )

        print(f"\\n=== Success! ===")
        print(f"Final output: {final_output}")
    except Exception as e:
        print(f"\\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
```

**Testing:**
- **Grid config mode:**
  - Test with example_map_simple.json
  - Test with example_map_complex.json
  - Verify grid is loaded correctly
  - Verify tile pattern extracted correctly
- **CLI pattern mode:**
  - Generate 2x2 grid (1 iteration)
  - Generate 3x2 grid (2 iterations)
  - Generate 5x2 grid (4 iterations)
  - Test with different tile type combinations
  - Verify pattern alternation is correct

### Phase 5: Add Error Handling and Validation

**Implementation:**

1. **Validate prompts config:**
```python
def validate_prompts_config(config, required_types):
    """Validate prompts config has all required tile types.

    Args:
        config: Loaded prompts config dict
        required_types: Set of tile types needed (e.g., {"grass", "stone"})

    Raises:
        ValueError: If config is invalid
    """
    # Check structure
    if "tile_types" not in config:
        raise ValueError("Prompts config missing 'tile_types' section")

    if "transitions" not in config:
        raise ValueError("Prompts config missing 'transitions' section")

    # Check required types exist
    for tile_type in required_types:
        if tile_type not in config["tile_types"]:
            raise ValueError(f"Tile type '{tile_type}' not found in prompts config")

        # Check required fields
        tile_config = config["tile_types"][tile_type]
        if "positive" not in tile_config or "negative" not in tile_config:
            raise ValueError(f"Tile type '{tile_type}' missing positive/negative prompts")

    # Check transitions exist
    for type_a in required_types:
        for type_b in required_types:
            if type_a == type_b:
                continue
            transition_key = f"{type_a}_{type_b}"
            if transition_key not in config["transitions"]:
                print(f"Warning: Transition '{transition_key}' not found, may use default")
```

2. **Add progress tracking:**
```python
def generate_texture_grid(...):
    # ... (beginning of function)

    # Create progress file
    progress_file = output_dir / "extend_texture_progress.json"
    progress = {
        "total_rows": num_rows,
        "completed_iterations": 0,
        "current_input": str(current_input),
        "outputs": []
    }

    def save_progress():
        with open(progress_file, 'w') as f:
            json.dump(progress, f, indent=2)

    save_progress()

    # In the loop:
    for iteration in range(num_rows - 1):
        # ... (generate row)

        progress["completed_iterations"] = iteration + 1
        progress["current_input"] = str(current_input)
        progress["outputs"].append(str(output_path))
        save_progress()
```

3. **Add resume capability:**
```python
def resume_generation(progress_file, ...):
    """Resume interrupted generation from progress file."""
    with open(progress_file, 'r') as f:
        progress = json.load(f)

    completed = progress["completed_iterations"]
    current_input = Path(progress["current_input"])

    print(f"Resuming from iteration {completed + 1}")

    # Continue from where we left off
    for iteration in range(completed, num_rows - 1):
        # ... (same loop as generate_texture_grid)
```

**Error Cases:**

| Error | Handling |
|-------|----------|
| Invalid input image | Validate exists and is 2048x1024 |
| Missing tile type | Validate at startup, clear error message |
| RunPod submission fails | Retry up to 3 times with exponential backoff |
| Timeout waiting for output | Save progress, allow resume |
| Disk space full | Check before each iteration |
| Invalid JSON config | Validate schema on load |

**Testing:**
- Test with invalid inputs (missing files, wrong dimensions)
- Test with missing tile types in config
- Simulate RunPod failure (mock)
- Test progress saving and resume
- Test with missing transition prompts

## Alternatives Considered

### Alternative 1: Modify Workflow to Loop Internally

**Approach:** Create a custom ComfyUI node that loops internally

**Pros:**
- Single workflow execution
- Faster (no network overhead between iterations)
- Simpler from Python script perspective

**Cons:**
- Requires custom ComfyUI node development
- More complex debugging
- Can't monitor intermediate results
- Harder to resume if interrupted

**Verdict:** Not chosen - external loop gives better control and visibility

### Alternative 2: Generate All Rows Independently

**Approach:** Don't use previous output as input, generate each row from scratch

**Pros:**
- Can parallelize (run all rows at once)
- No cascading errors

**Cons:**
- Loses vertical continuity between rows
- Each row wouldn't seamlessly connect
- Defeats purpose of outpainting workflow

**Verdict:** Not chosen - vertical continuity is essential

### Alternative 3: Store Prompts in Python Code

**Approach:** Hardcode prompts as Python dictionaries instead of JSON

**Pros:**
- No external file dependency
- Easier for simple cases

**Cons:**
- Less flexible (need to edit code to change prompts)
- Can't easily share prompts between projects
- Harder to manage as tile types grow

**Verdict:** Not chosen - JSON is more flexible and maintainable

### Alternative 4: Use ComfyUI API Directly

**Approach:** Call ComfyUI API instead of using send-to-runpod.py

**Pros:**
- Direct control over workflow execution
- Could monitor progress more granularly

**Cons:**
- Breaks existing send-to-runpod.py infrastructure
- Would need to reimplement auth, polling, etc.
- More code to maintain

**Verdict:** Not chosen - reuse existing infrastructure

## Path to NxN Grid Generation

This Nx2 implementation is the **first building block** for full NxN grid generation. Here's the complete strategy:

### Three Workflows Needed

**1. Extend Down (Current Workflow) - Nx2 Grids**
- Input: 1x2 row (2048x1024)
- Output: 2x2 grid (2048x2048)
- Purpose: Build vertical strips of arbitrary height
- Status: This plan

**2. Extend Right (Future Workflow) - 2xM Grids**
- Input: 2x1 column (1024x2048)
- Output: 2x2 grid (2048x2048)
- Purpose: Build horizontal strips of arbitrary width
- Implementation: Transpose of current workflow
  - Crop top/bottom instead of left/right
  - Outpaint horizontally instead of vertically
  - 3 transitions: top horiz, bottom horiz, right vertical seam
- Status: Future phase

**3. Fill Corner (Future Workflow) - 3 tiles → 4th tile**
- Input: 3 tiles in L-shape (top-left, top-right, bottom-left)
- Output: Complete 2x2 grid with filled bottom-right
- Purpose: Complete partial grids without full row/column
- Implementation: Similar but uses 3 input tiles
  - Inpaint bottom-right corner only
  - Blend 3 seams (right edge, bottom edge, corner)
- Status: Future phase

### NxN Orchestration Strategy

To generate an NxN grid (e.g., 4x4):

```
Step 1: Use "Extend Down" to create first column (Nx1)
  Input: Initial tile
  → 2x1, 3x1, 4x1, ..., Nx1

Step 2: Use "Extend Right" to create each row from column
  For each tile in column:
    Input: Single tile (1x1)
    → 2x1, 3x1, 4x1, ..., Mx1 row

Step 3: Composite all rows into NxM grid

Alternative: Use "Fill Corner" for partial grids
  If you have 3 tiles, directly fill 4th instead of full row/column
```

**Example: 4x4 Grid Generation**
```
Phase 1 (Extend Down): Build left column
[A]       [A]       [A]       [A]
          [E]       [E]       [E]
                    [I]       [I]
                              [M]

Phase 2 (Extend Right): Extend each row rightward
[A]       [A][B]    [A][B][C]    [A][B][C][D]
[E]       [E][F]    [E][F][G]    [E][F][G][H]
[I]       [I][J]    [I][J][K]    [I][J][K][L]
[M]       [M][N]    [M][N][O]    [M][N][O][P]

(Python composites all rows)
```

### Why This Approach Works

**Advantages:**
- ✓ Each workflow is simple (only handles 2x2)
- ✓ Reuses same blending/transition logic
- ✓ Python orchestration keeps workflows focused
- ✓ Can generate any NxM dimensions
- ✓ Progress is monitored at each step

**Complexity:**
- Each workflow generates 2x2 from smaller input
- Python handles all compositing and orchestration
- No complex multi-tile workflows needed

### Extensibility of Current Plan

**What transfers directly:**
- ✓ Prompt/transition config structure (tile_prompts.json)
- ✓ Grid config JSON format (can extend to 2D arrays)
- ✓ Three-output pattern (accumulated/2x2/next_input)
- ✓ Python compositing logic
- ✓ send-to-runpod.py integration

**What needs adaptation:**
- Workflow itself (transpose for horizontal)
- Transition mappings (different seams)
- Orchestration function (2D instead of 1D iteration)

**Verdict:** This Nx2 plan is an excellent foundation. The transposed workflow will be very similar, and the orchestration layer is straightforward Python logic.

## Technical Details

### Workflow Node Analysis

**Input/Output Chain:**
1. Node 200: LoadImage → loads 2048x1024 input
2. Nodes 201-202: Crop into two 1024x1024 tiles
3. Nodes 220-229c: Outpaint left column → 1024x2048
4. Nodes 230-239c: Outpaint right column → 1024x2048
5. Node 240: Stitch columns → 2048x2048
6. Nodes 300-307: Blend vertical seam → final 2048x2048
7. Node 307: SaveImage → "phase3_bottom_center_blended"

**Critical Nodes to Update:**
- Node 200 inputs.image: Input filename
- Node 10 inputs.text: Right column positive prompt
- Node 5 inputs.text: Right column negative prompt
- Node 50 inputs.text: Left column positive prompt
- Node 51 inputs.text: Left column negative prompt
- Node 101 inputs.text: Transition positive prompt
- Node 102 inputs.text: Transition negative prompt

### Image Dimensions and Iteration Strategy

**Key Insight:** The workflow ALWAYS outputs 2048x2048 (exactly 2 rows). We use Python compositing to build the accumulated grid.

**Workflow dimensions (fixed):**
- Input: 2048 x 1024 (1x2 tiles - bottom row of current grid)
- After crop: 1024 x 1024 each tile
- After outpaint: 1024 x 2048 each column (original + extended)
- After stitch: 2048 x 2048 (2x2 tiles)
- **Output: ALWAYS 2048 x 2048** (top row from input + new bottom row)

**Iteration strategy:**

**Iteration 0 (initial):**
```
Input to workflow:  [Row 0] (2048x1024)
Workflow output:    [Row 0, Row 1] (2048x2048)
Extract bottom 1x2: [Row 1] (2048x1024) → next input
Python composites:  [Row 0, Row 1] (2048x2048) → accumulated grid
```

**Iteration 1:**
```
Input to workflow:  [Row 1] (2048x1024)
Workflow output:    [Row 1, Row 2] (2048x2048)
Extract bottom 1x2: [Row 2] (2048x1024) → next input
Python composites:  [Row 0, Row 1] + [Row 2] → [Row 0, Row 1, Row 2] (2048x3072)
```

**Iteration n:**
```
Input to workflow:  [Row n] (2048x1024)
Workflow output:    [Row n, Row n+1] (2048x2048)
Extract bottom 1x2: [Row n+1] (2048x1024) → next input
Python composites:  accumulated_grid + [Row n+1] → (2048 x (n+2)*1024)
```

**Three outputs per iteration:**
1. **Accumulated grid** (`accumulated_grid_iteration_N.png`): Full Nx2 grid built so far
2. **Workflow 2x2 output** (`workflow_output_2x2_iteration_N.png`): Raw workflow result (for debugging)
3. **Bottom 1x2 for next iteration** (`next_input_1x2_iteration_N.png`): Extracted bottom row

**Why this approach:**
- ✓ Don't send large accumulated grids to RunPod (saves bandwidth/cost)
- ✓ Keep workflow input always 2048x1024 (simple, no variable height handling)
- ✓ Python compositing is fast and simple
- ✓ Three outputs allow monitoring progress and debugging

### File Paths and Naming

**Output organization per iteration:**
```
map-generator/outputs/
└── my_map_20250124_143022/  (timestamped run directory)
    ├── iteration_0/
    │   ├── accumulated_grid.png           (2048x2048 - Rows 0-1)
    │   ├── workflow_output_2x2.png        (2048x2048 - Debug)
    │   └── next_input_1x2.png             (2048x1024 - Row 1)
    ├── iteration_1/
    │   ├── accumulated_grid.png           (2048x3072 - Rows 0-2)
    │   ├── workflow_output_2x2.png        (2048x2048 - Debug)
    │   └── next_input_1x2.png             (2048x1024 - Row 2)
    ├── iteration_2/
    │   ├── accumulated_grid.png           (2048x4096 - Rows 0-3)
    │   ├── workflow_output_2x2.png        (2048x2048 - Debug)
    │   └── next_input_1x2.png             (2048x1024 - Row 3)
    ├── final_grid.png                     (symlink to last accumulated_grid.png)
    └── generation_progress.json           (metadata and progress tracking)
```

**Benefits:**
- Easy to monitor progress (check latest iteration folder)
- Debug any iteration by looking at workflow_output_2x2.png
- Can resume from any iteration
- Timestamped runs prevent overwriting

## Example Usage

### Grid Config Mode (Recommended)

```bash
# Generate from a grid configuration file
python map-generator/scripts/extend_texture_down.py \
    --grid-config map-generator/config/my_custom_map.json

# Use example configurations
python map-generator/scripts/extend_texture_down.py \
    --grid-config map-generator/config/example_map_simple.json

python map-generator/scripts/extend_texture_down.py \
    --grid-config map-generator/config/example_map_complex.json

# Use custom prompts file with grid config
python map-generator/scripts/extend_texture_down.py \
    --grid-config map-generator/config/my_map.json \
    --prompts map-generator/config/custom_prompts.json
```

### CLI Pattern Mode (Quick Testing)

```bash
# Generate 5x2 alternating pattern (grass/stone swap each row)
python map-generator/scripts/extend_texture_down.py \
    --rows 5 \
    --input input/grass_stone_row.png \
    --pattern "grass,stone"

# Generate uniform grass tiles (all same)
python map-generator/scripts/extend_texture_down.py \
    --rows 3 \
    --input input/grass_grass_row.png \
    --pattern "grass,grass"

# Generate explicit custom pattern
python map-generator/scripts/extend_texture_down.py \
    --rows 4 \
    --input input/start.png \
    --pattern "grass,stone;stone,grass;dirt,sand;mud,gravel"

# Use custom prompts file
python map-generator/scripts/extend_texture_down.py \
    --rows 3 \
    --input input/custom_tiles.png \
    --pattern "dirt,sand" \
    --prompts map-generator/config/custom_prompts.json
```

## Implementation Progress

### Phase 0: Modify Workflow Copy (Split Transition Prompts)
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 1: Extract Prompts and Create JSON Config
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 2: Create Workflow Update Functions
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 3: Implement RunPod Submission and Polling
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 4: Implement Main Generator Loop
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 5: Add Error Handling and Validation
- [ ] Implementation Complete
- [ ] Testing Complete
