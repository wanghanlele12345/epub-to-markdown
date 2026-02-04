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
            f.write(f"[EPUB_PY] {message}\n")
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
    s = re.sub(r'[\\/*?:"<>|]', "", str(name)).strip()
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
    
    # Ensure we use forward slashes for markdown compatibility
    prefix = relative_path_to_root.replace("\\", "/")
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
                 print(f"Pandoc warnings for {src_file}:\n{stderr_output}")
             
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

    header_level = 0
    
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
        
        if header_level == 0:
            header_level = 2 # Assume level 2 by default
    
    # Scan for next header of same or higher level
    end_idx = len(lines)
    scan_start = start_idx + 1
    
    for i in range(scan_start, len(lines)):
        line = lines[i]
        m = re.match(r'^(#+)\s+', line)
        if m:
            level = len(m.group(1))
            if level <= header_level:
                end_idx = i
                break
                
    return "\n".join(lines[start_idx:end_idx])

def append_footnotes(section_content, full_content):
    """
    Scans section_content for internal links (e.g. (#footnote1)).
    Finds lines in full_content that define these IDs (e.g. id="footnote1").
    Appends those lines to section_content if they are missing.
    """
    # 1. Find all internal links in section_content
    referenced_ids = set()
    
    # Match Markdown links: ](#id)
    # This covers standard markdown links and Pandoc's reference links
    links = re.findall(r'\]\(#([a-zA-Z0-9_.-]+)\)', section_content)
    referenced_ids.update(links)
    
    # Match HTML links: href="#id"
    html_links = re.findall(r'href="#([a-zA-Z0-9_.-]+)"', section_content)
    referenced_ids.update(html_links)
    
    if not referenced_ids:
        return section_content

    # 2. Find definitions in full_content
    # We look for lines containing id="ID" or {#ID}
    
    definitions = {}
    full_lines = full_content.splitlines()
    
    def get_ids_in_line(line):
        ids = set()
        # Match HTML id="ID"
        m_id = re.findall(r'id="([a-zA-Z0-9_.-]+)"', line)
        ids.update(m_id)
        # Match Pandoc attributes {#ID ...}
        # We need to be careful not to match just {#}
        m_attr = re.findall(r'\{#([a-zA-Z0-9_.-]+)', line)
        ids.update(m_attr)
        return ids

    # Scan full content to map IDs to Lines
    for line in full_lines:
        # Optimization: only check if line likely contains an ID
        if 'id="' in line or '{#' in line:
            ids = get_ids_in_line(line)
            for i in ids:
                # Store the line for this ID
                # If multiple IDs on one line, it's fine.
                # If multiple lines define same ID (unlikely for valid HTML), last one wins.
                if i in referenced_ids:
                    definitions[i] = line

    # 3. Append missing definitions
    to_append = []
    
    # Check if definition is already in section_content
    existing_ids_in_section = set()
    for line in section_content.splitlines():
        if 'id="' in line or '{#' in line:
            existing_ids_in_section.update(get_ids_in_line(line))
        
    for ref_id in referenced_ids:
        if ref_id not in existing_ids_in_section and ref_id in definitions:
            line = definitions[ref_id]
            if line not in to_append:
                to_append.append(line)
    
    if to_append:
        return section_content + "\n\n---\n\n" + "\n".join(to_append)
        
    return section_content

def cleanup_pandoc_artifacts(content):
    """
    Cleans up Pandoc's artifacts to make Markdown Obsidian-friendly.
    1. Converts inline ^[text](url){#id}^ to <sup id="id"><a href="#url">text</a></sup>
    2. Converts definition lines [text](url){#id} to <a href="url" id="id">text</a>
    3. Removes Pandoc Div fences (::: ...)
    4. Removes Header Attributes ({#id ...})
    """
    # Pattern 1: Inline footnotes ^[...](...){...}^
    pattern1 = r'\^\[(.*?)\]\((.*?)\)\{#([a-zA-Z0-9_.-]+).*?\}\^'
    
    def repl1(match):
        text_content = match.group(1)
        url = match.group(2)
        ref_id = match.group(3)
        # Clean escaped brackets if any
        clean_text = text_content.replace('\\[', '[').replace('\\]', ']')
        return f'<sup id="{ref_id}"><a href="{url}">{clean_text}</a></sup>'
    
    content = re.sub(pattern1, repl1, content)

    # Pattern 2: Link definitions with attributes [...](...){...}
    pattern2 = r'\[(.*?)\]\((.*?)\)\{#([a-zA-Z0-9_.-]+).*?\}'

    def repl2(match):
        text_content = match.group(1)
        url = match.group(2)
        ref_id = match.group(3)
        clean_text = text_content.replace('\\[', '[').replace('\\]', ']')
        return f'<a href="{url}" id="{ref_id}">{clean_text}</a>'

    content = re.sub(pattern2, repl2, content)

    # Pattern 3: Remove attributes from images ![...](...){...}
    # Matches: ![alt](url){.class width=...} -> ![alt](url)
    pattern3 = r'!\[(.*?)\]\((.*?)\)\{.*?\}'
    content = re.sub(pattern3, r'![\1](\2)', content)

    # Pattern 4: Remove generic span attributes [text]{...}
    # Matches: [text]{.class} -> text
    # Note: We use a lookahead to ensure we don't match links [text](url)
    # But since { immediately follows ], it distinguishes from (url)
    pattern4 = r'(?<!\!)\[(.*?)\]\{.*?\}'
    content = re.sub(pattern4, r'\1', content)

    # Pattern 5: Remove Pandoc Divs (::: ...)
    # Matches lines starting with :::
    content = re.sub(r'^:::.*?$', '', content, flags=re.MULTILINE)

    # Pattern 6: Remove Header Attributes {#...}
    # Matches: # Title {#id .class} -> # Title
    # We look for {#...} at the end of a header line
    content = re.sub(r'^(#+.*)\s+\{#[^}]+\}\s*$', r'\1', content, flags=re.MULTILINE)
    
    # Global cleanup of common Pandoc escapes that are unnecessary in Obsidian
    content = content.replace(r'\[', '[').replace(r'\]', ']').replace(r'\"', '"')
    
    return content

def convert_toc_item(item, output_base, index, epub_root, root_output_dir):
    title = item['title']
    src = item['src']
    safe_title = sanitize_name(title)
    prefix = f"{index:02d}"
    
    has_children = len(item['children']) > 0
    
    if has_children:
        current_dir = os.path.join(output_base, f"{prefix}_{safe_title}")
        os.makedirs(current_dir, exist_ok=True)
        filename = f"00_{safe_title}.md"
        output_path = os.path.join(current_dir, filename)
    else:
        current_dir = output_base
        filename = f"{prefix}_{safe_title}.md"
        output_path = os.path.join(current_dir, filename)

    if src:
        if '#' in src:
            parts = src.split('#')
            src_file = parts[0]
            anchor = parts[1]
        else:
            src_file = src
            anchor = None
            
        src_file = unquote(src_file)
        
        content = get_markdown_content(src_file, root_output_dir, epub_root)
            
        if anchor:
            final_content = extract_section(content, anchor)
        else:
            final_content = content
            
        # FIX FOOTNOTES: Append definitions found in full content if referenced in section
        final_content = append_footnotes(final_content, content)
            
        file_dir = os.path.dirname(output_path)
        rel_path = os.path.relpath(root_output_dir, file_dir)
        final_content = fix_media_links(final_content, rel_path)
        
        # Cleanup Pandoc artifacts (footnotes, divs, headers)
        final_content = cleanup_pandoc_artifacts(final_content)
            
        if final_content.strip():
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_content)

    if has_children:
        for i, child in enumerate(item['children']):
            convert_toc_item(child, current_dir, i+1, epub_root, root_output_dir)

def main(epub_path):
    if not os.path.exists(epub_path):
        print(f"File not found: {epub_path}")
        return

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
        
    container = os.path.join(temp_dir, "META-INF", "container.xml")
    if not os.path.exists(container):
        print("Invalid EPUB: META-INF/container.xml missing")
        return
        
    try:
        tree = ET.parse(container)
        root = tree.getroot()
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
        
        opf_tree = ET.parse(opf_path)
        opf_root = opf_tree.getroot()
        opf_ns = get_namespace(opf_root)
        
        spine = opf_root.find(f"{opf_ns}spine")
        toc_id = spine.attrib.get('toc') if spine is not None else None
        
        toc_file = None
        
        if toc_id:
            manifest = opf_root.find(f"{opf_ns}manifest")
            if manifest is not None:
                for item in manifest.findall(f"{opf_ns}item"):
                    if item.attrib.get('id') == toc_id:
                        toc_file = item.attrib.get('href')
                        break
                        
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
            
        toc_full_path = os.path.join(opf_dir, toc_file)
        
        output_dir = os.path.splitext(epub_path)[0] + "_toc_split"
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)
        
        toc_structure = []
        if toc_file.lower().endswith('.ncx'):
            toc_structure = parse_ncx(toc_full_path)
        else:
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
                convert_toc_item(item, output_dir, i+1, opf_dir, output_dir)
            print(f"Success! Output directory: {output_dir}")
        else:
            print("No TOC structure found in NCX/Nav. Falling back to Spine (linear structure)...")
            manifest = opf_root.find(f"{opf_ns}manifest")
            id_to_href = {}
            if manifest is not None:
                for item in manifest.findall(f"{opf_ns}item"):
                    iid = item.attrib.get('id')
                    href = item.attrib.get('href')
                    if iid and href:
                        id_to_href[iid] = href
            
            spine = opf_root.find(f"{opf_ns}spine")
            if spine is not None:
                spine_items = []
                for itemref in spine.findall(f"{opf_ns}itemref"):
                    idref = itemref.attrib.get('idref')
                    if idref and idref in id_to_href:
                        href = id_to_href[idref]
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