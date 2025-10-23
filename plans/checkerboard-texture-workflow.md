# Checkerboard Texture Workflow - Implementation Plan

## Overview

Create a ComfyUI workflow that generates a 2x2 checkerboard pattern of blended floor textures (2048x2048 total). Starting from a pre-generated grass→stone horizontal blend (2048x1024), extend downward 1024px and create:
- **Top row**: Grass (left) → Stone (right) with horizontal blend (loaded from input)
- **Bottom row**: Stone (left) → Grass (right) (generated as separate tiles)
- **Vertical seams**: Blended transitions where materials meet vertically

**Goals:**
- Load pre-generated top row from input directory
- Generate bottom tiles separately for consistency
- Create checkerboard layout with natural blended seams
- Maintain seamless tiling capability

## Technical Analysis

### Starting Point

We have `grass_stone_blended_transition_api.json` which produces:
```
[Grass 1024x1024] [Blend 1024x1024] [Stone 1024x1024]
        ↓                 ↓                ↓
    (0,0)            (1024,0)         (No need - center of blend)
```

Result: 2048x1024 image with grass→stone horizontal transition

### Target Layout

```
2048x2048 final image:

+----------------+----------------+
|     Grass      |  Horiz Blend   |     Stone      |
|   (0, 0)       |   (1024, 0)    |                |
|                |                |                |
+-------+--------+--------+-------+
|       |        |        |       |
| Vert  | CENTER | CENTER | Vert  |
| Blend | 4-WAY  | 4-WAY  | Blend |
|       | BLEND  | BLEND  |       |
+-------+--------+--------+-------+
|     Stone      |  Horiz Blend   |     Grass      |
|   (0, 1024)    |   (1024, 1024) |                |
|                |                |                |
+----------------+----------------+

Dimensions:
- Total: 2048x2048
- Each quadrant: 1024x1024
- Horizontal blend zones: 1024px wide (512px into each material)
- Vertical blend zones: 1024px tall (512px into each material)
- Center 4-way junction: 1024x1024 area where all blends overlap
```

### Key Challenge: The Center 4-Way Junction

The center 1024x1024 area is the most complex region:
- **Top-left quadrant** (512x512): Grass transitioning to both Stone (right) and Stone (down)
- **Top-right quadrant** (512x512): Stone transitioning to both Grass (left) and Grass (down)
- **Bottom-left quadrant** (512x512): Stone transitioning to both Grass (right) and Grass (up)
- **Bottom-right quadrant** (512x512): Grass transitioning to both Stone (left) and Stone (up)

**The center point (1024, 1024)** is where all four materials meet - this requires special handling.

## Solution Architecture

### Revised Six-Stage Approach (Properly Decomposed)

**Stage 0: Prepare Input** [MANUAL STEP]
- Run existing grass_stone_blended_transition_api.json workflow
- Save final output: step4_grass_stone_BLENDED_FINAL_*.png (2048x1024)
- Copy to input directory with consistent name: `grass_stone_row.png`
- This becomes our starting point

**Stage 1: Load and Pad Downward**
- Load `grass_stone_row.png` from input directory (2048x1024)
- Pad 1024px downward using ImagePadForOutpaint
- Output: 2048x2048 canvas (top filled, bottom blank)

**Stage 2a: Inpaint Bottom-Left (Stone)**
- Mask: Bottom-left quadrant (x=0-1024, y=1024-2048)
- Use inpainting checkpoint + LoRA
- Use stone prompts (same as original workflow)
- Seed: 44 (same as top-right stone for consistency)
- Denoise: 1.0 (full generation)
- Output: Stone tile in bottom-left

**Stage 2b: Inpaint Bottom-Right (Grass)**
- Mask: Bottom-right quadrant (x=1024-2048, y=1024-2048)
- Use inpainting checkpoint + LoRA
- Use grass prompts (same as original workflow)
- Seed: 42 (same as top-left grass for consistency)
- Denoise: 1.0 (full generation)
- Output: Grass tile in bottom-right
- Result: All four quadrants filled, but three hard seams (center vertical, left vertical, right vertical)

**Stage 3: Blend Bottom Center Vertical Seam** (Stone ↔ Grass)
- Mask: Vertical strip at bottom center (x=512-1536, y=1024-2048) [1024px wide, centered on x=1024]
- Blur mask edges horizontally (radius 48)
- Use grass/stone mixing prompt (same as top center blend)
- Seed: 46
- Denoise: 0.85 (high blend intensity)
- Output: Bottom row now has stone→grass blend (mirrors top grass→stone)

**Stage 4: Blend Left Vertical Seam** (Grass top ↔ Stone bottom)
- Mask: Vertical strip at left edge (x=0-512, y=512-1536) [512px wide, 1024px tall]
- Blur mask edges vertically (radius 48)
- Use grass/stone mixing prompt
- Seed: 47
- Denoise: 0.85
- Output: Left edge blended

**Stage 5: Blend Right Vertical Seam** (Stone top ↔ Grass bottom)
- Mask: Vertical strip at right edge (x=1536-2048, y=512-1536) [512px wide, 1024px tall]
- Blur mask edges vertically (radius 48)
- Use grass/stone mixing prompt
- Seed: 48
- Denoise: 0.85
- Output: Right edge blended, all seams now natural

**Note:** Right vertical mask (x=1536-2048) intentionally overlaps bottom center mask (x=512-1536) by 24px. This is acceptable for testing - we'll verify if overlapping blends produce good results.

**Benefits of This Approach:**
1. **Reuses proven technique** - Each blend is same as original horizontal blend (just rotated/positioned)
2. **No 4-way complexity** - Each blend is simple 2-material transition
3. **Modular** - Four separate tiles + three separate blends = clear separation
4. **Consistent style** - Bottom tiles use same seeds as matching top tiles
5. **Three independent blends** - Can iterate on each separately if needed

## Phases

### Phase 1: Analysis and Planning
**Goal:** Fully understand the problem and design the blending strategy

**Tasks:**
- Read existing grass_stone_blended workflow
- Map out 2048x2048 coordinate system
- Design mask positions for all blend zones
- Calculate overlap regions
- Decide on single vs multi-pass center blending

**Deliverable:** Clear coordinate mappings and mask specifications

### Phase 2: Create Base Layout (Generate Bottom Tiles)
**Goal:** Generate stone and grass tiles for bottom row

**Tasks:**
- Add LoadImage node to load `grass_stone_row.png` from input directory
- Add ImagePadForOutpaint node (pad bottom 1024px)
- Add Create Rect Mask for bottom-left (x=0, y=1024, w=1024, h=1024)
- Add VAEEncodeForInpaint for bottom-left stone
- Add KSampler with stone prompts, seed 44, denoise 1.0
- Add VAEDecode + ImageCompositeMasked for stone tile
- Add Create Rect Mask for bottom-right (x=1024, y=1024, w=1024, h=1024)
- Add VAEEncodeForInpaint for bottom-right grass
- Add KSampler with grass prompts, seed 42, denoise 1.0
- Add VAEDecode + ImageCompositeMasked for grass tile
- Add SaveImage for debugging (all tiles, hard seams visible)

**Deliverable:** 2048x2048 with all four quadrants filled, three hard seams

### Phase 3: Blend Bottom Center Vertical Seam
**Goal:** Blend stone/grass in bottom row (mirrors top row blend)

**Tasks:**
- Add Create Rect Mask for bottom center (x=512, y=1024, w=1024, h=1024)
- Add Blur node with radius 48, sigma_factor 2.0 (horizontal blur)
- Add Image To Mask converter
- Add VAEEncodeForInpaint
- Add KSampler with grass/stone mixing prompt, seed 46, denoise 0.85
- Add VAEDecode + ImageCompositeMasked
- Add SaveImage (bottom row now blended)

**Deliverable:** Bottom row has natural stone→grass transition

### Phase 4: Blend Vertical Seams (Left and Right Edges)
**Goal:** Blend left (grass/stone) and right (stone/grass) vertical edges

**Tasks:**
- Add Create Rect Mask for left vertical (x=0, y=512, w=512, h=1024)
- Add Blur + Image To Mask + VAEEncodeForInpaint
- Add KSampler with seed 47, denoise 0.85
- Add VAEDecode + ImageCompositeMasked
- Add Create Rect Mask for right vertical (x=1536, y=512, w=512, h=1024)
- Add Blur + Image To Mask + VAEEncodeForInpaint
- Add KSampler with seed 48, denoise 0.85
- Add VAEDecode + ImageCompositeMasked
- Add SaveImage for final result

**Deliverable:** All three seams blended naturally (note: right vertical overlaps bottom center by 24px for testing)

### Phase 5: Testing and Refinement
**Goal:** Ensure quality across all seams and optimize parameters

**Tasks:**
- Test full workflow end-to-end
- Verify checkerboard pattern recognizable
- Check all three blend zones (bottom center vertical, left vertical, right vertical)
- Verify no visible hard seams
- Test seamless tiling (tile 2x2)
- Evaluate overlapping blend region (bottom center + right vertical)
- Adjust denoise/blur if needed

**Deliverable:** Production-ready workflow with validated results

### Phase 6: Documentation
**Goal:** Document the workflow for future use and adaptation

**Tasks:**
- Update plan with final parameters and results
- Create README explaining coordinate system and blend zones
- Document center blending strategy and why it works
- Add adaptation guide for different layouts (3x3, etc.)
- Document performance metrics

**Deliverable:** Complete documentation

## Alternatives Considered

### Alternative 1: Generate Entire Bottom Row as Single Inpaint

**Approach:** Treat bottom 2048x1024 as one region, prompt for "stone on left transitioning to grass on right"

**Pros:**
- Fewer nodes - simpler workflow
- AI naturally creates horizontal blend in bottom row
- Mirrors top row architecture (grass→stone vs stone→grass)
- Avoids 4-way complexity - center is just two horizontal blends meeting

**Cons:**
- Difficult to generate high-quality gradient in single pass
- Less control over individual tile consistency
- User feedback: Separate tiles + blending is more reliable
- **REJECTED:** Replaced by Alternative 2 approach

### Alternative 2: Generate All Four Tiles Separately, Then Blend All Seams

**Approach:**
1. Load pre-generated top row (grass→stone with blend)
2. Generate bottom-left stone tile (seed 44)
3. Generate bottom-right grass tile (seed 42)
4. Blend three seams (bottom center vertical, left vertical, right vertical)

**Pros:**
- Very modular and clear separation of concerns
- Leverages existing top row workflow
- Separate tiles ensure consistent style
- Each blend is simple 2-material transition
- **SELECTED:** This is the implemented approach

**Cons:**
- More nodes than single-pass bottom row
- Three separate blend passes (acceptable for quality)

### Alternative 3: Hierarchical Blending (Blend Pairs, Then Blend Pairs)

**Approach:**
1. Generate top row with blend (grass→stone)
2. Generate bottom row with blend (stone→grass)
3. Composite into 2048x2048
4. Single horizontal blend pass through center

**Pros:**
- Only one seam to blend (horizontal through middle)
- Simpler conceptually

**Cons:**
- Bottom row would be independent workflow execution
- Still need to handle left/right vertical seams somehow
- Horizontal blend alone won't fix vertical discontinuities
- **Rejected:** Doesn't address vertical seam problem

### Alternative 4: Circular Dependency Resolution (Iterative Refinement)

**Approach:**
1. Generate base tiles with hard seams
2. Blend one seam
3. Blend second seam (considering first blend)
4. Re-blend first seam (considering second blend)
5. Iterate until convergence

**Pros:**
- Might produce highest quality results
- Accounts for interdependencies

**Cons:**
- Extremely slow (3-5 full inpaint passes)
- Complexity high
- Diminishing returns after 2-3 iterations
- **Rejected:** Overengineered for this use case

**Selected Solution:** Alternative 2 - Load input image, pad downward, generate bottom tiles separately (stone left, grass right), blend three seams (bottom center vertical, left vertical, right vertical). Modular approach with proven blending technique.

## Key Design Decisions

### Decision 1: Load Input Image vs Embed Entire Workflow

**Options:**
- **A:** Embed grass_stone_blended workflow inside new workflow
- **B:** Load pre-generated image from input directory

**Decision:** Option B (load from input)

**Rationale (user feedback):**
- Simpler workflow (fewer nodes)
- Faster iteration (don't regenerate top row every test)
- Modular approach (top row already validated)
- Can easily swap different top rows
- Workflow focuses only on new functionality (bottom row + blend)

### Decision 2: Bottom Row Generation Strategy

**Options:**
- **A:** Generate two separate tiles (stone left, grass right) then blend
- **B:** Generate entire bottom row as single inpaint with horizontal blend

**Decision:** Option A (separate tiles then blend)

**Rationale (user feedback):**
- More reliable quality - proven technique for individual tiles
- Better control over material consistency
- Simple 2-material blends instead of complex gradients
- Matches tile-based approach for clarity
- Each blend zone independent and tunable

### Decision 3: Blend Prompt Strategy

**Challenge:** Blend three seams (bottom center vertical, left vertical, right vertical)

**Decision:** Reuse existing grass/stone mixing prompt for all three blends

**Prompt (same as original horizontal blend):**
```
natural transition between grass and stone, grass growing between stone cracks,
moss on stones, weathered stone edges with grass, organic boundary, small grass
tufts emerging from stone gaps, stone fragments scattered in grass, seamless
blend, hand painted game texture
```

**Rationale:**
- Each seam is simple 2-material transition (grass ↔ stone)
- Proven prompt that already works well for horizontal blend
- Same prompt works for vertical blends (rotated context)
- Consistency across all three blend zones
- Simpler = more predictable results

### Decision 4: Seed Management

**Challenge:** Maintain consistent style across tiles and blends

**Decision:**
- Bottom-left stone: seed 44 (matches top-right stone)
- Bottom-right grass: seed 42 (matches top-left grass)
- Bottom center blend: seed 46
- Left vertical blend: seed 47
- Right vertical blend: seed 48

**Rationale:**
- Bottom tiles match top tiles for style consistency
- Different seeds for each blend zone provide variation
- Same LoRA/prompts ensure overall cohesion
- Allows natural texture variation without repetition
- Can tune individual zones if needed during testing

## Testing Strategy

### Phase 2 Testing: Base Layout
- **Method:** Visual inspection of 2048x2048 output
- **Success Criteria:**
  - All four quadrants filled
  - Top-left: Grass (from input)
  - Top-right: Stone (from input)
  - Bottom-left: Stone (newly generated, matches top-right style)
  - Bottom-right: Grass (newly generated, matches top-left style)
  - Three visible hard seams (bottom center vertical, left vertical, right vertical)

### Phase 3 Testing: Bottom Center Blend
- **Method:** Inspect bottom center vertical seam
- **Success Criteria:**
  - Bottom row has smooth stone→grass transition
  - Mirrors top row's grass→stone transition
  - No hard vertical line at x=1024 in bottom half

### Phase 4 Testing: Vertical Edge Blends
- **Method:** Inspect left and right edges
- **Success Criteria:**
  - Left edge: Smooth grass (top) ↔ stone (bottom) transition
  - Right edge: Smooth stone (top) ↔ grass (bottom) transition
  - No hard horizontal lines at y=1024 on edges
  - Natural material mixing vertically

### Phase 5 Testing: Tiling and Overall Quality
- **Method:** Tile result 2x2 and check all seams
- **Success Criteria:**
  - Seamless horizontal tiling (left edge matches right edge)
  - Seamless vertical tiling (top edge matches bottom edge)
  - Checkerboard pattern recognizable but naturally blended
  - Usable as game texture asset
  - No obvious artifacts or generation errors

### Performance Testing (Revised)
- **Method:** Time each stage on RunPod
- **Expected:**
  - Stage 0 (pre-generate top row): ~90s (done manually beforehand)
  - Stage 1 (load + pad): <1s
  - Stage 2a (bottom-left stone): ~30s
  - Stage 2b (bottom-right grass): ~30s
  - Stage 3 (bottom center blend): ~40s
  - Stage 4 (left vertical blend): ~40s
  - Stage 5 (right vertical blend): ~40s
  - **Total: ~180-210 seconds (~3-3.5 minutes)**
  - Comparable to original horizontal blend workflow

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Bottom tiles don't match top tile style despite same seeds | Low | Medium | Use same LoRA strength, CFG, steps. Same seeds as matching top tiles ensure consistency. |
| Vertical seams interfere with top row blend | Low | Medium | Carefully position vertical masks to start at y=512 (below top blend zone). |
| Overlapping blends (right vertical + bottom center) cause artifacts | Medium | Medium | Testing with 24px overlap. May need to adjust if problematic. |
| Workflow too slow (>3.5 minutes) | Low | Low | Acceptable for high-quality result. Can optimize by reducing steps if needed. |
| Blend prompt produces unexpected results on vertical seams | Low | Medium | Same proven prompt from horizontal blend. Can adjust denoise if needed. |
| Memory exhaustion (2048x2048 image + multiple passes) | Low | High | Monitor VRAM. RunPod H100 has adequate memory for this workflow. |

## Coordinate Reference

### Mask Positions (All in pixels, origin top-left)

**Top Row (Existing):**
- Grass: (0, 0) to (1024, 1024)
- Horizontal blend: (512, 0) to (1536, 1024) [1024px wide]
- Stone: (1024, 0) to (2048, 1024)

**Bottom Row (New):**
- Stone: (0, 1024) to (1024, 2048)
- Horizontal blend: (512, 1024) to (1536, 2048) [1024px wide, mirrors top]
- Grass: (1024, 1024) to (2048, 2048)

**Vertical Seams:**
- Left vertical: (0, 512) to (512, 1536) [512px wide, 1024px tall]
- Right vertical: (1536, 512) to (2048, 1536) [512px wide, 1024px tall]

**Center Junction:**
- Center 4-way: (512, 512) to (1536, 1536) [1024x1024 square]

**Overlap Regions:**
- Top-center: (512, 0) to (1536, 512) - Existing horizontal blend's top half
- Bottom-center: (512, 1536) to (1536, 2048) - Horizontal blend's bottom half
- Left-center: (0, 512) to (512, 1536) - Vertical blend's left half
- Right-center: (1536, 512) to (2048, 1536) - Vertical blend's right half
- True center: (512, 512) to (1536, 1536) - Where all overlaps meet

## Implementation Progress

### Phase 1: Analysis and Planning
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 2: Create Base Layout (Generate Bottom Tiles)
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 3: Blend Bottom Center Vertical Seam
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 4: Blend Vertical Edge Seams
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 5: Testing and Refinement
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 6: Documentation
- [ ] Implementation Complete
- [ ] Testing Complete
