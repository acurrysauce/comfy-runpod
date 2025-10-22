import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Add RunPod queue button to ComfyUI
app.registerExtension({
    name: "RunPod.QueueButton",

    async setup() {
        try {
            console.log("RunPod extension setup starting...");

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

                                            // Create overlay to display images
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
                                                        <h1 style="color: #4CAF50; margin: 0;">✓ RunPod Results (${newImages.length} image${newImages.length !== 1 ? 's' : ''})</h1>
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
                                                    ${newImages.map(img => `
                                                        <div style="
                                                            margin: 20px 0;
                                                            background: #2a2a2a;
                                                            padding: 15px;
                                                            border-radius: 8px;
                                                        ">
                                                            <div style="
                                                                color: #888;
                                                                font-size: 14px;
                                                                margin-bottom: 10px;
                                                            ">${img.filename}</div>
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

                                            // Add overlay to page
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

                console.log("RunPod Queue button added to interface");
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
