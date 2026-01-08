# AI Screenshot Renamer

Automatically renames your screenshots using AI (OpenAI GPT-4 Vision). 
It watches your screenshots folder, analyzes new images, and gives them descriptive filenames like `2024-01-08_github-pull-request-review.png`.

It also adds the full AI description to the file's metadata (Finder comments), making your screenshots searchable via Spotlight.

## Features

-   **Automatic Watching**: Runs in the background and processes new screenshots instantly.
-   **Smart Renaming**: Uses GPT-4 Vision to understand image content.
-   **Metadata Tagging**: Embeds the full description in Finder comments for Spotlight search.
-   **Safe**: Handles duplicates and never overwrites existing files.

## Setup

1.  **Clone the repo**:
    ```bash
    git clone https://github.com/yourusername/screenshot-renamer.git
    cd screenshot-renamer
    ```

2.  **Create a Virtual Environment**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure API Key**:
    Create a `.env` file in the project directory:
    ```bash
    OPENAI_API_KEY=sk-your-api-key-here
    ```

## Usage

### Run Manually
```bash
# Process existing files
python3 renamer.py ~/Documents/Screenshots

# Watch for new files
python3 renamer.py ~/Documents/Screenshots --watch
```

### Run via Double-Click (macOS)
1.  Make the script executable: `chmod +x "Screenshot Renamer.command"`
2.  Double-click **Screenshot Renamer.command** to start watching.
3.  Double-click it again to stop the background process.

## Customization
You can modify `renamer.py` to change the AI prompt or naming convention.
