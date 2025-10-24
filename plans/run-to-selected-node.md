# Run to Selected Node Feature Plan

## Overview

Add a "Run to Selected" button to ComfyUI that allows users to execute only the workflow nodes necessary to reach a selected target node. This saves time and costs by avoiding execution of downstream nodes that aren't needed for intermediate testing.

**Goals:**
- Allow users to select one or more SaveImage nodes in the workflow graph
- Automatically determine all predecessor nodes required to execute the selected nodes
- Trim the workflow to include only necessary nodes (union of all dependency trees)
- Send trimmed workflow to RunPod for execution
- Maintain compatibility with existing "Queue on RunPod" functionality

**Constraints:**
- Only works with SaveImage nodes (ensures output is generated)
- Supports both single and multiple node selection
- Button disabled if no SaveImage nodes are selected

**Use Case Examples:**
1. **Single SaveImage:** User selects intermediate SaveImage node, executes only its prerequisites
2. **Multiple SaveImage:** User selects 2 SaveImage nodes from different branches, executes union of both dependency trees
3. **Branching workflow:** User has parallel processing paths (path A and path B), selects SaveImage from each, both branches execute

## Phases

### Phase 1: Backend - Workflow Trimming Function

**Files to modify:**
- `/custom_nodes/runpod-queue/__init__.py`

**Implementation:**

1. **Create `get_node_dependencies()` function**
   - Takes: workflow dict, target node ID
   - Returns: set of all node IDs that the target depends on (including target itself)
   - Algorithm: Recursive depth-first search through node inputs
   - Handle both direct inputs and nested inputs

2. **Create `trim_workflow()` function**
   - Takes: workflow dict, list of target node IDs
   - Returns: trimmed workflow dict containing only necessary nodes
   - Steps:
     1. For each target node, call `get_node_dependencies()` to get required node IDs
     2. Union all dependency sets together
     3. Create new workflow dict with only those nodes
     4. Validate that all dependencies are satisfied

**Technical Details:**

Input references in ComfyUI workflows use format: `["node_id", output_slot]`

Example:
```python
def get_node_dependencies(workflow, target_node_id):
    """Recursively find all nodes that target_node_id depends on.

    Args:
        workflow: Dict mapping node_id -> node_data
        target_node_id: ID of the target node to execute

    Returns:
        Set of node IDs (strings) that are required
    """
    dependencies = set()

    def visit_node(node_id):
        if node_id in dependencies:
            return  # Already visited

        node = workflow.get(str(node_id))
        if not node:
            return

        dependencies.add(str(node_id))

        # Check all inputs for node references
        inputs = node.get('inputs', {})
        for input_value in inputs.values():
            # Input can be ["node_id", output_index]
            if isinstance(input_value, list) and len(input_value) >= 2:
                input_node_id = str(input_value[0])
                visit_node(input_node_id)

    visit_node(str(target_node_id))
    return dependencies


def trim_workflow(workflow, target_node_ids):
    """Create a trimmed workflow containing only nodes necessary for targets.

    Args:
        workflow: Dict mapping node_id -> node_data
        target_node_ids: List of target node IDs to execute

    Returns:
        Dict containing trimmed workflow
    """
    # Collect dependencies for all target nodes
    all_required_nodes = set()
    for target_node_id in target_node_ids:
        required_nodes = get_node_dependencies(workflow, target_node_id)
        all_required_nodes.update(required_nodes)

    # Build trimmed workflow
    trimmed = {}
    for node_id in all_required_nodes:
        trimmed[node_id] = workflow[node_id]

    return trimmed
```

**Edge Cases to Handle:**
- Target node doesn't exist in workflow
- Target node has no dependencies (is a source node)
- Circular dependencies (shouldn't exist in valid workflow, but check)
- Missing referenced nodes (invalid workflow)

**Testing:**
- Create test workflow with 5 nodes in linear chain (1→2→3→4→5)
- Test `trim_workflow(workflow, ["3"])` returns nodes {1, 2, 3}
- Test `trim_workflow(workflow, ["1"])` returns node {1}
- Test `trim_workflow(workflow, ["5"])` returns all nodes {1, 2, 3, 4, 5}
- Test `trim_workflow(workflow, ["3", "5"])` returns all nodes {1, 2, 3, 4, 5}
- Test with branching workflow:
  - Workflow: 1→2→3, 1→4→5, SaveImage at 3 and 5
  - `trim_workflow(workflow, ["3"])` returns {1, 2, 3}
  - `trim_workflow(workflow, ["5"])` returns {1, 4, 5}
  - `trim_workflow(workflow, ["3", "5"])` returns {1, 2, 3, 4, 5} (union of both branches)

### Phase 2: Backend - API Route for Run to Selected

**Files to modify:**
- `/custom_nodes/runpod-queue/__init__.py`

**Implementation:**

1. **Create new route** `@server.PromptServer.instance.routes.post('/runpod/queue_to_selected')`
2. **Accept parameters:**
   - `workflow`: Full workflow dict
   - `target_node_ids`: List of selected node IDs
3. **Process request:**
   - Validate that target_node_ids is a list with at least one element
   - Call `trim_workflow()` to get trimmed workflow
   - Save trimmed workflow to temp file
   - Find input images (same as existing logic)
   - Call `send-to-runpod.py` with trimmed workflow
   - Return status to frontend

**Endpoint signature:**
```python
@server.PromptServer.instance.routes.post('/runpod/queue_to_selected')
async def queue_to_selected_on_runpod(request):
    """Handle workflow submission to RunPod with trimming to target nodes."""
    try:
        data = await request.json()
        workflow = data.get('workflow', {})
        target_node_ids = data.get('target_node_ids', [])

        if not target_node_ids or not isinstance(target_node_ids, list):
            return web.json_response({
                "status": "error",
                "message": "No target nodes specified or invalid format"
            }, status=400)

        # Trim workflow to include only nodes needed for targets
        trimmed_workflow = trim_workflow(workflow, target_node_ids)

        # Calculate image depths for sorting
        current_image_depths = get_image_depths(trimmed_workflow)

        # Save trimmed workflow to temp file
        temp_workflow = PROJECT_ROOT / "temp_workflow_trimmed.json"
        with open(temp_workflow, 'w') as f:
            json.dump(trimmed_workflow, f, indent=2)

        # Find input images (same as regular queue)
        input_images = find_input_images(trimmed_workflow)

        # Call send-to-runpod script
        script_path = PROJECT_ROOT / "scripts" / "send-to-runpod.py"
        log_file = PROJECT_ROOT / "send-to-runpod.log"

        cmd = ['python3', str(script_path), '--workflow', str(temp_workflow), '--no-open']
        if input_images:
            cmd.extend(['--images'] + input_images)

        with open(log_file, 'a') as log:
            subprocess.Popen(
                cmd,
                stdout=log,
                stderr=log,
                cwd=str(PROJECT_ROOT)
            )

        num_nodes = len(trimmed_workflow)
        total_nodes = len(workflow)
        num_targets = len(target_node_ids)
        target_label = f"{num_targets} SaveImage node{'s' if num_targets > 1 else ''}"
        message = f"Trimmed workflow to {num_nodes}/{total_nodes} nodes. Running to {target_label}..."

        return web.json_response({
            "status": "submitted",
            "message": message,
            "nodes_included": num_nodes,
            "total_nodes": total_nodes,
            "target_node_ids": target_node_ids,
            "num_targets": num_targets
        })

    except Exception as e:
        import traceback
        return web.json_response({
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }, status=500)
```

**Testing:**
- Test with single valid target node ID
- Test with multiple valid target node IDs
- Test with invalid target node ID
- Test with empty target_node_ids list
- Test with non-list target_node_ids
- Test with nodes at start of workflow
- Test with nodes at end of workflow
- Test with nodes from different branches
- Verify trimmed workflow file is created correctly
- Verify send-to-runpod.py receives correct workflow

### Phase 3: Frontend - Node Selection Detection

**Files to modify:**
- `/custom_nodes/runpod-queue/web/runpod_button.js`

**Implementation:**

1. **Detect selected nodes in ComfyUI**
   - ComfyUI stores selected nodes in `app.canvas.selected_nodes`
   - This is an object where keys are node IDs and values are node objects
   - Need to handle both single and multiple selections

2. **Add helper function to get selected SaveImage nodes:**
```javascript
function getSelectedSaveImageNodes() {
    const selected = app.canvas.selected_nodes;
    if (!selected || Object.keys(selected).length === 0) {
        return [];
    }

    // Get workflow to check node types
    const workflow = app.graph._nodes_by_id;

    // Collect all selected SaveImage nodes
    const saveImageNodes = [];
    for (const nodeId in selected) {
        const node = workflow[nodeId];
        if (node && node.type === 'SaveImage') {
            saveImageNodes.push({
                id: nodeId,
                node: node
            });
        }
    }

    return saveImageNodes;
}
```

**Testing:**
- Select a SaveImage node in ComfyUI and verify it's detected
- Select multiple SaveImage nodes and verify all are detected
- Select a non-SaveImage node and verify empty array is returned
- Test with mixed selection (SaveImage + other nodes) and verify only SaveImage returned
- Test with no selection and verify empty array is returned

### Phase 4: Frontend - "Run to Selected" Button

**Files to modify:**
- `/custom_nodes/runpod-queue/web/runpod_button.js`

**Implementation:**

1. **Create "Run to Selected" button** next to existing buttons
2. **Button styling:**
   - Similar to "Queue on RunPod" but different color (e.g., orange)
   - Positioned between "Min Workers" and "Queue on RunPod"
3. **Button behavior:**
   - Disabled if no SaveImage nodes are selected (gray out)
   - Enabled when one or more SaveImage nodes are selected
   - Button text updates to show count: "Run to Selected (N)" where N is count of SaveImage nodes
   - On click:
     - Get all selected SaveImage node IDs
     - Get current workflow
     - Send to `/runpod/queue_to_selected` endpoint with array of node IDs
     - Show loading state
     - Poll for results (same as regular queue)
     - Display results in overlay

**Button creation code:**
```javascript
// Create "Run to Selected" button
const runToSelectedBtn = document.createElement("button");
runToSelectedBtn.id = "runpod-run-to-selected-button";
runToSelectedBtn.textContent = "Run to Selected";
runToSelectedBtn.style.marginLeft = "5px";
runToSelectedBtn.style.backgroundColor = "#FF9800";  // Orange
runToSelectedBtn.style.color = "white";
runToSelectedBtn.style.padding = "8px 16px";
runToSelectedBtn.style.border = "none";
runToSelectedBtn.style.borderRadius = "4px";
runToSelectedBtn.style.cursor = "pointer";
runToSelectedBtn.style.fontWeight = "500";

// Function to update button state based on selection
const updateRunToSelectedButton = () => {
    const selectedNodes = getSelectedSaveImageNodes();
    const count = selectedNodes.length;

    if (count > 0) {
        runToSelectedBtn.disabled = false;
        runToSelectedBtn.style.backgroundColor = "#FF9800";
        runToSelectedBtn.style.cursor = "pointer";
        runToSelectedBtn.textContent = `Run to Selected (${count})`;
        runToSelectedBtn.title = `Run workflow up to ${count} selected SaveImage node${count > 1 ? 's' : ''}`;
    } else {
        runToSelectedBtn.disabled = true;
        runToSelectedBtn.style.backgroundColor = "#888";
        runToSelectedBtn.style.cursor = "not-allowed";
        runToSelectedBtn.textContent = "Run to Selected";
        runToSelectedBtn.title = "Select SaveImage node(s) to enable";
    }
};

// Button click handler
runToSelectedBtn.onclick = async () => {
    const selectedNodes = getSelectedSaveImageNodes();

    if (selectedNodes.length === 0) {
        alert("Please select at least one SaveImage node first");
        return;
    }

    try {
        // Disable button while processing
        runToSelectedBtn.disabled = true;
        runToSelectedBtn.textContent = "Trimming...";
        runToSelectedBtn.style.backgroundColor = "#888";

        // Get current workflow
        const prompt = await app.graphToPrompt();
        const workflow = prompt.output;

        // Extract node IDs
        const targetNodeIds = selectedNodes.map(n => n.id);
        console.log(`Running workflow to ${targetNodeIds.length} node(s):`, targetNodeIds);

        // Send to RunPod endpoint
        const response = await fetch('/runpod/queue_to_selected', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                workflow: workflow,
                target_node_ids: targetNodeIds
            })
        });

        const result = await response.json();

        if (!response.ok || result.status === 'error') {
            // Show error (reuse existing error display logic)
            alert(`Error: ${result.message}`);
            runToSelectedBtn.disabled = false;
            runToSelectedBtn.textContent = "Run to Selected";
            updateRunToSelectedButton();
            return;
        }

        // Success - show message and start polling
        runToSelectedBtn.textContent = `Processing (${result.nodes_included}/${result.total_nodes} nodes)...`;

        // Poll for results (reuse existing polling logic from Queue on RunPod)
        // ... (implementation similar to regular queue button)

    } catch (error) {
        console.error('Run to Selected error:', error);
        alert('Failed to run workflow: ' + error.message);
        runToSelectedBtn.disabled = false;
        runToSelectedBtn.textContent = "Run to Selected";
        updateRunToSelectedButton();
    }
};

// Update button state periodically (ComfyUI doesn't have selection change events)
setInterval(updateRunToSelectedButton, 500);

// Initial state
updateRunToSelectedButton();

// Add button to container (between worker toggle and queue button)
container.insertBefore(runToSelectedBtn, runpodBtn);
```

**Testing:**
- Load ComfyUI and verify button appears in correct position (between Min Workers and Queue on RunPod)
- Verify button is disabled and shows "Run to Selected" when no node is selected
- Select a non-SaveImage node and verify button stays disabled
- Select one SaveImage node and verify button shows "Run to Selected (1)"
- Select two SaveImage nodes and verify button shows "Run to Selected (2)"
- Select mixed nodes (1 SaveImage + 1 other) and verify button shows "Run to Selected (1)"
- Click button with single selection and verify workflow is trimmed and submitted
- Click button with multiple selection and verify workflow includes union of dependencies
- Verify results polling and display works correctly

### Phase 5: Error Handling and Edge Cases

**Implementation:**

1. **Backend error handling:**
   - Invalid target node ID (doesn't exist in workflow)
   - Circular dependencies (shouldn't happen, but check)
   - Empty workflow

2. **Frontend error handling:**
   - No SaveImage nodes selected (button disabled)
   - Only non-SaveImage nodes selected (button disabled)
   - Network errors
   - Timeout errors

3. **User feedback:**
   - Button shows count of selected SaveImage nodes: "Run to Selected (N)"
   - Show how many nodes will be executed (e.g., "Running 5/10 nodes")
   - Message indicates number of target nodes (e.g., "Running to 2 SaveImage nodes")
   - Button clearly indicates SaveImage requirement when disabled

**Edge Cases:**

| Case | Behavior |
|------|----------|
| No node selected | Button disabled, shows "Run to Selected", tooltip says "Select SaveImage node(s) to enable" |
| One SaveImage node selected | Button enabled, shows "Run to Selected (1)", execute normally |
| Multiple SaveImage nodes selected | Button enabled, shows "Run to Selected (N)", execute union of dependencies |
| Non-SaveImage node selected | Button disabled (requirement not met) |
| Mixed selection (SaveImage + other) | Button enabled with count of SaveImage nodes only |
| Multiple SaveImage from same branch | Works normally, deduplicated dependency tree |
| Multiple SaveImage from different branches | Both branches execute (union of trees) |
| Invalid node ID in backend | Backend returns 400 error with clear message |
| Circular dependency | Backend detects and returns error (shouldn't happen) |
| Network timeout | Frontend shows timeout error after 5 minutes |

**Testing:**
- Test all edge cases listed above
- Test with complex workflows (20+ nodes)
- Test with branching workflows (select SaveImage from each branch)
- Test with convergent workflows (branches that merge)
- Test rapid clicking (prevent double submission)
- Test selecting all SaveImage nodes (should execute full workflow)
- Test selecting SaveImage nodes in different order (result should be same)

### Phase 6: Persistent Image Display (Enhancement)

**Overview:**
Allow users to view the last workflow results without re-running. Adds a "View Last Results" button that reopens the image overlay using filenames stored in memory.

**Files to modify:**
- `/custom_nodes/runpod-queue/web/runpod_button.js`

**Implementation:**

1. **Store last results globally (just filenames):**
```javascript
// At top of extension setup, before addButton()
let lastRunpodResults = null;  // Stores {filenames: ["img1.png", ...], source: "queue"|"selected"}
```

2. **Create "View Last Results" button:**
```javascript
const viewResultsBtn = document.createElement("button");
viewResultsBtn.id = "runpod-view-results-button";
viewResultsBtn.textContent = "View Last Results";
viewResultsBtn.style.marginLeft = "5px";
viewResultsBtn.style.backgroundColor = "#9C27B0";  // Purple
viewResultsBtn.style.color = "white";
viewResultsBtn.style.padding = "8px 16px";
viewResultsBtn.style.border = "none";
viewResultsBtn.style.borderRadius = "4px";
viewResultsBtn.style.cursor = "pointer";
viewResultsBtn.style.fontWeight = "500";
viewResultsBtn.disabled = true;  // Initially disabled
viewResultsBtn.title = "No results yet - run a workflow first";

// Add to container (after Run to Selected, before Queue on RunPod)
container.insertBefore(viewResultsBtn, runpodBtn);
```

3. **Extract overlay display logic into reusable function:**
```javascript
function showImageOverlay(images, title) {
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.95);
        z-index: 10000;
        overflow: auto;
        padding: 20px;
        box-sizing: border-box;
    `;

    overlay.innerHTML = `
        <div style="max-width: 1200px; margin: 0 auto;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h1 style="color: #4CAF50; margin: 0;">${title}</h1>
                <button id="runpod-close-overlay" style="
                    background: #f44336;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 16px;
                    font-weight: 500;
                ">Close</button>
            </div>
            ${images.map(img => `
                <div style="margin: 20px 0; background: #2a2a2a; padding: 15px; border-radius: 8px;">
                    <div style="color: #888; font-size: 14px; margin-bottom: 10px;">${img.filename}</div>
                    <img src="${img.url}" alt="${img.filename}" style="
                        max-width: 512px;
                        width: 100%;
                        height: auto;
                        display: block;
                        border-radius: 4px;
                    ">
                </div>
            `).join('')}
        </div>
    `;

    document.body.appendChild(overlay);

    // Close button handler
    document.getElementById('runpod-close-overlay').onclick = () => {
        document.body.removeChild(overlay);
    };

    // Close on escape key
    const escapeHandler = (e) => {
        if (e.key === 'Escape' && document.body.contains(overlay)) {
            document.body.removeChild(overlay);
            document.removeEventListener('keydown', escapeHandler);
        }
    };
    document.addEventListener('keydown', escapeHandler);
}
```

4. **Update both "Queue on RunPod" and "Run to Selected" to save results:**
```javascript
// In polling success callback (both buttons), after detecting new images:
const newImages = imagesData.images
    .filter(img => img.modified > submissionTime)
    .sort((a, b) => b.depth - a.depth);

// Save just the filenames (images are already in output/ directory)
lastRunpodResults = {
    filenames: newImages.map(img => img.filename),
    source: "queue"  // or "selected" for Run to Selected button
};

// Enable view results button
viewResultsBtn.disabled = false;
viewResultsBtn.title = `View ${newImages.length} image(s) from last run`;

// Show overlay (refactored to use extracted function)
showImageOverlay(newImages, `✓ RunPod Results (${newImages.length} image${newImages.length !== 1 ? 's' : ''})`);
```

5. **View Results button click handler:**
```javascript
viewResultsBtn.onclick = () => {
    if (!lastRunpodResults || lastRunpodResults.filenames.length === 0) {
        alert("No results available. Run a workflow first.");
        return;
    }

    // Reconstruct image objects from filenames
    // Images are served by ComfyUI from output/ via /view endpoint
    const images = lastRunpodResults.filenames.map(filename => ({
        filename: filename,
        url: `/view?filename=${filename}`
    }));

    const source = lastRunpodResults.source === "selected" ? "Selected Nodes" : "Full Workflow";
    showImageOverlay(
        images,
        `✓ Last Results - ${source} (${images.length} image${images.length !== 1 ? 's' : ''})`
    );
};
```

**Button positioning:**
```
[Min Workers: 1] [Run to Selected (2)] [View Last Results] [Queue on RunPod]
```

**How it works:**
1. Images are saved to `output/` directory by RunPod workflow (existing behavior)
2. Frontend stores just the filenames in `lastRunpodResults`
3. When "View Last Results" is clicked, reconstruct URLs using `/view?filename=...`
4. ComfyUI serves images from `output/` directory (existing ComfyUI feature)

**Benefits:**
- Minimal memory usage (just filename strings)
- No need to re-run workflow to see results
- Works for both "Queue on RunPod" and "Run to Selected"
- Images accessible as long as they exist in `output/` directory
- Simple implementation

**Testing:**
- Verify button is initially disabled
- Run "Queue on RunPod", verify button becomes enabled
- Close overlay, click "View Last Results", verify same images shown
- Run "Run to Selected", verify button updates with new results
- Close and reopen multiple times, verify images still load
- Refresh page, verify button resets to disabled (no persistence across page loads)
- Delete images from output/, verify "View Last Results" shows broken images (expected behavior)

## Technical Details

### ComfyUI Selection API

ComfyUI stores selected nodes in:
```javascript
app.canvas.selected_nodes  // Object: {node_id: node_object}
```

When a node is selected:
- Single click: Selects one node
- Ctrl+click: Multi-select
- Drag selection box: Multi-select

### Workflow Node Reference Format

Nodes reference other nodes via:
```json
{
  "inputs": {
    "model": ["1", 0],  // [node_id, output_slot]
    "text": "some value"  // Simple value (not a reference)
  }
}
```

Algorithm must check if input value is:
- `list` with length ≥ 2 where `[0]` is a node ID string

### Data Structures

**Request payload:**
```json
{
  "workflow": { /* full workflow dict */ },
  "target_node_ids": ["5", "8"]
}
```

**Response (single target):**
```json
{
  "status": "submitted",
  "message": "Trimmed workflow to 5/10 nodes. Running to 1 SaveImage node...",
  "nodes_included": 5,
  "total_nodes": 10,
  "target_node_ids": ["5"],
  "num_targets": 1
}
```

**Response (multiple targets):**
```json
{
  "status": "submitted",
  "message": "Trimmed workflow to 8/10 nodes. Running to 2 SaveImage nodes...",
  "nodes_included": 8,
  "total_nodes": 10,
  "target_node_ids": ["5", "8"],
  "num_targets": 2
}
```

**Error response:**
```json
{
  "status": "error",
  "message": "Node '99' not found in workflow",
  "traceback": "..."
}
```

## Alternatives Considered

### Alternative 1: Allow Any Node Type

**Approach:** Allow selecting any node, not just SaveImage nodes

**Pros:**
- More flexible
- Could be useful for debugging intermediate steps

**Cons:**
- No output would be saved (defeats the purpose)
- Confusing user experience (workflow executes but nothing to show)
- Would need complex warning system

**Verdict:** Not chosen - require SaveImage nodes for clear, useful output

### Alternative 2: Mute/Bypass Nodes Instead of Trimming

**Approach:** Use ComfyUI's mute feature to disable nodes instead of removing them

**Pros:**
- Preserves full workflow structure
- Easier to understand what was skipped

**Cons:**
- ComfyUI API format doesn't include mute status
- Would need to modify how workflows are sent to RunPod
- More complex to implement

**Verdict:** Not chosen - trimming is cleaner and doesn't require API changes

### Alternative 3: Auto-detect Closest SaveImage

**Approach:** If non-SaveImage selected, find and use nearest downstream SaveImage

**Pros:**
- More user-friendly (any selection works)
- Could be intuitive for some workflows

**Cons:**
- Ambiguous which SaveImage to choose
- Changes user's intent
- More complex logic
- Confusing if unexpected SaveImage is used

**Verdict:** Not chosen - require explicit SaveImage selection for clarity

### Alternative 4: Separate Workflows Per Target

**Approach:** Send multiple separate workflows to RunPod (one per selected SaveImage)

**Pros:**
- Simpler logic (no need to union dependency trees)
- Could run in parallel on RunPod

**Cons:**
- Inefficient (duplicate execution of shared dependencies)
- More expensive (runs same nodes multiple times)
- Multiple API calls needed
- Results harder to track

**Verdict:** Not chosen - union approach is more efficient and matches user intent

## Integration Points

1. **Existing queue endpoint:** Shares code for finding input images, polling, display
2. **send-to-runpod.py:** Reused without modification
3. **Image polling system:** Reused from existing implementation
4. **Error display:** Reused overlay system

## Future Enhancements

1. **Saved Selections:** Remember common target nodes for quick access
2. **Multi-target:** Run to multiple selected nodes (multiple trimmed workflows)
3. **Visual Preview:** Highlight which nodes will be executed before running
4. **Dry Run:** Show trimmed workflow without executing
5. **Diff View:** Show which nodes are excluded
6. **Hotkeys:** Keyboard shortcuts (e.g., Ctrl+Shift+R for run to selected)

## Implementation Progress

### Phase 1: Backend - Workflow Trimming Function
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 2: Backend - API Route for Run to Selected
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 3: Frontend - Node Selection Detection
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 4: Frontend - "Run to Selected" Button
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 5: Error Handling and Edge Cases
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 6: Persistent Image Display (Enhancement)
- [ ] Implementation Complete
- [ ] Testing Complete
