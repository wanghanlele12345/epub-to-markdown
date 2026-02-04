#!/bin/bash

# Default Log file
LOGFILE="$HOME/epub2md.log"
exec >> "$LOGFILE" 2>&1

echo "--- Conversion Task: $(date) ---"

# Setup Environment
# Add standard paths for homebrew, local bin etc.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

# Paths to helper scripts
# We assume scripts are in the same directory as this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SPLIT_SCRIPT="$SCRIPT_DIR/split_markdown.py"
EPUB_SCRIPT="$SCRIPT_DIR/epub_to_md.py"
MARKER_BIN="marker_single"

# Soft check for marker_single (optional for PDF)
if ! command -v marker_single &> /dev/null; then
    # Try common locations if needed or warn
    # echo "Warning: marker_single not found in PATH."
    pass=true
fi

# Main Loop
if [ $# -eq 0 ]; then
    echo "Usage: $0 <file1> [file2] ..."
    exit 1
fi

TOTAL=$#
CURRENT=0

for INPUT_FILE in "$@"; do
    CURRENT=$((CURRENT + 1))
    FILENAME=$(basename "$INPUT_FILE")
    EXTENSION="${FILENAME##*.}"
    EXTENSION=$(echo "$EXTENSION" | tr '[:upper:]' '[:lower:]')
    
    echo "Processing ($CURRENT/$TOTAL): $FILENAME ($EXTENSION)"
    # osascript is macOS specific. 
    if [[ "$OSTYPE" == "darwin"* ]]; then
        osascript -e "display notification "Processing $FILENAME..." with title "Converting ($CURRENT/$TOTAL)"" 2>/dev/null
    fi

    if [[ "$EXTENSION" == "pdf" ]]; then
        # PDF Logic (Marker)
        if ! command -v "$MARKER_BIN" &> /dev/null; then
             echo "Error: marker_single not found. Cannot convert PDF."
             continue
        fi

        DIR=$(dirname "$INPUT_FILE")
        BASENAME="${FILENAME%.*}"
        OUTPUT_DIR="$DIR/${BASENAME}_md"
        
        "$MARKER_BIN" "$INPUT_FILE" --output_dir "$OUTPUT_DIR"

        # Split Markdown (H1/H2)
        if [ -f "$SPLIT_SCRIPT" ]; then
            MD_FILE=$(find "$OUTPUT_DIR" -maxdepth 1 -name "*.md" | head -n 1)
            if [ -f "$MD_FILE" ]; then
                echo "Splitting PDF Markdown..."
                python3 "$SPLIT_SCRIPT" "$MD_FILE"
            fi
        fi
        
    elif [[ "$EXTENSION" == "epub" ]]; then
        # EPUB Logic (TOC Split)
        if [ -f "$EPUB_SCRIPT" ]; then
            echo "Splitting EPUB by TOC..."
            python3 "$EPUB_SCRIPT" "$INPUT_FILE"
        else
            echo "Error: EPUB script not found at $EPUB_SCRIPT"
        fi
        
    else
        echo "Unsupported format: $EXTENSION"
    fi

done

if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e "display notification "All tasks completed!" with title "Convert to MD"" 2>/dev/null
    # Optional: Close terminal if run from Automator context
    # osascript -e 'tell application "Terminal" to close front window' & exit
fi

echo "Done."
