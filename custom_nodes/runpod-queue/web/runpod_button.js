import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Add RunPod queue button to ComfyUI
app.registerExtension({
    name: "RunPod.QueueButton",

    async setup() {
        try {
            console.log("RunPod extension setup starting...");

            // Store last results globally (just filenames)
            let lastRunpodResults = null;  // {filenames: [...], source: "queue"|"selected"}

            // Shared function to display image overlay
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

            // Wait for DOM to be ready
            const addButton = () => {
                // Find the action bar (top right buttons in new UI)
                let container = document.querySelector(".action-bar");

                // Fallback: find queue button and add next to it
                if (!container) {
                    const queueBtn = document.querySelector('[data-testid="queue-button"]');
                    if (queueBtn) {
                        container = queueBtn.parentElement;
                    }
                }

                // Another fallback: look for workflow-tabs header
                if (!container) {
                    container = document.querySelector(".workflow-tabs-header");
                }

                // Try the old menu as last resort
                if (!container) {
                    container = document.querySelector(".comfy-menu");
                }

                if (!container) {
                    console.warn("RunPod: Could not find container element, will retry...");
                    return false;
                }

                console.log("RunPod: Found container element:", container);

                // Create RunPod button
                const runpodBtn = document.createElement("button");
                runpodBtn.id = "runpod-queue-button";
                runpodBtn.textContent = "Queue on RunPod";
                runpodBtn.style.marginLeft = "5px";
                runpodBtn.style.backgroundColor = "#4CAF50";
                runpodBtn.style.color = "white";
                runpodBtn.style.padding = "8px 16px";
                runpodBtn.style.border = "none";
                runpodBtn.style.borderRadius = "4px";
                runpodBtn.style.cursor = "pointer";
                runpodBtn.style.fontWeight = "500";

                runpodBtn.onclick = async () => {
                    try {
                        // Disable button while processing
                        runpodBtn.disabled = true;
                        runpodBtn.textContent = "Submitting...";
                        runpodBtn.style.backgroundColor = "#888";

                        // Get current workflow in API format (same as Queue Prompt button)
                        const prompt = await app.graphToPrompt();
                        const workflow = prompt.output;

                        console.log("Submitting workflow to RunPod:", workflow);

                        // Send to RunPod endpoint
                        const response = await fetch('/runpod/queue', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                workflow: workflow
                            })
                        });

                        const result = await response.json();

                        if (!response.ok || result.status === 'error') {
                            // Show detailed error message
                            const errorMsg = result.message || 'Unknown error';
                            const errorDetails = result.details || result.traceback || '';

                            // Create error overlay
                            const errorOverlay = document.createElement('div');
                            errorOverlay.style.cssText = `
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

                            errorOverlay.innerHTML = `
                                <div style="max-width: 1200px; margin: 0 auto;">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                                        <h1 style="color: #f44336; margin: 0;">✗ Workflow Error</h1>
                                        <button id="runpod-close-error" style="
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
                                    <div style="
                                        background: #2a2a2a;
                                        padding: 20px;
                                        border-radius: 8px;
                                        margin-bottom: 20px;
                                    ">
                                        <h2 style="color: #fff; margin-top: 0;">Error Message:</h2>
                                        <pre style="
                                            color: #f44336;
                                            white-space: pre-wrap;
                                            word-wrap: break-word;
                                            font-family: monospace;
                                            font-size: 14px;
                                        ">${errorMsg}</pre>
                                    </div>
                                    ${errorDetails ? `
                                        <div style="
                                            background: #2a2a2a;
                                            padding: 20px;
                                            border-radius: 8px;
                                        ">
                                            <h2 style="color: #fff; margin-top: 0;">Details:</h2>
                                            <pre style="
                                                color: #888;
                                                white-space: pre-wrap;
                                                word-wrap: break-word;
                                                font-family: monospace;
                                                font-size: 12px;
                                                max-height: 400px;
                                                overflow-y: auto;
                                            ">${errorDetails}</pre>
                                        </div>
                                    ` : ''}
                                </div>
                            `;

                            document.body.appendChild(errorOverlay);

                            // Close button handler
                            document.getElementById('runpod-close-error').onclick = () => {
                                document.body.removeChild(errorOverlay);
                            };

                            // Close on escape key
                            const escapeHandler = (e) => {
                                if (e.key === 'Escape' && document.body.contains(errorOverlay)) {
                                    document.body.removeChild(errorOverlay);
                                    document.removeEventListener('keydown', escapeHandler);
                                }
                            };
                            document.addEventListener('keydown', escapeHandler);

                            // Re-enable button
                            runpodBtn.disabled = false;
                            runpodBtn.textContent = "Queue on RunPod";
                            runpodBtn.style.backgroundColor = "#4CAF50";
                            return;
                        }

                        if (result.status === 'submitted') {
                            runpodBtn.textContent = "Processing...";

                            // Record current time - any images modified after this are new
                            const submissionTime = Date.now() / 1000; // Convert to seconds
                            console.log(`RunPod: Workflow submitted at ${submissionTime}`);

                            // Poll for new images
                            const pollInterval = setInterval(async () => {
                                try {
                                    const imagesResponse = await fetch('/runpod/latest_images');
                                    const imagesData = await imagesResponse.json();

                                    console.log(`RunPod: Polling... Latest image time: ${imagesData.images.length > 0 ? imagesData.images[0].modified : 'none'}`);

                                    if (imagesData.images.length > 0) {
                                        const latestImageTime = imagesData.images[0].modified;

                                        // Check if there are new images (modified after submission)
                                        if (latestImageTime > submissionTime) {
                                            console.log('RunPod: New images detected!');
                                            clearInterval(pollInterval);

                                            // Get all new images and sort by node depth (deepest first = final result first)
                                            const newImages = imagesData.images
                                                .filter(img => img.modified > submissionTime)
                                                .sort((a, b) => b.depth - a.depth);  // Reverse: deepest first

                                            console.log('RunPod: Image depths:', newImages.map(img => ({name: img.filename, depth: img.depth})));

                                            // Save results (just filenames)
                                            lastRunpodResults = {
                                                filenames: newImages.map(img => img.filename),
                                                source: "queue"
                                            };

                                            // Enable View Results button
                                            if (typeof enableViewResults === 'function') {
                                                enableViewResults();
                                            }

                                            // Show overlay using shared function
                                            showImageOverlay(newImages, `✓ RunPod Results (${newImages.length} image${newImages.length !== 1 ? 's' : ''})`);

                                            // Re-enable button
                                            runpodBtn.disabled = false;
                                            runpodBtn.textContent = "Queue on RunPod";
                                            runpodBtn.style.backgroundColor = "#4CAF50";
                                        }
                                    }
                                } catch (err) {
                                    console.error('Error polling for images:', err);
                                    clearInterval(pollInterval);
                                    runpodBtn.disabled = false;
                                    runpodBtn.textContent = "Queue on RunPod";
                                    runpodBtn.style.backgroundColor = "#4CAF50";
                                }
                            }, 3000); // Poll every 3 seconds

                            // Timeout after 5 minutes
                            setTimeout(() => {
                                clearInterval(pollInterval);
                                runpodBtn.disabled = false;
                                runpodBtn.textContent = "Queue on RunPod";
                                runpodBtn.style.backgroundColor = "#4CAF50";
                            }, 300000);
                        } else {
                            alert('✗ Error: ' + result.message);
                            runpodBtn.disabled = false;
                            runpodBtn.textContent = "Queue on RunPod";
                            runpodBtn.style.backgroundColor = "#4CAF50";
                        }

                    } catch (error) {
                        console.error('RunPod queue error:', error);
                        alert('✗ Failed to submit to RunPod: ' + error.message);
                        runpodBtn.disabled = false;
                        runpodBtn.textContent = "Queue on RunPod";
                        runpodBtn.style.backgroundColor = "#4CAF50";
                    }
                };

                // Append button to container
                container.appendChild(runpodBtn);

                // Create worker status toggle button
                const workerBtn = document.createElement("button");
                workerBtn.id = "runpod-worker-toggle";
                workerBtn.textContent = "Min Workers: Loading...";
                workerBtn.style.marginLeft = "5px";
                workerBtn.style.backgroundColor = "#2196F3";
                workerBtn.style.color = "white";
                workerBtn.style.padding = "8px 16px";
                workerBtn.style.border = "none";
                workerBtn.style.borderRadius = "4px";
                workerBtn.style.cursor = "pointer";
                workerBtn.style.fontWeight = "500";

                // Function to update worker status display
                const updateWorkerStatus = async () => {
                    try {
                        const response = await fetch('/runpod/worker_status');
                        const data = await response.json();

                        if (data.status === 'success') {
                            const workersMin = data.workers_min;
                            if (workersMin === 0) {
                                workerBtn.textContent = "Min Workers: 0 💤";
                                workerBtn.style.backgroundColor = "#757575"; // Gray for cost-saving
                                workerBtn.title = "Cost-saving mode (slow cold starts)\nClick to enable always-on worker";
                            } else {
                                workerBtn.textContent = "Min Workers: 1 ⚡";
                                workerBtn.style.backgroundColor = "#4CAF50"; // Green for always-ready
                                workerBtn.title = "Always-ready mode (instant response)\nClick to disable for cost savings";
                            }
                        } else {
                            workerBtn.textContent = "Min Workers: Error";
                            workerBtn.style.backgroundColor = "#f44336";
                            workerBtn.title = data.message || "Failed to get worker status";
                        }
                    } catch (error) {
                        console.error('Error getting worker status:', error);
                        workerBtn.textContent = "Min Workers: Error";
                        workerBtn.style.backgroundColor = "#f44336";
                        workerBtn.title = "Failed to get worker status: " + error.message;
                    }
                };

                // Toggle worker on click
                workerBtn.onclick = async () => {
                    try {
                        // Disable button while processing
                        workerBtn.disabled = true;
                        const originalText = workerBtn.textContent;
                        workerBtn.textContent = "Toggling...";
                        workerBtn.style.backgroundColor = "#888";

                        // Call toggle endpoint
                        const response = await fetch('/runpod/toggle_workers', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            }
                        });

                        const result = await response.json();

                        if (result.status === 'success') {
                            console.log('RunPod: Worker toggle successful:', result.message);
                            // Update display with new status
                            await updateWorkerStatus();
                        } else {
                            alert('✗ Error toggling workers: ' + result.message);
                            workerBtn.textContent = originalText;
                        }

                        // Re-enable button
                        workerBtn.disabled = false;

                    } catch (error) {
                        console.error('RunPod worker toggle error:', error);
                        alert('✗ Failed to toggle workers: ' + error.message);
                        workerBtn.disabled = false;
                        await updateWorkerStatus(); // Try to restore correct state
                    }
                };

                // Append worker button to container
                container.appendChild(workerBtn);

                // Load initial worker status
                updateWorkerStatus();

                // Helper function to get selected SaveImage nodes
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

                // Button click handler - similar to Queue on RunPod but sends to different endpoint
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
                            // Show detailed error message
                            const errorMsg = result.message || 'Unknown error';
                            const errorDetails = result.details || result.traceback || '';

                            // Reuse error overlay pattern from Queue on RunPod
                            alert(`Error: ${errorMsg}\n\n${errorDetails ? 'See console for details' : ''}`);
                            if (errorDetails) {
                                console.error('RunPod error details:', errorDetails);
                            }

                            runToSelectedBtn.disabled = false;
                            runToSelectedBtn.textContent = "Run to Selected";
                            updateRunToSelectedButton();
                            return;
                        }

                        // Success - show message and start polling (reuse polling logic from Queue on RunPod)
                        runToSelectedBtn.textContent = `Processing (${result.nodes_included}/${result.total_nodes} nodes)...`;

                        // Record current time - any images modified after this are new
                        const submissionTime = Date.now() / 1000; // Convert to seconds
                        console.log(`RunPod: Trimmed workflow submitted at ${submissionTime}`);
                        console.log(`RunPod: Running to ${result.num_targets} SaveImage node(s)`);

                        // Poll for new images (same pattern as Queue on RunPod)
                        const pollInterval = setInterval(async () => {
                            try {
                                const imagesResponse = await fetch('/runpod/latest_images');
                                const imagesData = await imagesResponse.json();

                                if (imagesData.images.length > 0) {
                                    const latestImageTime = imagesData.images[0].modified;

                                    // Check if there are new images (modified after submission)
                                    if (latestImageTime > submissionTime) {
                                        console.log('RunPod: New images detected!');
                                        clearInterval(pollInterval);

                                        // Get all new images and sort by node depth (deepest first = final result first)
                                        const newImages = imagesData.images
                                            .filter(img => img.modified > submissionTime)
                                            .sort((a, b) => b.depth - a.depth);

                                        // Save results (just filenames)
                                        lastRunpodResults = {
                                            filenames: newImages.map(img => img.filename),
                                            source: "selected"
                                        };

                                        // Enable View Results button
                                        if (typeof enableViewResults === 'function') {
                                            enableViewResults();
                                        }

                                        // Show overlay using shared function
                                        showImageOverlay(newImages, `✓ RunPod Results (${newImages.length} image${newImages.length !== 1 ? 's' : ''})`);

                                        // Re-enable button
                                        runToSelectedBtn.disabled = false;
                                        updateRunToSelectedButton();
                                    }
                                }
                            } catch (err) {
                                console.error('Error polling for images:', err);
                                clearInterval(pollInterval);
                                runToSelectedBtn.disabled = false;
                                updateRunToSelectedButton();
                            }
                        }, 3000); // Poll every 3 seconds

                        // Timeout after 5 minutes
                        setTimeout(() => {
                            clearInterval(pollInterval);
                            runToSelectedBtn.disabled = false;
                            updateRunToSelectedButton();
                        }, 300000);

                    } catch (error) {
                        console.error('Run to Selected error:', error);
                        alert('✗ Failed to run workflow: ' + error.message);
                        runToSelectedBtn.disabled = false;
                        updateRunToSelectedButton();
                    }
                };

                // Append Run to Selected button to container (before Queue on RunPod)
                container.insertBefore(runToSelectedBtn, runpodBtn);

                // Update button state periodically (ComfyUI doesn't have selection change events)
                setInterval(updateRunToSelectedButton, 500);

                // Initial state
                updateRunToSelectedButton();

                // Create "View Last Results" button
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

                // View Results button click handler
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

                // Function to enable View Results button (called after workflow completes)
                const enableViewResults = () => {
                    if (lastRunpodResults && lastRunpodResults.filenames.length > 0) {
                        viewResultsBtn.disabled = false;
                        viewResultsBtn.style.backgroundColor = "#9C27B0";
                        viewResultsBtn.style.cursor = "pointer";
                        viewResultsBtn.title = `View ${lastRunpodResults.filenames.length} image(s) from last run`;
                    }
                };

                // Append View Results button to container (before Queue on RunPod)
                container.insertBefore(viewResultsBtn, runpodBtn);

                console.log("RunPod Queue button, Worker Toggle, Run to Selected, and View Last Results added to interface");
                return true;
            };

            // Try to add button immediately
            if (!addButton()) {
                // If it failed, retry after a delay
                setTimeout(() => {
                    if (!addButton()) {
                        // Final retry after longer delay
                        setTimeout(addButton, 2000);
                    }
                }, 500);
            }

        } catch (error) {
            console.error("RunPod extension setup error:", error);
        }
    }
});
