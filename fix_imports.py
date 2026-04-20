import os

for root, _, files in os.walk("src/mem_graph/tools"):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, "r") as f:
                content = f.read()
            lines = content.split('\n')
            
            import_line_idx = -1
            import_line = ""
            for i, line in enumerate(lines):
                if line.startswith("from ") and "markers import" in line:
                    import_line_idx = i
                    import_line = line
                    break
                    
            if import_line_idx == -1:
                 continue
                 
            future_idx = -1
            for i, line in enumerate(lines):
                if line.startswith("from __future__ import annotations"):
                    future_idx = i
                    break
                    
            if future_idx != -1 and import_line_idx < future_idx:
                lines.pop(import_line_idx)
                # update future_idx since we popped
                future_idx = lines.index("from __future__ import annotations")
                lines.insert(future_idx + 1, import_line)
                
                with open(path, "w") as f:
                    f.write("\n".join(lines))
                    print(f"Fixed {path}")

