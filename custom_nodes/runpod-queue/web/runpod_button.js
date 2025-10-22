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
                            alert('✓ Workflow submitted to RunPod!\n\nYour workflow is being processed on RunPod.\nResults will be saved to: output/\n\nCheck send-to-runpod.log for progress.');
                        } else {
                            alert('✗ Error: ' + result.message);
                        }

                    } catch (error) {
                        console.error('RunPod queue error:', error);
                        alert('✗ Failed to submit to RunPod: ' + error.message);
                    } finally {
                        // Re-enable button
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
