#!/usr/bin/env python3
"""
Model Sync Utility for ComfyUI RunPod Deployment

Automates the process of syncing models from local machine to RunPod network volume.

Workflow:
1. Creates a zip archive of local models directory
2. Uses runpodctl to send the archive
3. Generates an extraction script for the RunPod side
4. Provides instructions for completing the transfer

Usage:
    python scripts/sync-models.py <local_models_dir> [--volume-id VOLUME_ID]
    python scripts/sync-models.py /path/to/models --volume-id my-volume
    python scripts/sync-models.py /path/to/models --dry-run
"""

import argparse
import os
import sys
import subprocess
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Sync models to RunPod network volume using runpodctl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync models directory
  python scripts/sync-models.py /path/to/models

  # Specify volume ID
  python scripts/sync-models.py /path/to/models --volume-id my-volume

  # Dry run (create zip but don't send)
  python scripts/sync-models.py /path/to/models --dry-run

  # Custom zip name
  python scripts/sync-models.py /path/to/models --zip-name my-models.zip
        """
    )

    parser.add_argument(
        "local_dir",
        type=str,
        help="Local directory containing models to sync"
    )

    parser.add_argument(
        "--volume-id",
        type=str,
        help="RunPod network volume ID (for documentation)"
    )

    parser.add_argument(
        "--zip-name",
        type=str,
        default="comfyui-models.zip",
        help="Name for the zip file (default: comfyui-models.zip)"
    )

    parser.add_argument(
        "--target-path",
        type=str,
        default="/runpod-volume/comfyui/models",
        help="Target path on RunPod volume (default: /runpod-volume/comfyui/models)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Create zip but don't send via runpodctl"
    )

    parser.add_argument(
        "--keep-zip",
        action="store_true",
        help="Keep zip file after sending"
    )

    return parser.parse_args()


def get_dir_size(path):
    """Calculate total size of directory in bytes."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.isfile(filepath):
                total += os.path.getsize(filepath)
    return total


def format_size(bytes_size):
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def create_zip(local_dir, zip_path):
    """Create zip archive of local directory.

    Args:
        local_dir: Path to directory to zip
        zip_path: Path for output zip file

    Returns:
        tuple: (success: bool, file_count: int, zip_size: int)
    """
    print(f"\nCreating zip archive: {zip_path}")
    print("-" * 60)

    local_path = Path(local_dir).resolve()
    if not local_path.exists():
        print(f"ERROR: Directory does not exist: {local_dir}")
        return False, 0, 0

    if not local_path.is_dir():
        print(f"ERROR: Path is not a directory: {local_dir}")
        return False, 0, 0

    file_count = 0

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(local_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Calculate relative path from local_dir
                    arcname = os.path.relpath(file_path, local_path)
                    zipf.write(file_path, arcname)
                    file_count += 1

                    if file_count % 10 == 0:
                        print(f"  Added {file_count} files...", end='\r')

        zip_size = os.path.getsize(zip_path)
        print(f"  Added {file_count} files...done!")
        print(f"\n✓ Zip created successfully")
        print(f"  Files: {file_count}")
        print(f"  Size: {format_size(zip_size)}")

        return True, file_count, zip_size

    except Exception as e:
        print(f"\n✗ Error creating zip: {e}")
        return False, 0, 0


def check_runpodctl():
    """Check if runpodctl is installed and available.

    Returns:
        bool: True if runpodctl is available
    """
    try:
        result = subprocess.run(
            ["runpodctl", "version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def send_via_runpodctl(zip_path):
    """Send zip file via runpodctl and capture transfer code.

    Args:
        zip_path: Path to zip file to send

    Returns:
        str: Transfer code or None if failed
    """
    print(f"\nSending via runpodctl...")
    print("-" * 60)

    try:
        # Run runpodctl send
        result = subprocess.run(
            ["runpodctl", "send", zip_path],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )

        if result.returncode != 0:
            print(f"✗ runpodctl send failed:")
            print(result.stderr)
            return None

        # Parse output for transfer code
        # runpodctl outputs the code in format: "Code is: 1234-alpha-bravo"
        output = result.stdout
        print(output)

        # Extract code from output
        for line in output.split('\n'):
            if 'code' in line.lower() or 'receive' in line.lower():
                # Try to extract the code pattern (xxxx-word-word-word)
                words = line.split()
                for word in words:
                    if '-' in word and len(word) > 10:
                        return word.strip()

        # If we couldn't parse the code, return a marker
        print("\n⚠ Could not automatically parse transfer code from output")
        print("Please check the output above for the transfer code")
        return "UNKNOWN"

    except subprocess.TimeoutExpired:
        print("✗ runpodctl send timed out after 5 minutes")
        return None
    except Exception as e:
        print(f"✗ Error running runpodctl: {e}")
        return None


def generate_extract_script(zip_name, target_path):
    """Generate Python extraction script for RunPod side.

    Args:
        zip_name: Name of the zip file
        target_path: Target extraction path

    Returns:
        str: Python script content
    """
    script = f'''#!/usr/bin/env python3
"""
Model Extraction Script
Generated by sync-models.py on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This script extracts models from the transferred zip file to the ComfyUI models directory.
"""

import os
import sys
import zipfile
from pathlib import Path


def extract_models():
    """Extract models from zip to target directory."""
    zip_path = "{zip_name}"
    target_path = "{target_path}"

    print("=" * 60)
    print("ComfyUI Models Extraction")
    print("=" * 60)
    print(f"Zip file: {{zip_path}}")
    print(f"Target: {{target_path}}")
    print()

    # Check if zip exists
    if not os.path.exists(zip_path):
        print(f"ERROR: Zip file not found: {{zip_path}}")
        print("\\nMake sure you:")
        print("  1. Ran: runpodctl receive <transfer-code>")
        print("  2. Are in the directory where the zip was received")
        return False

    # Create target directory
    print("Creating target directory...")
    os.makedirs(target_path, exist_ok=True)
    print(f"✓ Target directory ready: {{target_path}}")
    print()

    # Extract zip
    print("Extracting files...")
    print("-" * 60)

    try:
        file_count = 0
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            members = zipf.namelist()
            total = len(members)

            for i, member in enumerate(members, 1):
                zipf.extract(member, target_path)
                file_count += 1

                if file_count % 10 == 0:
                    print(f"  Extracted {{file_count}}/{{total}} files...", end='\\r')

            print(f"  Extracted {{file_count}}/{{total}} files...done!")

        print()
        print("✓ Extraction complete!")
        print(f"  Files extracted: {{file_count}}")
        print(f"  Location: {{target_path}}")
        print()

        # List what was extracted
        print("Extracted directories:")
        print("-" * 60)
        for item in os.listdir(target_path):
            item_path = os.path.join(target_path, item)
            if os.path.isdir(item_path):
                count = len(list(Path(item_path).rglob('*')))
                print(f"  {{item}}/  ({{count}} items)")

        print()

        # Ask about cleanup
        response = input("Delete zip file? (y/N): ")
        if response.lower() == 'y':
            os.remove(zip_path)
            print(f"✓ Deleted {{zip_path}}")
        else:
            print(f"Keeping {{zip_path}}")

        print()
        print("=" * 60)
        print("Models ready for ComfyUI!")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\\n✗ Error during extraction: {{e}}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = extract_models()
    sys.exit(0 if success else 1)
'''

    return script


def save_extract_script(script_content, zip_name):
    """Save extraction script to file.

    Args:
        script_content: Python script content
        zip_name: Name of zip file (used to name script)

    Returns:
        str: Path to saved script
    """
    script_name = f"extract-{zip_name.replace('.zip', '')}.py"
    script_path = os.path.join("scripts", script_name)

    with open(script_path, 'w') as f:
        f.write(script_content)

    # Make executable
    os.chmod(script_path, 0o755)

    return script_path


def print_instructions(transfer_code, zip_name, extract_script_path, volume_id, target_path):
    """Print instructions for completing the transfer on RunPod side.

    Args:
        transfer_code: Transfer code from runpodctl
        zip_name: Name of the zip file
        extract_script_path: Path to extraction script
        volume_id: RunPod volume ID
        target_path: Target extraction path
    """
    print("\n" + "=" * 60)
    print("TRANSFER INITIATED")
    print("=" * 60)
    print()
    print("Next steps on RunPod side:")
    print()

    if volume_id:
        print(f"1. Connect to RunPod pod with volume '{volume_id}' mounted")
    else:
        print("1. Connect to RunPod pod with network volume mounted")

    print()
    print("2. Receive the file:")
    print(f"   runpodctl receive {transfer_code}")
    print()
    print("3. Copy the extraction script to the pod:")
    print(f"   (Upload {extract_script_path} to the pod)")
    print()
    print("4. Run the extraction script:")
    print(f"   python {os.path.basename(extract_script_path)}")
    print()
    print("   Or manually extract:")
    print(f"   unzip {zip_name} -d {target_path}")
    print()
    print("=" * 60)
    print()
    print(f"Extraction script saved to: {extract_script_path}")
    print("You can copy this script to RunPod to automate extraction.")
    print()


def main():
    """Main execution function."""
    args = parse_args()

    print("=" * 60)
    print("ComfyUI Model Sync Utility")
    print("=" * 60)
    print()
    print(f"Local directory: {args.local_dir}")
    print(f"Zip name: {args.zip_name}")
    print(f"Target path: {args.target_path}")
    if args.volume_id:
        print(f"Volume ID: {args.volume_id}")
    if args.dry_run:
        print("Mode: DRY RUN")
    print()

    # Check local directory
    dir_size = get_dir_size(args.local_dir)
    print(f"Directory size: {format_size(dir_size)}")
    print()

    # Create zip
    success, file_count, zip_size = create_zip(args.local_dir, args.zip_name)
    if not success:
        sys.exit(1)

    # Generate extraction script
    print("\nGenerating extraction script...")
    script_content = generate_extract_script(args.zip_name, args.target_path)
    extract_script_path = save_extract_script(script_content, args.zip_name)
    print(f"✓ Extraction script saved: {extract_script_path}")

    # Send via runpodctl (unless dry-run)
    transfer_code = None

    if args.dry_run:
        print("\nDRY RUN - Skipping runpodctl send")
        transfer_code = "XXXX-dry-run-code"
    else:
        # Check if runpodctl is available
        if not check_runpodctl():
            print("\n⚠ runpodctl not found in PATH")
            print("Install runpodctl: https://github.com/runpod/runpodctl")
            print()
            print("You can still use the zip file manually:")
            print(f"  1. Upload {args.zip_name} to RunPod")
            print(f"  2. Run {extract_script_path}")
            sys.exit(1)

        transfer_code = send_via_runpodctl(args.zip_name)
        if not transfer_code:
            print("\n✗ Failed to send file via runpodctl")
            sys.exit(1)

    # Print instructions
    print_instructions(
        transfer_code,
        args.zip_name,
        extract_script_path,
        args.volume_id,
        args.target_path
    )

    # Cleanup zip if requested
    if not args.keep_zip and not args.dry_run:
        response = input("Delete local zip file? (y/N): ")
        if response.lower() == 'y':
            os.remove(args.zip_name)
            print(f"✓ Deleted {args.zip_name}")
        else:
            print(f"Keeping {args.zip_name}")

    print("\n✓ Sync initiated successfully!")


if __name__ == "__main__":
    main()
