# ComfyUI Mask Blur Nodes Reference

Comprehensive guide to mask blurring nodes in ComfyUI, including installation, parameters, and example workflows.

## Primary Mask Blur Nodes

### 1. ImpactGaussianBlurMask (ComfyUI-Impact-Pack)

Most popular for mask blurring, smooths edges and reduces noise.

**Parameters:**
- `kernel_size`: Size of blur kernel (0-100, default: 10)
- `sigma`: Standard deviation for blur spread (0.1-100.0, default: 10.0)

**Installation:**
```bash
cd docker/ComfyUI/custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack
uv pip install -r ComfyUI-Impact-Pack/requirements.txt
```

### 2. MaskBlur+ (ComfyUI_essentials)

Gaussian blur specifically for softening mask edges.

**Parameters:**
- `amount`: Blur intensity (0-256, default: 6)
- `device`: Hardware selection (auto/cpu/gpu)

**Installation:**
```bash
cd docker/ComfyUI/custom_nodes
git clone https://github.com/cubiq/ComfyUI_essentials
uv pip install -r ComfyUI_essentials/requirements.txt
```

### 3. BlurMaskFast (ComfyUI-Image-Filters)

Fast OpenCV-based Gaussian blur with directional control.

**Parameters:**
- `radius_x`: Horizontal blur (0-1023, default: 1)
- `radius_y`: Vertical blur (0-1023, default: 1)

**Installation:**
```bash
cd docker/ComfyUI/custom_nodes
git clone https://github.com/spacepxl/ComfyUI-Image-Filters
uv pip install -r ComfyUI-Image-Filters/requirements.txt
```

### 4. Blur (masquerade-nodes-comfyui)

General-purpose blur for masks and images with ClipSeg integration.

**Parameters:**
- `blur_radius`: Area size for blur effect
- `sigma`: Gaussian spread (usually leave at 1)

**Installation:**
```bash
cd docker/ComfyUI/custom_nodes
git clone https://github.com/BadCafeCode/masquerade-nodes-comfyui
uv pip install -r masquerade-nodes-comfyui/requirements.txt
```

### 5. INPAINT_MaskedBlur (comfyui-inpaint-nodes)

Selective blur with mask grow/feather functionality for inpainting workflows.

**Installation:**
```bash
cd docker/ComfyUI/custom_nodes
git clone https://github.com/Acly/comfyui-inpaint-nodes
uv pip install -r comfyui-inpaint-nodes/requirements.txt
```

## Example Workflows

### Best Sources for Example Workflows

1. **Acly's Inpaint Nodes** (has workflow JSON files):
   - Repository: https://github.com/Acly/comfyui-inpaint-nodes
   - Workflows: https://github.com/Acly/comfyui-inpaint-nodes/tree/main/workflows
   - Includes: simple, refine, and outpaint workflows with mask feathering

2. **Impact Pack Tutorial Workflows**:
   - Repository: https://github.com/ltdrdata/ComfyUI-extension-tutorials
   - Advanced tutorials with Gaussian blur examples
   - Video tutorials available on YouTube playlist

3. **Stable Diffusion Art Tutorial**:
   - Tutorial: https://stable-diffusion-art.com/inpaint-comfyui/
   - Downloadable JSON workflows for inpainting with mask blur
   - Multiple methods covered: standard models, inpainting models, ControlNet

4. **OpenArt Workflow Database**:
   - Database: https://openart.ai/workflows/
   - Searchable database with drag-and-drop JSON workflows
   - Filter by "inpaint" or "mask blur"

5. **ComfyUI Wiki**:
   - Examples: https://comfyui-wiki.com/en/workflows/inpaint
   - Tutorials: https://comfyui-wiki.com/en/tutorial/basic/how-to-inpaint-an-image-in-comfyui

## Typical Usage Pattern

```
LoadImage
  → MaskEditor/ClipSeg
  → GrowMask (optional)
  → ImpactGaussianBlurMask
  → InpaintModelConditioning
  → KSampler
  → VAEDecode
```

## Recommended Parameter Values

### Subtle Blur (Soft Edges)
- **kernel_size**: 3-5
- **sigma**: 1.0-2.0
- **Use case**: Minor edge softening, natural transitions

### Moderate Blur (Standard Feathering)
- **kernel_size**: 10-15
- **sigma**: 5.0-10.0
- **Use case**: Typical inpainting, blending operations

### Heavy Feathering (Strong Blur)
- **kernel_size**: 20-30
- **sigma**: 15.0-20.0
- **Use case**: Large area blending, artistic effects

## Common Workflow Patterns

### Pattern 1: Basic Inpainting with Mask Blur
```
1. Load base image
2. Create/load mask
3. Blur mask (ImpactGaussianBlurMask)
4. Apply inpaint model
5. Sample with KSampler
6. Decode and save
```

### Pattern 2: Mask Grow + Blur (Expanded Feathering)
```
1. Load base image
2. Create/load mask
3. Grow mask by N pixels (GrowMask)
4. Blur grown mask (ImpactGaussianBlurMask)
5. Apply inpaint processing
6. Sample and composite
```

### Pattern 3: Selective Area Blur
```
1. Load image
2. Generate mask with ClipSeg (text-based)
3. Blur mask for soft selection
4. Apply INPAINT_MaskedBlur to blur only masked area
5. Composite results
```

## Best Practices

1. **Start Small**: Begin with low blur values and increase gradually
2. **Match Context**: Use subtle blur for detailed work, heavy for backgrounds
3. **Combine Nodes**: Chain GrowMask + GaussianBlurMask for best feathering
4. **Test Iterations**: Preview mask after blur to verify edge quality
5. **Hardware Selection**: Use GPU for large masks (MaskBlur+ device parameter)

## Node Comparison

| Node | Speed | Quality | Features | Best For |
|------|-------|---------|----------|----------|
| ImpactGaussianBlurMask | Medium | High | Kernel + Sigma control | General purpose |
| MaskBlur+ | Fast | High | GPU acceleration | Production workflows |
| BlurMaskFast | Very Fast | Good | Directional blur | Quick iterations |
| Blur (masquerade) | Medium | High | ClipSeg integration | Dynamic masking |
| INPAINT_MaskedBlur | Medium | High | Grow + blur combo | Inpainting |

## Additional Resources

- **ComfyUI Official Docs**: https://docs.comfy.org/tutorials/basic/inpaint
- **ComfyUI Community Manual**: https://blenderneko.github.io/ComfyUI-docs/
- **Node Documentation**: https://comfyai.run/ (searchable node reference)
- **RunComfy Node Index**: https://www.runcomfy.com/comfyui-nodes/

## Installation Notes

For this project (comfy-runpod):
- Install custom nodes to `docker/ComfyUI/custom_nodes/`
- Use `uv pip install -r requirements.txt` for dependencies
- Update Docker build to include nodes for production deployment
- Test locally before deploying to RunPod

Recommended for this project:
- **ComfyUI-Impact-Pack**: Essential for mask processing
- **comfyui-inpaint-nodes**: For inpainting workflows
- **masquerade-nodes-comfyui**: For ClipSeg-based dynamic masking
