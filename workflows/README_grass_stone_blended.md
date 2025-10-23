# Grass-Stone Blended Texture Workflow

**File:** `grass_stone_blended_transition_api.json`

## Overview

ComfyUI workflow that generates seamless blended floor textures for video games. Creates a 2048x1024 texture with grass on the left, stone on the right, and a natural organic transition in the middle where materials mix together.

## Quick Start

### Requirements

**Models:**
- `sd_xl_base_1.0.safetensors` (base generation)
- `sd_xl_base_1.0_inpainting_0.1.safetensors` (stone inpainting)
- `sdxl_vae.safetensors` (VAE)
- `Hand-Painted_2d_Seamless_Textures-000007.safetensors` (LoRA)

**Custom Nodes:**
- `masquerade-nodes-comfyui` (for Create Rect Mask, Blur, Image To Mask)

### Usage

**Local (via ComfyUI UI):**
1. Load workflow in ComfyUI
2. Click "Queue Prompt"
3. Wait ~2-3 minutes for 5 output images

**Local (via command line):**
```bash
python scripts/send-to-runpod.py --workflow workflows/grass_stone_blended_transition_api.json
```

**RunPod Serverless:**
```bash
python scripts/send-to-runpod.py --workflow workflows/grass_stone_blended_transition_api.json --no-open
```

## Output Images

The workflow generates 5 images:

1. **step1_grass_base** - Initial grass generation (1024x1024)
2. **step2_grass_refined** - Refined grass with more detail (1024x1024)
3. **step3_grass_plus_blank** - Grass padded with blank space on right (2048x1024)
4. **step3b_grass_and_stone_before_blend** - Grass + stone without blending (2048x1024)
5. **step4_grass_stone_BLENDED_FINAL** - Final result with blended transition (2048x1024) ✨

## Architecture

### Three-Stage Process

```
Stage 1: Grass Generation
┌─────────────────────────────────────┐
│  1. Generate base grass (1024x1024) │
│  2. Refine with img2img (denoise 0.8)│
│  Output: Stylized grass texture     │
└─────────────────────────────────────┘
                  ↓
Stage 2: Stone Generation
┌─────────────────────────────────────┐
│  1. Pad canvas 1024px to right      │
│  2. Inpaint stone texture (denoise 1.0)│
│  Output: Grass + Stone (hard edge)  │
└─────────────────────────────────────┘
                  ↓
Stage 3: Blend Transition (KEY INNOVATION)
┌─────────────────────────────────────┐
│  1. Create 1024px wide mask         │
│  2. Blur mask edges (radius 48)     │
│  3. Inpaint with mixing prompt      │
│     (denoise 0.85, high intensity)  │
│  4. Composite blended result        │
│  Output: Natural organic transition │
└─────────────────────────────────────┘
```

### Key Innovation: Blurred Mask + High Denoise

The transition zone uses a **blurred rectangular mask** combined with **high denoise (0.85)** to achieve natural blending:

1. **Wide transition zone (1024px)** - Covers 512px into each material
2. **Blurred mask edges** - Creates soft gradients instead of hard boundaries
3. **High denoise** - Generates new mixed content rather than preserving averaged pixels
4. **Mixing prompt** - Explicitly requests grass in stone cracks and stone fragments in grass

## Customization

### Adjust Blend Intensity

**More aggressive blending:**
```json
"denoise": 0.9,  // Node 104
"cfg": 8.5
```

**More subtle blending:**
```json
"denoise": 0.7,  // Node 104
"cfg": 7.0
```

### Adjust Transition Width

**Wider transition (e.g., 1200px):**
```json
// Node 100
"x": 724,          // = 1024 - (1200/2)
"width": 1200
```

**Narrower transition (e.g., 800px):**
```json
// Node 100
"x": 624,          // = 1024 - (800/2)
"width": 800
```

### Adjust Edge Softness

**Softer, more gradual edges:**
```json
// Node 113 (Blur)
"radius": 48,          // Maximum
"sigma_factor": 3.0    // Increase for stronger blur
```

**Sharper edges:**
```json
// Node 113 (Blur)
"radius": 24,          // Reduce
"sigma_factor": 1.0    // Reduce
```

### Change Materials

To adapt for other material combinations (e.g., dirt→sand, wood→metal):

1. **First Material Prompts** (Nodes 4, 10):
   - Change grass descriptions to your first material

2. **Second Material Prompts** (Nodes 50, 51):
   - Change stone descriptions to your second material

3. **Blend Prompt** (Node 101):
   - Update to describe how materials should mix
   - Example for dirt→sand: "natural transition between dirt and sand, sand grains scattered in dirt, dirt patches in sand, organic boundary"

4. **Keep same architecture** - The transition system works for any materials

## Parameters Reference

### Node 100: Create Rect Mask (Transition Zone)
```json
{
  "mode": "pixels",
  "origin": "topleft",
  "x": 774,           // Position: 1024 - (width/2)
  "y": 0,
  "width": 1024,      // Covers 512px into each material
  "height": 1024,
  "image_width": 2048,
  "image_height": 1024
}
```

### Node 113: Blur (Soften Mask Edges)
```json
{
  "radius": 48,        // Maximum blur radius
  "sigma_factor": 2.0  // Blur intensity
}
```

### Node 104: KSampler (Blend Pass)
```json
{
  "seed": 45,          // Fixed for reproducibility
  "steps": 40,         // High quality
  "cfg": 8.0,          // Strong prompt adherence
  "denoise": 0.85      // High intensity - generates new mixed content
}
```

## Troubleshooting

### Only 3 images generated (workflow stops at padding)

**Cause:** Custom node missing or failed execution

**Solutions:**
1. Check `masquerade-nodes-comfyui` is installed
2. Verify node 100 (Create Rect Mask) executes
3. Check ComfyUI console for errors

### Gray strip in transition zone (no texture)

**Cause:** Denoise too low, preserving averaged gray pixels

**Solution:** Increase denoise in node 104 to ≥0.75

### Hard line visible at transition edges

**Cause:** Insufficient blur on mask

**Solutions:**
1. Increase blur radius in node 113 (try 48 max)
2. Increase sigma_factor in node 113 (try 2.5-3.0)

### Transition too narrow/wide

**Solution:** Adjust width in node 100 and recalculate x position:
```
x = 1024 - (width / 2)
```

## Performance

**Execution Time (RunPod H100):**
- Total: ~90-120 seconds
- Grass generation: ~25-30s
- Stone generation: ~25-30s
- Blend pass: ~30-40s

**VRAM Usage:**
- Peak: ~12-15GB
- Recommended: 16GB+ GPU

## Technical Details

### Why This Approach Works

**Problem:** Simple alpha blending or feathering creates fades/gradients, not material mixing.

**Solution:** Use inpainting with explicit mixing prompt in a blurred transition zone:

1. **Blurred mask** provides soft edges
2. **High denoise (0.85)** generates new content instead of preserving underlying pixels
3. **Mixing prompt** guides the AI to create grass/stone intermixing
4. **Wide zone (1024px)** gives enough space for gradual material transition

### Node Type Conversions

⚠️ **Important:** `Create Rect Mask` returns IMAGE type, not MASK type.

Must use `Image To Mask` (node 114) to convert before feeding to `VAEEncodeForInpaint`.

### Debugging Tips

1. **Add SaveImage nodes** between stages to verify each step
2. **Check node execution order** - later nodes depend on earlier ones
3. **Verify custom nodes installed** - workflow uses masquerade-nodes-comfyui
4. **Monitor VRAM usage** - high denoise + large canvases = memory intensive

## Credits

- Base concept: Outpainting with inpaint refinement
- Innovation: Blurred mask + high denoise for material blending
- Models: Stable Diffusion XL + hand-painted textures LoRA
- Custom nodes: masquerade-nodes-comfyui

## License

This workflow is provided as-is for game development and creative projects.
