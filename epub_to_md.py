import os
import sys
import shutil
import zipfile
import subprocess
import xml.etree.ElementTree as ET
import re
from urllib.parse import unquote

# Default log file location
LOG_FILE = os.path.expanduser("~/epub2md.log")

def log(message):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[EPUB_PY] {message}
")
    except Exception:
        pass
    print(message, flush=True)

# Redirect stderr to log for uncaught exceptions
try:
    sys.stderr = open(LOG_FILE, "a", encoding="utf-8")
except Exception:
    pass

# Check for pandoc
if shutil.which('pandoc') is None:
    # Try common paths
    common_paths = ["/opt/homebrew/bin/pandoc", "/usr/local/bin/pandoc", "/usr/bin/pandoc"]
    found = False
    for p in common_paths:
        if os.path.exists(p):
            log(f"Found pandoc at {p}")
            os.environ["PATH"] += os.pathsep + os.path.dirname(p)
            found = True
            break
    
    if not found:
        log("Error: pandoc not found in PATH or common locations.")
        sys.exit(1)

def sanitize_name(name):
    if name is None:
        return "Untitled"
    # Remove invalid characters
    # We want to remove \ / * ? : " < > |
    # Regex: [\/*?:"<>|]
    s = re.sub(r'[\/*?:"<>|]', "", str(name)).strip()
    if not s:
        return "Untitled"
    return s[:100]

def get_namespace(element):
    m = re.match(r'\{.*\}', element.tag)
    return m.group(0) if m else ''

def parse_ncx(ncx_path):
    try:
        tree = ET.parse(ncx_path)
        root = tree.getroot()
        ns = get_namespace(root)
        
        toc = []
        
        def process_navpoint(node):
            items = []
            # Find all navPoints (direct children)
            for child in node:
                if child.tag.endswith('navPoint'):
                    # Get Label
                    navLabel = child.find(f"{ns}navLabel")
                    text_tag = navLabel.find(f"{ns}text") if navLabel is not None else None
                    title = text_tag.text if text_tag is not None else "Untitled"
                    
                    # Get Content
                    content = child.find(f"{ns}content")
                    src = content.attrib.get('src') if content is not None else None
                    
                    # Recurse
                    children = process_navpoint(child)
                    
                    items.append({
                        'title': title,
                        'src': src,
                        'children': children
                    })
            return items
            
        navMap = root.find(f"{ns}navMap")
        if navMap is not None:
            toc = process_navpoint(navMap)
            
        return toc
    except Exception as e:
        print(f"Error parsing NCX: {e}")
        return []

# Global cache for converted markdown content: src_file -> markdown_text
MARKDOWN_CACHE = {}

def fix_media_links(content, relative_path_to_root):
    """
    Adjusts media links in the content to be relative to the file location.
    Pandoc generates links like 'media/image.jpg' (relative to root).
    We need to change them to '../media/image.jpg' if the file is in a subfolder.
    """
    if not relative_path_to_root or relative_path_to_root == ".":
        return content
    
    # We want to replace "media/" with "relative_path/media/"
    # relative_path_to_root might be ".." or "../.."
    
    # Ensure we use forward slashes for markdown compatibility
    prefix = relative_path_to_root.replace("", "/")
    replacement = f"{prefix}/media/"
    
    # Regex for Markdown: ![...](media/...)
    # We look for ](media/
    content = re.sub(r'\]\(media/', f']({replacement}', content)
    
    # Regex for HTML: src="media/..." or src='media/...'
    content = re.sub(r'src="media/', f'src="{replacement}', content)
    content = re.sub(r"src='media/", f"src='{replacement}", content)
    
    return content

def get_markdown_content(src_file, root_output_dir, epub_root):
    # Check cache first
    if src_file in MARKDOWN_CACHE:
        return MARKDOWN_CACHE[src_file]

    full_src_path = os.path.join(epub_root, src_file)
    
    if not os.path.exists(full_src_path):
        print(f"Warning: Source file not found: {full_src_path}")
        return ""

    # Prepare command
    # We run pandoc from root_output_dir so media is extracted to root_output_dir/media
    media_dir = "media" 
    os.makedirs(os.path.join(root_output_dir, media_dir), exist_ok=True)
    
    input_dir = os.path.dirname(full_src_path)
    
    # We use 'markdown' (Pandoc's default) to preserve Header Attributes like {#id}
    # This allows us to accurately slice content based on TOC anchors.
    cmd = [
        'pandoc',
        full_src_path,
        '--extract-media', media_dir,
        '--resource-path', input_dir,
        '--wrap=none',
        '-f', 'html',
        '-t', 'markdown' 
    ]
    
    try:
        # Capture stdout
        # cwd is root_output_dir
        result = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=root_output_dir)
        if result.returncode != 0:
             print(f"Error converting {src_file}: {result.stderr.decode()}")
             return ""
        else:
             stderr_output = result.stderr.decode().strip()
             if stderr_output:
                 # Filter out common benign warnings about missing fonts etc if needed
                 # For now, just print.
                 print(f"Pandoc warnings for {src_file}:
{stderr_output}")
             
             content = result.stdout.decode('utf-8')
             MARKDOWN_CACHE[src_file] = content
             return content

    except Exception as e:
        print(f"Exception converting {src_file}: {e}")
        return ""

def extract_section(content, anchor):
    """
    Extracts a section from markdown content starting at the anchor.
    """
    if not anchor:
        return content

    lines = content.splitlines()
    start_idx = -1
    
    # Search for anchor. 
    # In Pandoc markdown, it usually appears as {#anchor} at end of header
    # or <div id="anchor"> or <span id="anchor">
    
    patterns = [
        f"{{#{anchor}}}",
        f'id="{anchor}"',
        f"id='{anchor}'",
        f'name="{anchor}"'
    ]
    
    for i, line in enumerate(lines):
        for pat in patterns:
            if pat in line:
                start_idx = i
                break
        if start_idx != -1:
            break
            
    if start_idx == -1:
        print(f"Warning: Anchor '{anchor}' not found in content.")
        return content # Fallback

    # If the found line is a header (has #), use its level.
    # If it's a div/span, look for the next header.
    
    header_level = 0
    content_start_idx = start_idx
    
    # Check if the start line itself is a header
    m = re.match(r'^(#+)\s+', lines[start_idx])
    if m:
        header_level = len(m.group(1))
    else:
        # Look forward for a header
        for i in range(start_idx, min(start_idx + 20, len(lines))):
            line = lines[i]
            m = re.match(r'^(#+)\s+', line)
            if m:
                header_level = len(m.group(1))
                break
        
        # If no header found nearby, maybe it's just a text anchor?
        # In that case, we slice until... end of file? Or next header?
        # Let's assume until next header of ANY level? Or just assume it's a subsection?
        # Safe bet: If we can't determine level, slice until next H1 or H2?
        if header_level == 0:
            header_level = 2 # Assume level 2 by default?
    
    # Scan for next header of same or higher level (fewer #)
    end_idx = len(lines)
    
    # Start scanning AFTER the anchor line (or the header line we found?)
    # If we found a header at line X, we start checking from X+1
    scan_start = start_idx + 1
    
    for i in range(scan_start, len(lines)):
        line = lines[i]
        m = re.match(r'^(#+)\s+', line)
        if m:
            level = len(m.group(1))
            if level <= header_level:
                end_idx = i
                break
                
    return "
".join(lines[start_idx:end_idx])

def convert_toc_item(item, output_base, index, epub_root, root_output_dir):
    title = item['title']
    src = item['src']
    safe_title = sanitize_name(title)
    prefix = f"{index:02d}"
    
    has_children = len(item['children']) > 0
    
    # Determine output location
    if has_children:
        current_dir = os.path.join(output_base, f"{prefix}_{safe_title}")
        os.makedirs(current_dir, exist_ok=True)
        filename = f"00_{safe_title}.md"
        output_path = os.path.join(current_dir, filename)
    else:
        current_dir = output_base
        filename = f"{prefix}_{safe_title}.md"
        output_path = os.path.join(current_dir, filename)

    # Process Content
    if src:
        # Parse src for anchor
        if '#' in src:
            parts = src.split('#')
            src_file = parts[0]
            anchor = parts[1]
        else:
            src_file = src
            anchor = None
            
        src_file = unquote(src_file)
        
        # Get full markdown (cached, generated relative to root)
        content = get_markdown_content(src_file, root_output_dir, epub_root)
            
        # Extract section if anchor exists
        if anchor:
            final_content = extract_section(content, anchor)
        else:
            final_content = content
            
        # Fix media links
        # Calculate relative path from directory containing output_path to root_output_dir
        file_dir = os.path.dirname(output_path)
        rel_path = os.path.relpath(root_output_dir, file_dir)
        final_content = fix_media_links(final_content, rel_path)
            
        if final_content.strip():
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_content)

    # Process children
    if has_children:
        for i, child in enumerate(item['children']):
            convert_toc_item(child, current_dir, i+1, epub_root, root_output_dir)

def main(epub_path):
    if not os.path.exists(epub_path):
        print(f"File not found: {epub_path}")
        return

    # Extract EPUB
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(epub_path)), "temp_epub_extract")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        
    print(f"Processing: {epub_path}")
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            z.extractall(temp_dir)
    except zipfile.BadZipFile:
        print("Error: Invalid EPUB file.")
        return
        
    # Find OPF
    container = os.path.join(temp_dir, "META-INF", "container.xml")
    if not os.path.exists(container):
        print("Invalid EPUB: META-INF/container.xml missing")
        return
        
    try:
        tree = ET.parse(container)
        root = tree.getroot()
        # Find full-path
        rootfile = None
        for child in root.iter():
            if 'full-path' in child.attrib:
                rootfile = child.attrib['full-path']
                break
                
        if not rootfile:
            print("Could not find OPF path")
            return
            
        opf_path = os.path.join(temp_dir, rootfile)
        opf_dir = os.path.dirname(opf_path)
        
        # Parse OPF to find TOC
        opf_tree = ET.parse(opf_path)
        opf_root = opf_tree.getroot()
        opf_ns = get_namespace(opf_root)
        
        # Try to find NCX in spine
        spine = opf_root.find(f"{opf_ns}spine")
        toc_id = spine.attrib.get('toc') if spine is not None else None
        
        toc_file = None
        
        # 1. Look up ID in manifest
        if toc_id:
            manifest = opf_root.find(f"{opf_ns}manifest")
            if manifest is not None:
                for item in manifest.findall(f"{opf_ns}item"):
                    if item.attrib.get('id') == toc_id:
                        toc_file = item.attrib.get('href')
                        break
                        
        # 2. If not found, look for 'nav' property (EPUB 3)
        if not toc_file:
             manifest = opf_root.find(f"{opf_ns}manifest")
             if manifest is not None:
                 for item in manifest.findall(f"{opf_ns}item"):
                     props = item.attrib.get('properties', '')
                     if 'nav' in props.split():
                         toc_file = item.attrib.get('href')
                         break
                         
        if not toc_file:
            print("Could not find TOC file in OPF.")
            return
            
        # print(f"Found TOC: {toc_file}")
        toc_full_path = os.path.join(opf_dir, toc_file)
        
        output_dir = os.path.splitext(epub_path)[0] + "_toc_split"
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)
        
        # Process TOC
        toc_structure = []
        if toc_file.lower().endswith('.ncx'):
            # print("Parsing NCX TOC...")
            toc_structure = parse_ncx(toc_full_path)
        else:
            # print("Parsing HTML Nav TOC...")
            try:
                from bs4 import BeautifulSoup
                with open(toc_full_path, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f, 'html.parser')
                
                nav = soup.find('nav', attrs={'epub:type': 'toc'}) or soup.find('nav')
                if nav:
                    def process_ol(ol_node):
                        items = []
                        for li in ol_node.find_all('li', recursive=False):
                            a = li.find('a', recursive=False) or li.find('span', recursive=False)
                            
                            if a:
                                title = a.get_text().strip()
                                href = a.get('href')
                                
                                children = []
                                next_ol = li.find('ol', recursive=False)
                                if next_ol:
                                    children = process_ol(next_ol)
                                    
                                items.append({'title': title, 'src': href, 'children': children})
                        return items
    
                    ol = nav.find('ol')
                    if ol:
                        toc_structure = process_ol(ol)
            except ImportError:
                print("BeautifulSoup not found, cannot parse EPUB 3 Nav.")
            except Exception as e:
                print(f"Error parsing NAV: {e}")

        if toc_structure:
            for i, item in enumerate(toc_structure):
                # Pass output_dir as both output_base and root_output_dir initially
                convert_toc_item(item, output_dir, i+1, opf_dir, output_dir)
            print(f"Success! Output directory: {output_dir}")
        else:
            print("No TOC structure found in NCX/Nav. Falling back to Spine (linear structure)...")
            # Fallback to Spine
            # 1. Map manifest IDs to Hrefs
            manifest = opf_root.find(f"{opf_ns}manifest")
            id_to_href = {}
            if manifest is not None:
                for item in manifest.findall(f"{opf_ns}item"):
                    iid = item.attrib.get('id')
                    href = item.attrib.get('href')
                    if iid and href:
                        id_to_href[iid] = href
            
            # 2. Iterate Spine
            spine = opf_root.find(f"{opf_ns}spine")
            if spine is not None:
                spine_items = []
                for itemref in spine.findall(f"{opf_ns}itemref"):
                    idref = itemref.attrib.get('idref')
                    if idref and idref in id_to_href:
                        href = id_to_href[idref]
                        # Ignore generated TOCs if possible? 
                        # But harder to detect. Just convert everything.
                        spine_items.append({'title': f"Section {len(spine_items)+1}", 'src': href, 'children': []})
                
                if spine_items:
                    for i, item in enumerate(spine_items):
                        convert_toc_item(item, output_dir, i+1, opf_dir, output_dir)
                    print(f"Success! Output directory: {output_dir}")
                else:
                    print("Error: No Spine items found.")
            else:
                 print("Error: No Spine found.")

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python epub_to_md.py <epub_file>")
        sys.exit(1)
    main(sys.argv[1])
