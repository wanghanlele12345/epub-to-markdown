#!/bin/bash

# Default Log file
LOGFILE="$HOME/epub2md.log"
exec >> "$LOGFILE" 2>&1

echo "--- Conversion Task: $(date) ---"

# Setup Environment
# Add standard paths for homebrew, local bin etc. to ensure tools are found
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
export LANG=en_US.UTF-8

# Paths to helper scripts
# We assume scripts are in the same directory as this script
# Using realpath to ensure we have the absolute path even if symlinked
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SPLIT_SCRIPT="$SCRIPT_DIR/split_markdown.py"
EPUB_SCRIPT="$SCRIPT_DIR/epub_to_md.py"
MARKER_BIN="marker_single"

# Helper function for macOS notifications
notify() {
    local msg="$1"
    local title="$2"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        osascript -e "display notification \"$msg\" with title \"$title\"" 2>/dev/null
    fi
}

# Helper function for macOS alerts (modal dialogs for errors)
alert() {
    local msg="$1"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        osascript -e "display alert \"Conversion Error\" message \"$msg\" as critical" 2>/dev/null
    fi
}

# Check Arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <file1> [file2] ..."
    exit 1
fi

TOTAL=$#
CURRENT=0
FAILURES=0

# Initial Notification
notify "Starting conversion of $TOTAL file(s)..." "EPUB to Markdown"

for INPUT_FILE in "$@"; do
    CURRENT=$((CURRENT + 1))
    FILENAME=$(basename "$INPUT_FILE")
    EXTENSION="${FILENAME##*.}"
    EXTENSION=$(echo "$EXTENSION" | tr '[:upper:]' '[:lower:]')
    
    echo "Processing ($CURRENT/$TOTAL): $FILENAME ($EXTENSION)"
    notify "Processing $FILENAME..." "Converting ($CURRENT/$TOTAL)"

    if [[ "$EXTENSION" == "pdf" ]]; then
        # PDF Logic (Marker)
        if ! command -v "$MARKER_BIN" &> /dev/null; then
             ERR="Error: marker_single not found. Cannot convert PDF."
             echo "$ERR"
             alert "$ERR"
             FAILURES=$((FAILURES + 1))
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
            RET=$?
            if [ $RET -ne 0 ]; then
                ERR="Failed to convert $FILENAME. See log at $LOGFILE."
                echo "Python Script Failed with exit code $RET"
                alert "$ERR"
                FAILURES=$((FAILURES + 1))
            fi
        else
            ERR="Error: EPUB script not found at $EPUB_SCRIPT"
            echo "$ERR"
            alert "$ERR"
            FAILURES=$((FAILURES + 1))
        fi
        
    else
        echo "Unsupported format: $EXTENSION"
        # Optional: alert for unsupported format
        # alert "Skipping $FILENAME: Unsupported format $EXTENSION"
    fi

done

if [[ "$OSTYPE" == "darwin"* ]]; then
    if [ $FAILURES -eq 0 ]; then
        notify "All $TOTAL tasks completed successfully!" "Conversion Finished"
        osascript -e "display notification \"Check the folder for output.\" with title \"Success\" subtitle \"Processed $TOTAL files\"" 2>/dev/null
    else
        notify "Completed with $FAILURES error(s)." "Conversion Finished"
        # We don't pop an alert here since we likely alerted during the loop, 
        # or we can pop a final summary.
    fi
fi

echo "Done."