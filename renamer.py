#!/usr/bin/env python3
"""
Screenshot AI Renamer
Watches a folder and automatically renames screenshots using OpenAI GPT-4 Vision.
"""

import argparse
import base64
import io
import os
import re
import plistlib
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from PIL import Image
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

# Max image dimension for processing
MAX_IMAGE_SIZE = 1024

# Supported image extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}

# Default OpenAI model
DEFAULT_MODEL = 'gpt-4o-mini'

# AI prompt for generating filenames
FILENAME_PROMPT = """Look at this screenshot and generate a descriptive filename.

Be specific about what you see:
- If it's an app, name the app and what's shown (e.g., "slack-dm-with-john-about-project")
- If it's a webpage, include the site and content (e.g., "github-pull-request-review-comments")
- If it's code, mention the language and what it does (e.g., "python-async-api-handler")
- If it's a document, describe the content (e.g., "quarterly-sales-report-chart")

Rules:
- Use lowercase letters and hyphens only
- Be specific and descriptive (5-8 words is ideal)
- No special characters or punctuation

Respond with ONLY the filename, nothing else."""


def sanitize_filename(text: str, max_length: int = 60) -> str:
    """Clean AI output to create a valid filename."""
    # Lowercase and strip
    text = text.lower().strip()

    # Remove quotes and common prefixes AI might add
    text = re.sub(r'^["\'`]|["\'`]$', '', text)
    text = re.sub(r'^(filename:|description:|here is|the filename is)\s*', '', text, flags=re.IGNORECASE)

    # Replace spaces and underscores with hyphens
    text = re.sub(r'[\s_]+', '-', text)

    # Keep only alphanumeric and hyphens
    text = re.sub(r'[^a-z0-9-]', '', text)

    # Collapse multiple hyphens
    text = re.sub(r'-+', '-', text)

    # Remove leading/trailing hyphens
    text = text.strip('-')

    # Truncate
    if len(text) > max_length:
        text = text[:max_length].rsplit('-', 1)[0]

    return text or 'screenshot'


def set_finder_comment(file_path: Path, comment: str) -> None:
    """Set the Finder comment for a file using xattr (requires binary plist)."""
    if not comment:
        return

    try:
        # Create binary plist for the comment
        plist_data = plistlib.dumps(comment, fmt=plistlib.FMT_BINARY)
        
        # Convert to hex string for xattr -x
        hex_data = plist_data.hex()
        
        # Use xattr with -x (hex input)
        cmd = [
            'xattr',
            '-x',
            '-w',
            'com.apple.metadata:kMDItemFinderComment',
            hex_data,
            str(file_path.absolute())
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        print("  Added Finder comment")
    except Exception as e:
        print(f"  Warning: Error setting comment: {e}")


def get_unique_path(base_path: Path) -> Path:
    """Generate a unique file path by appending numbers if needed."""
    if not base_path.exists():
        return base_path

    stem = base_path.stem
    suffix = base_path.suffix
    parent = base_path.parent

    counter = 1
    while True:
        new_path = parent / f"{stem}-{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


def resize_image_if_needed(image_path: str) -> bytes:
    """Resize image if it's too large for efficient processing."""
    with Image.open(image_path) as img:
        # Convert to RGB if necessary (handles PNG with transparency)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Resize if larger than max size
        if max(img.size) > MAX_IMAGE_SIZE:
            img.thumbnail((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE), Image.Resampling.LANCZOS)
            print(f"  Resized to {img.size[0]}x{img.size[1]} for processing")

        # Save to bytes
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()


def analyze_image(client: OpenAI, image_path: str, model: str = DEFAULT_MODEL) -> str:
    """Send image to OpenAI for analysis."""
    try:
        # Resize large images before sending
        image_bytes = resize_image_if_needed(image_path)
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')

        response = client.chat.completions.create(
            model=model,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': FILENAME_PROMPT},
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': f'data:image/jpeg;base64,{image_b64}',
                            'detail': 'low'
                        }
                    }
                ]
            }],
            max_tokens=100
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error analyzing image: {e}")
        return ""


def rename_screenshot(client: OpenAI, file_path: Path, model: str = DEFAULT_MODEL, dry_run: bool = False) -> bool:
    """Analyze and rename a single screenshot."""
    print(f"Processing: {file_path.name}")

    # Get AI description
    description = analyze_image(client, str(file_path), model)
    if not description:
        print(f"  Skipping: Could not analyze image")
        return False

    # Sanitize the description
    clean_name = sanitize_filename(description)
    print(f"  AI description: {description.strip()[:60]}...")
    print(f"  Sanitized: {clean_name}")

    # Build new filename with date prefix
    date_str = datetime.now().strftime('%Y-%m-%d')
    new_name = f"{date_str}_{clean_name}{file_path.suffix.lower()}"
    new_path = get_unique_path(file_path.parent / new_name)

    if dry_run:
        print(f"  Would rename to: {new_path.name}")
        return True

    # Rename the file
    try:
        file_path.rename(new_path)
        print(f"  Renamed to: {new_path.name}")
        
        # Add the original description as metadata
        set_finder_comment(new_path, description)
        
        return True
    except OSError as e:
        print(f"  Error renaming: {e}")
        return False


class ScreenshotHandler(FileSystemEventHandler):
    """Handle new files in the watched folder."""

    def __init__(self, client: OpenAI, model: str = DEFAULT_MODEL, delay: float = 2.0):
        self.client = client
        self.model = model
        self.delay = delay
        self.processed = set()

    def handle_file(self, file_path: Path):
        """Process a new or modified file."""
        # Check if it's an image
        if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            return

        # Avoid processing the same file twice
        if str(file_path) in self.processed:
            return

        # Skip files that look already processed (date prefix)
        if re.match(r'^\d{4}-\d{2}-\d{2}_', file_path.name):
            return

        print(f"Detected: {file_path.name}")
        self.processed.add(str(file_path))

        # Wait for file to be fully written
        time.sleep(self.delay)

        # Verify file still exists (might have been moved/deleted)
        if not file_path.exists():
            print(f"  File no longer exists, skipping")
            return

        rename_screenshot(self.client, file_path, self.model)

    def on_created(self, event):
        if event.is_directory:
            return
        self.handle_file(Path(event.src_path))

    def on_modified(self, event):
        if event.is_directory:
            return
        self.handle_file(Path(event.src_path))


def watch_folder(client: OpenAI, folder: Path, model: str = DEFAULT_MODEL):
    """Watch a folder for new screenshots."""
    print(f"Watching: {folder}")
    print(f"Model: {model}")
    print("Press Ctrl+C to stop\n")

    handler = ScreenshotHandler(client, model=model)
    observer = PollingObserver(timeout=1)
    observer.schedule(handler, str(folder), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        observer.stop()

    observer.join()


def process_existing(client: OpenAI, folder: Path, model: str = DEFAULT_MODEL, dry_run: bool = False):
    """Process all existing screenshots in a folder."""
    images = [
        f for f in folder.iterdir()
        if f.is_file()
        and f.suffix.lower() in IMAGE_EXTENSIONS
        and not re.match(r'^\d{4}-\d{2}-\d{2}_', f.name)
    ]

    if not images:
        print("No unprocessed screenshots found.")
        return

    print(f"Found {len(images)} screenshot(s) to process\n")

    for img in images:
        rename_screenshot(client, img, model, dry_run)
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Rename screenshots using AI-generated descriptions'
    )
    parser.add_argument(
        'folder',
        type=Path,
        help='Folder to watch or process'
    )
    parser.add_argument(
        '--watch', '-w',
        action='store_true',
        help='Watch folder for new screenshots (default: process existing)'
    )
    parser.add_argument(
        '--model', '-m',
        default=DEFAULT_MODEL,
        help=f'OpenAI model to use (default: {DEFAULT_MODEL})'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would be renamed without actually renaming'
    )

    args = parser.parse_args()

    # Validate folder
    folder = args.folder.expanduser().resolve()
    if not folder.exists():
        print(f"Error: Folder does not exist: {folder}")
        sys.exit(1)
    if not folder.is_dir():
        print(f"Error: Not a directory: {folder}")
        sys.exit(1)

    # Check for API key
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Set it with: export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)

    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)

    if args.watch:
        watch_folder(client, folder, args.model)
    else:
        process_existing(client, folder, args.model, args.dry_run)


if __name__ == '__main__':
    main()
