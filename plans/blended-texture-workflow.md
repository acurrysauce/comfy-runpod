# Blended Texture Workflow - Implementation Plan

## Overview

Create a ComfyUI workflow in API format that generates seamless blended floor textures for video games. The workflow generates a base grass texture (1024x1024), then pads it 1024px to the right and generates a stone texture with natural mixing/blending at the boundary (grass growing between stones, stone fragments in grass).

**Goals:**
- Generate high-quality hand-painted game textures
- Natural transition between grass and stone materials
- Maintain API format for programmatic use
- Seamless tiling support

**Key Challenge:** The existing workflow (`test_simple_inpaint_refined_grass_2_api.json`) creates hard boundaries between materials. We need organic blending where materials intermix.

## Technical Analysis

### Current Workflow Issues

The existing workflow has these problems:

1. **Node 11 (ImagePadForOutpaint)**: `feathering: 0` creates a binary mask with hard edge
2. **Node 16 (VAEEncodeForInpaint)**: `grow_mask_by: 12` only slightly expands the inpaint region
3. **Node 17 (KSampler - Stone)**: Uses full `denoise: 1.0`, completely replacing content in mask area
4. **No transition zone**: The workflow fills grass (left 1024px) then stone (right 1024px) with no overlap
5. **Prompt doesn't request blending**: Stone prompt actively excludes grass in negative prompt

### Root Cause

The workflow treats the boundary as a **hard cut** rather than a **transition zone**. To get natural blending, we need:

1. A wider transition mask that overlaps both materials
2. Lower denoise strength to preserve underlying textures
3. A dedicated "blend pass" with prompts asking for mixed elements
4. Multiple inpainting passes: first fill new area, then blend boundary

## Solution Architecture

### Three-Stage Approach

**Stage 1: Generate Base Grass Texture** (existing, works well)
- Generate 1024x1024 grass base
- Refine with img2img pass
- Output: Clean grass tile

**Stage 2: Generate Stone Texture** (existing, works well)
- Pad canvas 1024px to the right
- Inpaint stone floor in new area
- Output: Grass + Stone with hard boundary

**Stage 3: Blend Transition Zone** (NEW - this is the key improvement)
- Create a 300px wide mask centered on boundary (150px into grass, 150px into stone)
- Use low denoise (0.6-0.7) to preserve both textures underneath
- Prompt explicitly requests mixed elements (grass in stone cracks, stone chips in grass)
- Output: Naturally blended transition

### Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Transition mask X position | 874px | Centers 300px mask on 1024px boundary (1024 - 150 = 874) |
| Transition mask width | 300px | 150px into each material for gradual blend |
| Blend denoise strength | 0.6-0.7 | Low enough to preserve both textures, high enough to add new elements |
| Blend CFG | 7.0 | Standard guidance for balance |
| Blend steps | 30 | More steps for smoother blending |

### Node Dependencies

```
Grass Pipeline:
1 (Checkpoint) → 3 (LoRA) → 7 (KSampler) → 8 (VAEDecode) → 9 (Save)
                            ↓
                   13 (VAEEncode) → 14 (Refine KSampler) → 15 (VAEDecode) → 21 (Save)

Padding:
15 (Refined Grass) → 11 (Pad Right) → 12 (Save)

Stone Pipeline:
400 (Inpaint Checkpoint) → 401 (LoRA) → 17 (Stone KSampler) → 18 (VAEDecode)
11 (Padded) → 16 (VAEEncodeForInpaint) ↗                            ↓
                                                        19 (Composite) → 20 (Save - if no blend)

Blend Pipeline (NEW):
100 (Create Rect Mask - 300px transition zone)
19 (Grass+Stone) → 103 (VAEEncodeForInpaint) → 104 (Blend KSampler) → 105 (VAEDecode)
100 (Mask) ↗                                                              ↓
                                                             106 (Composite) → 20 (Save Final)
```

## Phases

### Phase 1: Analyze Existing Workflow
**Goal:** Understand current structure, identify exact nodes causing hard boundaries

**Tasks:**
- Read and parse `test_simple_inpaint_refined_grass_2_api.json`
- Document all nodes and their connections
- Identify mask creation and inpainting parameters
- Test current workflow to confirm hard boundary issue

**Deliverable:** Clear understanding of what needs to change

### Phase 2: Design Blend Strategy
**Goal:** Determine optimal parameters for natural blending

**Tasks:**
- Research: What denoise strength preserves underlying content?
- Research: What mask width gives natural transitions?
- Design transition zone dimensions (recommend 300px: 150px each side)
- Design blend prompts (grass in stone cracks, stone chips in grass, moss, weathering)
- Choose blend sampler settings (steps, CFG, denoise)

**Deliverable:** Parameter specifications for Phase 3

### Phase 3: Create New Workflow with Blend Pass
**Goal:** Implement the new workflow in API format

**Tasks:**
- Copy existing workflow as base
- Add new nodes:
  - Node 100: `Create Rect Mask` for transition zone (x=874, width=300)
  - Node 101: Positive prompt for blending
  - Node 102: Negative prompt avoiding hard edges
  - Node 103: `VAEEncodeForInpaint` for blend region
  - Node 104: `KSampler` with low denoise (0.65)
  - Node 105: `VAEDecode` for blend result
  - Node 106: `ImageCompositeMasked` to apply blend
- Update node 20 (final save) to use output from node 106 instead of 19
- Validate JSON structure
- Add descriptive `_meta.title` for all nodes

**Deliverable:** `workflows/grass_stone_blended_transition_api.json`

### Phase 4: Testing and Iteration
**Goal:** Verify blending works, tune parameters if needed

**Tasks:**
- Test workflow locally with `--output-directory` flag
- Verify all stages save correctly (grass base, refined, padded, final blended)
- Inspect transition zone for:
  - Grass growing in stone cracks ✓
  - Stone fragments in grass ✓
  - Natural weathering/moss ✓
  - No hard boundary line ✓
- If blending insufficient, iterate on:
  - Denoise strength (try 0.6, 0.65, 0.7)
  - Mask width (try 250px, 300px, 350px)
  - Blend prompt wording
  - Number of steps (try 25, 30, 35)

**Deliverable:** Tuned workflow with natural blending

### Phase 5: Documentation
**Goal:** Document the workflow for future use

**Tasks:**
- Add comments to workflow explaining each stage
- Document recommended parameter ranges
- Add usage instructions to CLAUDE.md or separate README
- Document how to adapt for other material combinations (grass→dirt, stone→wood, etc.)

**Deliverable:** Documentation for using and adapting the workflow

## Alternatives Considered

### Alternative 1: Feathered Mask on Initial Pad
**Approach:** Set `feathering: 100` on node 11 (ImagePadForOutpaint)

**Pros:**
- Simpler, uses existing nodes
- Single pass blending

**Cons:**
- Feathering creates gradient transparency, not material mixing
- Stone inpainting would just fade to transparent, not blend textures
- Doesn't add grass elements to stone or vice versa
- **Rejected:** Feathering is for soft edges, not material mixing

### Alternative 2: ControlNet Depth/Edge Guidance
**Approach:** Use ControlNet with edge detection to guide blending

**Pros:**
- Very precise control over blend regions
- Could preserve specific structural elements

**Cons:**
- Requires additional models (ControlNet weights)
- Much more complex workflow
- Slower inference
- Overkill for organic material blending
- **Rejected:** Too complex for this use case

### Alternative 3: Multiple Overlapping Inpaint Passes
**Approach:** Create 3-4 narrow masks with progressively lower denoise

**Pros:**
- Extremely smooth gradual transition
- Fine-grained control

**Cons:**
- Workflow becomes very long (8+ additional nodes per pass)
- Much slower (4x inpainting operations)
- Diminishing returns after first blend pass
- **Rejected:** Single well-tuned blend pass should suffice

### Alternative 4: Post-Process Blending with Image Operations
**Approach:** Generate both textures separately, use image blending nodes (ImageBlend, ImageComposite with gradients)

**Pros:**
- Deterministic blending
- Fast execution

**Cons:**
- Simple alpha blending, not semantic mixing
- Wouldn't add grass elements to stone or stone chips to grass
- Looks artificial (gradient overlay rather than natural growth)
- **Rejected:** Need semantic understanding, not just pixel blending

**Selected Solution:** Alternative 0 (our main proposal) - dedicated inpaint blend pass with low denoise and explicit mixing prompt. Best balance of simplicity, quality, and semantic understanding.

## Testing Strategy

### Phase 1 Testing: Workflow Analysis
- **Method:** Manual code inspection
- **Success Criteria:** Complete understanding of node graph documented

### Phase 3 Testing: Workflow Creation
- **Method:** JSON validation
- **Success Criteria:** Valid API format, no syntax errors, all node references correct

### Phase 4 Testing: Visual Quality
- **Method:** Run workflow locally and on RunPod
- **Test Cases:**
  1. **Baseline:** Run old workflow, confirm hard boundary exists
  2. **New workflow:** Run new workflow, compare transition zone
  3. **Zoom inspection:** Examine boundary at 200% zoom for:
     - Grass blades/tufts in stone cracks
     - Stone fragments scattered in grass edge
     - Moss or weathering on stones near grass
     - Gradual material transition (not abrupt)
  4. **Tiling test:** Place result side-by-side horizontally, verify seamless tile
  5. **Parameter sweep:** Test denoise values [0.6, 0.65, 0.7] to find sweet spot

- **Success Criteria:**
  - Visible mixing of materials (grass in stone, stone in grass)
  - No visible hard line at 1024px boundary
  - Natural organic appearance
  - Seamless tiling maintained

### Phase 4 Testing: RunPod Deployment
- **Method:** Test via `send-to-runpod.py`
- **Success Criteria:**
  - Workflow executes without errors
  - All checkpoint/LoRA/VAE files found
  - Output matches local results
  - Execution time reasonable (<2 minutes)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Blend denoise too high → loses original textures | Medium | High | Start at 0.6, iterate up carefully |
| Blend denoise too low → no mixing visible | Medium | High | Test range 0.6-0.75, find sweet spot |
| Transition mask too narrow → still looks like hard edge | Low | Medium | Use 300px minimum (150px each side) |
| Transition mask too wide → affects too much of each texture | Low | Medium | 300px is <15% of each side, should be safe |
| Create Rect Mask node not available | Low | Critical | Check custom nodes, install if needed |
| Blend prompt ignored by model | Low | Medium | Use strong descriptive terms, test prompt variations |
| Workflow breaks on RunPod (missing dependencies) | Low | High | Test early in Phase 4, verify all nodes available |

## Implementation Progress

### Phase 1: Analyze Existing Workflow
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 2: Design Blend Strategy
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 3: Create New Workflow with Blend Pass
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 4: Testing and Iteration
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 5: Documentation
- [ ] Implementation Complete
- [ ] Testing Complete
