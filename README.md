# Epub & PDF to Markdown Converter

This project provides a robust solution for converting EPUB and PDF files into structured Markdown documents. It is designed to preserve the structure of the original document as much as possible, splitting content into separate files based on the Table of Contents (TOC) or Headers.

## Key Features

*   **EPUB Conversion**:
    *   **TOC-Based Splitting**: intelligently parses the EPUB's Table of Contents (NCX or Nav) to create a matching directory structure.
    *   **Nested Structure**: Preserves hierarchy (e.g., `Part 1/Chapter 1.md`).
    *   **Smart Media Handling**: Extracts all images to a centralized `media/` folder and automatically fixes relative links in the Markdown files to point to the correct location.
    *   **Anchor Slicing**: Uses Pandoc to convert the full text but then slices it precisely based on internal anchors, avoiding content duplication across chapters.
    *   **Fallback Mechanism**: If no TOC is found, falls back to the linear "Spine" structure of the EPUB.

*   **PDF Conversion**:
    *   Uses `marker` (a powerful PDF-to-Markdown engine) for high-quality conversion.
    *   **Header Splitting**: Automatically splits the resulting large Markdown file into smaller files based on H1 (`#`) and H2 (`##`) headers.

*   **macOS Integration**:
    *   Includes a script ready to be used with macOS Automator for "Right Click -> Convert" functionality.

## Requirements

*   **Python 3.x**
*   **Pandoc**: Required for EPUB conversion.
    *   Install via Homebrew: `brew install pandoc`
*   **Marker** (Optional, for PDF support):
    *   See [Marker installation instructions](https://github.com/VikParuchuri/marker).

## Installation

1.  Clone this repository:
    ```bash
    git clone https://github.com/wanghanlele12345/epub-to-markdown.git
    cd epub-to-markdown
    ```

2.  Ensure you have the required dependencies (Pandoc, Python).

## Usage

### Command Line

You can run the conversion script directly on one or more files:

```bash
./convert.sh book.epub document.pdf
```

*   **For EPUB**: Creates a folder named `book_toc_split/` containing the structured markdown.
*   **For PDF**: Creates a folder named `document_md/` with the raw output and a `_split/` subfolder with the split content.

### macOS Context Menu (Quick Action)

To add this as a right-click action on macOS:

1.  Open **Automator**.
2.  Create a new **Quick Action**.
3.  Set "Workflow receives current" to **files or folders** in **Finder**.
4.  Add a **Run Shell Script** action.
5.  Set "Pass input" to **as arguments**.
6.  Paste the logic from `convert.sh` or simply call the script:
    ```bash
    /path/to/epub-to-markdown/convert.sh "$@"
    ```
7.  Save as "Convert to Markdown".

Now you can right-click any EPUB or PDF file and select **Quick Actions > Convert to Markdown**.

## Project Structure

*   `epub_to_md.py`: The core Python script for handling EPUB parsing, Pandoc conversion, content slicing, and media management.
*   `split_markdown.py`: A helper Python script to split flat Markdown files (used for PDF output) based on headers.
*   `convert.sh`: The main shell script that acts as an entry point, detecting file types and calling the appropriate Python converter.

## License

MIT License. Feel free to use and modify.
