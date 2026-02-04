import os
import re
import sys
import shutil

def sanitize_filename(name):
    # Remove invalid characters and strip whitespace
    s = re.sub(r'[\/*?:"<>|]', "", name).strip()
    return s[:100] # Limit length

def split_markdown(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    base_dir = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    file_root, _ = os.path.splitext(filename)
    
    output_dir = os.path.join(base_dir, f"{file_root}_split")
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    lines = content.splitlines()
    
    chunks = []
    current_chunk = {'type': 'preamble', 'lines': []}
    chunks.append(current_chunk)
    
    in_code_block = False
    
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            current_chunk['lines'].append(line)
            continue
            
        if in_code_block:
            current_chunk['lines'].append(line)
            continue

        # Check for H1
        m = re.match(r'^#\s+(.+)$', line)
        if m:
            title = m.group(1)
            current_chunk = {'type': 'h1', 'title': title, 'lines': [line]}
            chunks.append(current_chunk)
        else:
            current_chunk['lines'].append(line)

    for i, chunk in enumerate(chunks):
        if not chunk['lines']:
            continue
            
        if chunk['type'] == 'preamble':
            text = "
".join(chunk['lines']).strip()
            if text:
                with open(os.path.join(output_dir, "00_Preamble.md"), "w", encoding="utf-8") as f:
                    f.write(text)
            continue
            
        h1_title = chunk['title']
        h1_lines = chunk['lines']
        
        has_h2 = any(re.match(r'^##\s+', l) for l in h1_lines)
        
        safe_h1_title = sanitize_filename(h1_title)
        prefix = f"{i:02d}"
        
        if has_h2:
            folder_name = f"{prefix}_{safe_h1_title}"
            folder_path = os.path.join(output_dir, folder_name)
            os.makedirs(folder_path)
            
            sub_chunks = []
            curr_sub = {'type': 'intro', 'lines': []}
            sub_chunks.append(curr_sub)
            
            in_code_block_h2 = False
            
            for line in h1_lines:
                stripped = line.lstrip()
                if stripped.startswith("```") or stripped.startswith("~~~"):
                    in_code_block_h2 = not in_code_block_h2
                    curr_sub['lines'].append(line)
                    continue
                
                if in_code_block_h2:
                    curr_sub['lines'].append(line)
                    continue

                m2 = re.match(r'^##\s+(.+)$', line)
                if m2:
                    sub_title = m2.group(1)
                    curr_sub = {'type': 'h2', 'title': sub_title, 'lines': [line]}
                    sub_chunks.append(curr_sub)
                else:
                    curr_sub['lines'].append(line)
            
            for j, sub in enumerate(sub_chunks):
                text = "
".join(sub['lines']).strip()
                if not text:
                    continue
                
                if sub['type'] == 'intro':
                    fname = "00_Overview.md"
                else:
                    safe_h2 = sanitize_filename(sub['title'])
                    fname = f"{j:02d}_{safe_h2}.md"
                
                with open(os.path.join(folder_path, fname), "w", encoding="utf-8") as f:
                    f.write(text)
        else:
            fname = f"{prefix}_{safe_h1_title}.md"
            text = "
".join(h1_lines).strip()
            with open(os.path.join(output_dir, fname), "w", encoding="utf-8") as f:
                f.write(text)

    print(f"Successfully processed {file_path}")
    print(f"Output directory: {output_dir}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python split_markdown.py <file_path>")
        sys.exit(1)
    split_markdown(sys.argv[1])
