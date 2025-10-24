"""Test workflow trimming functions for Run to Selected feature."""


def get_node_dependencies(workflow, target_node_id):
    """Recursively find all nodes that target_node_id depends on."""
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
    """Create a trimmed workflow containing only nodes necessary for targets."""
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


def test_linear_workflow():
    """Test with simple linear workflow: 1→2→3→4→5"""
    workflow = {
        "1": {"class_type": "CheckpointLoader", "inputs": {"ckpt_name": "model.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "test", "clip": ["1", 1]}},
        "3": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0]}},
        "4": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["1", 2]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}},
    }

    # Test single node in middle
    result = trim_workflow(workflow, ["3"])
    expected = {"1", "2", "3"}
    assert set(result.keys()) == expected, f"Expected {expected}, got {set(result.keys())}"
    print("✓ Linear workflow - middle node: PASS")

    # Test first node
    result = trim_workflow(workflow, ["1"])
    expected = {"1"}
    assert set(result.keys()) == expected, f"Expected {expected}, got {set(result.keys())}"
    print("✓ Linear workflow - first node: PASS")

    # Test last node
    result = trim_workflow(workflow, ["5"])
    expected = {"1", "2", "3", "4", "5"}
    assert set(result.keys()) == expected, f"Expected {expected}, got {set(result.keys())}"
    print("✓ Linear workflow - last node: PASS")

    # Test multiple nodes (3 and 5)
    result = trim_workflow(workflow, ["3", "5"])
    expected = {"1", "2", "3", "4", "5"}  # Union of dependencies
    assert set(result.keys()) == expected, f"Expected {expected}, got {set(result.keys())}"
    print("✓ Linear workflow - multiple nodes: PASS")


def test_branching_workflow():
    """Test with branching workflow: 1→2→3, 1→4→5"""
    workflow = {
        "1": {"class_type": "CheckpointLoader", "inputs": {"ckpt_name": "model.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "branch A", "clip": ["1", 1]}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},  # Branch A end
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "branch B", "clip": ["1", 1]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}},  # Branch B end
    }

    # Test branch A only
    result = trim_workflow(workflow, ["3"])
    expected = {"1", "2", "3"}
    assert set(result.keys()) == expected, f"Expected {expected}, got {set(result.keys())}"
    print("✓ Branching workflow - branch A only: PASS")

    # Test branch B only
    result = trim_workflow(workflow, ["5"])
    expected = {"1", "4", "5"}
    assert set(result.keys()) == expected, f"Expected {expected}, got {set(result.keys())}"
    print("✓ Branching workflow - branch B only: PASS")

    # Test both branches (union)
    result = trim_workflow(workflow, ["3", "5"])
    expected = {"1", "2", "3", "4", "5"}  # Union of both branches
    assert set(result.keys()) == expected, f"Expected {expected}, got {set(result.keys())}"
    print("✓ Branching workflow - both branches: PASS")


def test_real_workflow():
    """Test with actual workflow format from sample-txt2img.json"""
    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "a beautiful landscape",
                "clip": ["1", 1]
            }
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "blurry",
                "clip": ["1", 1]
            }
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 1024,
                "height": 1024,
                "batch_size": 1
            }
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0]
            }
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2]
            }
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "ComfyUI",
                "images": ["6", 0]
            }
        }
    }

    # Test trimming to SaveImage node (should include all)
    result = trim_workflow(workflow, ["7"])
    expected = {"1", "2", "3", "4", "5", "6", "7"}
    assert set(result.keys()) == expected, f"Expected {expected}, got {set(result.keys())}"
    print("✓ Real workflow - full workflow via SaveImage: PASS")

    # Test trimming to KSampler (should exclude VAEDecode and SaveImage)
    result = trim_workflow(workflow, ["5"])
    expected = {"1", "2", "3", "4", "5"}
    assert set(result.keys()) == expected, f"Expected {expected}, got {set(result.keys())}"
    print("✓ Real workflow - trim to KSampler: PASS")


if __name__ == "__main__":
    print("Testing workflow trimming functions...\n")

    test_linear_workflow()
    print()
    test_branching_workflow()
    print()
    test_real_workflow()

    print("\n✅ All tests passed!")
