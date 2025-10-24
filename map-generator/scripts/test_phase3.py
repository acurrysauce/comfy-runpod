#!/usr/bin/env python3
"""
Test Phase 3 image processing functions.

Creates test images and validates:
- extract_bottom_1x2() correctly crops 2048x2048 → 2048x1024
- composite_accumulated_grid() correctly pastes rows
- save_iteration_outputs() creates correct directory structure
"""

import tempfile
from pathlib import Path
from PIL import Image, ImageDraw

# Import the functions we're testing
from extend_texture_down import (
    extract_bottom_1x2,
    composite_accumulated_grid,
    save_iteration_outputs
)


def create_test_image_2x2():
    """Create a 2048x2048 test image with distinguishable top/bottom halves."""
    img = Image.new('RGB', (2048, 2048))
    draw = ImageDraw.Draw(img)

    # Top half: red
    draw.rectangle([(0, 0), (2048, 1024)], fill=(255, 0, 0))

    # Bottom half: blue
    draw.rectangle([(0, 1024), (2048, 2048)], fill=(0, 0, 255))

    return img


def create_test_image_1x2(color):
    """Create a 2048x1024 test image with a single color."""
    img = Image.new('RGB', (2048, 1024), color)
    return img


def test_extract_bottom_1x2():
    """Test extract_bottom_1x2() function."""
    print("Testing extract_bottom_1x2()...")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test image
        test_img = create_test_image_2x2()
        test_path = Path(tmpdir) / "test_2x2.png"
        test_img.save(test_path)

        # Extract bottom 1x2
        bottom_1x2 = extract_bottom_1x2(test_path)

        # Verify dimensions
        assert bottom_1x2.size == (2048, 1024), f"Expected (2048, 1024), got {bottom_1x2.size}"

        # Verify it's the blue half (bottom)
        pixel = bottom_1x2.getpixel((1024, 512))
        assert pixel == (0, 0, 255), f"Expected blue pixel (0, 0, 255), got {pixel}"

        print("  ✓ Correctly extracts bottom 1024 pixels from 2048x2048 image")
        print("  ✓ Output dimensions: 2048x1024")


def test_composite_accumulated_grid():
    """Test composite_accumulated_grid() function."""
    print("\nTesting composite_accumulated_grid()...")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create previous grid (red, 2048x1024)
        previous_grid = create_test_image_1x2((255, 0, 0))
        previous_path = Path(tmpdir) / "previous.png"
        previous_grid.save(previous_path)

        # Create new row (blue, 2048x1024)
        new_row = create_test_image_1x2((0, 0, 255))

        # Composite
        accumulated = composite_accumulated_grid(previous_path, new_row)

        # Verify dimensions
        assert accumulated.size == (2048, 2048), f"Expected (2048, 2048), got {accumulated.size}"

        # Verify top half is red (previous grid)
        top_pixel = accumulated.getpixel((1024, 512))
        assert top_pixel == (255, 0, 0), f"Expected red pixel at top, got {top_pixel}"

        # Verify bottom half is blue (new row)
        bottom_pixel = accumulated.getpixel((1024, 1536))
        assert bottom_pixel == (0, 0, 255), f"Expected blue pixel at bottom, got {bottom_pixel}"

        print("  ✓ Correctly composites new row onto previous grid")
        print("  ✓ Output dimensions: 2048x2048 (from 2048x1024 + 2048x1024)")

        # Test with taller previous grid (2048x2048)
        taller_previous = create_test_image_1x2((0, 255, 0))
        taller_previous = taller_previous.resize((2048, 2048))
        taller_path = Path(tmpdir) / "taller_previous.png"
        taller_previous.save(taller_path)

        # Composite another row
        accumulated2 = composite_accumulated_grid(taller_path, new_row)

        # Verify dimensions
        assert accumulated2.size == (2048, 3072), f"Expected (2048, 3072), got {accumulated2.size}"
        print("  ✓ Correctly handles taller grids (2048x2048 + 2048x1024 → 2048x3072)")


def test_save_iteration_outputs():
    """Test save_iteration_outputs() function."""
    print("\nTesting save_iteration_outputs()...")

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "test_output"

        # Create test images
        workflow_2x2 = create_test_image_2x2()
        accumulated = create_test_image_1x2((0, 255, 0))
        accumulated = accumulated.resize((2048, 2048))
        next_input = create_test_image_1x2((0, 0, 255))

        # Save iteration 0
        paths = save_iteration_outputs(0, workflow_2x2, accumulated, next_input, output_dir)

        # Verify directory created
        iter_dir = output_dir / "iteration_0"
        assert iter_dir.exists(), "iteration_0 directory not created"

        # Verify all three files exist
        assert paths['workflow_2x2'].exists(), "workflow_output_2x2.png not created"
        assert paths['accumulated'].exists(), "accumulated_grid.png not created"
        assert paths['next_input'].exists(), "next_input_1x2.png not created"

        # Verify file dimensions
        workflow_img = Image.open(paths['workflow_2x2'])
        assert workflow_img.size == (2048, 2048), "workflow_2x2 wrong size"

        accumulated_img = Image.open(paths['accumulated'])
        assert accumulated_img.size == (2048, 2048), "accumulated wrong size"

        next_input_img = Image.open(paths['next_input'])
        assert next_input_img.size == (2048, 1024), "next_input wrong size"

        print("  ✓ Creates iteration_N directory")
        print("  ✓ Saves all three output files")
        print("  ✓ Files have correct dimensions")


if __name__ == "__main__":
    print("Running Phase 3 image processing tests...\n")

    try:
        test_extract_bottom_1x2()
        test_composite_accumulated_grid()
        test_save_iteration_outputs()

        print("\n✅ All Phase 3 tests passed!")

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
