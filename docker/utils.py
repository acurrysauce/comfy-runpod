"""
Utility functions for comfy-runpod handler.

Provides helpers for model downloading, S3 operations, and cleanup.
"""

import os
import time
import logging
import requests
import boto3
from pathlib import Path
from typing import Dict, Any, Optional, Union
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def download_file(url: str, destination: str) -> bool:
    """Download file from URL with streaming.

    Args:
        url: URL to download from
        destination: Local file path to save to

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Downloading {url} to {destination}")

        # Create parent directory if needed
        os.makedirs(os.path.dirname(destination), exist_ok=True)

        # Stream download
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        with open(destination, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        file_size_mb = os.path.getsize(destination) / (1024 * 1024)
        logger.info(f"✓ Downloaded {file_size_mb:.1f} MB")
        return True

    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        return False


def download_from_s3(s3_uri: str, destination: str) -> bool:
    """Download file from S3.

    Args:
        s3_uri: S3 URI (s3://bucket/key)
        destination: Local file path to save to

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Downloading from S3: {s3_uri}")

        # Parse S3 URI
        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')

        # Create parent directory if needed
        os.makedirs(os.path.dirname(destination), exist_ok=True)

        # Download from S3
        s3 = boto3.client('s3')
        s3.download_file(bucket, key, destination)

        file_size_mb = os.path.getsize(destination) / (1024 * 1024)
        logger.info(f"✓ Downloaded {file_size_mb:.1f} MB from S3")
        return True

    except Exception as e:
        logger.error(f"Error downloading from S3 {s3_uri}: {e}")
        return False


def download_models(models_config: Dict[str, Any], base_path: str) -> Dict[str, bool]:
    """Download models specified in configuration.

    Args:
        models_config: Dictionary of model types to URLs/S3 URIs
        base_path: Base path for models directory

    Returns:
        Dictionary mapping model names to success status

    Example:
        models_config = {
            "checkpoints": {
                "model1.safetensors": "https://example.com/model1.safetensors",
                "model2.safetensors": {"s3": "s3://bucket/model2.safetensors"}
            },
            "loras": {
                "lora1.safetensors": "https://example.com/lora1.safetensors"
            }
        }
    """
    results = {}

    for model_type, models in models_config.items():
        model_dir = os.path.join(base_path, model_type)
        os.makedirs(model_dir, exist_ok=True)

        for filename, source in models.items():
            destination = os.path.join(model_dir, filename)

            # Skip if already exists
            if os.path.exists(destination):
                logger.info(f"✓ Model already exists: {filename}")
                results[filename] = True
                continue

            # Download based on source type
            if isinstance(source, str):
                # Direct URL
                if source.startswith("s3://"):
                    results[filename] = download_from_s3(source, destination)
                else:
                    results[filename] = download_file(source, destination)
            elif isinstance(source, dict):
                # Dictionary with url or s3 key
                if "s3" in source:
                    results[filename] = download_from_s3(source["s3"], destination)
                elif "url" in source:
                    results[filename] = download_file(source["url"], destination)
                else:
                    logger.error(f"Invalid source for {filename}: {source}")
                    results[filename] = False
            else:
                logger.error(f"Invalid source type for {filename}: {type(source)}")
                results[filename] = False

    # Log summary
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    logger.info(f"Model download complete: {success_count}/{total_count} successful")

    return results


def upload_to_s3(file_path: str, bucket: str, key: str, generate_presigned_url: bool = True, expiration: int = 604800) -> Optional[str]:
    """Upload file to S3 and optionally generate presigned URL.

    Args:
        file_path: Local file path to upload
        bucket: S3 bucket name
        key: S3 key (path) for the file
        generate_presigned_url: Whether to generate presigned URL
        expiration: Presigned URL expiration in seconds (default: 7 days)

    Returns:
        Presigned URL if requested, None otherwise
    """
    try:
        logger.info(f"Uploading {file_path} to s3://{bucket}/{key}")

        s3 = boto3.client('s3')
        s3.upload_file(file_path, bucket, key)

        logger.info(f"✓ Uploaded to S3")

        if generate_presigned_url:
            url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=expiration
            )
            logger.info(f"✓ Generated presigned URL (expires in {expiration}s)")
            return url

        return None

    except Exception as e:
        logger.error(f"Error uploading to S3: {e}")
        return None


def cleanup_outputs(output_dir: str, max_age_seconds: int = 3600) -> int:
    """Remove old output files to prevent disk space issues.

    Args:
        output_dir: Output directory to clean
        max_age_seconds: Maximum age of files to keep (default: 1 hour)

    Returns:
        Number of files removed
    """
    try:
        if not os.path.exists(output_dir):
            return 0

        current_time = time.time()
        removed_count = 0

        for filename in os.listdir(output_dir):
            filepath = os.path.join(output_dir, filename)

            # Skip directories
            if not os.path.isfile(filepath):
                continue

            # Check file age
            file_age = current_time - os.path.getmtime(filepath)
            if file_age > max_age_seconds:
                try:
                    os.remove(filepath)
                    removed_count += 1
                    logger.debug(f"Removed old file: {filename} (age: {file_age/60:.1f} min)")
                except Exception as e:
                    logger.warning(f"Failed to remove {filename}: {e}")

        if removed_count > 0:
            logger.info(f"✓ Cleaned up {removed_count} old output files")

        return removed_count

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return 0
