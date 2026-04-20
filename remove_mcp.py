import os

files = [
    "src/mem_graph/tools/filesystem/filesystem.py",
    "src/mem_graph/tools/filesystem/status.py",
    "src/mem_graph/tools/filesystem/tree.py",
    "src/mem_graph/tools/graph/graph_queries.py",
    "src/mem_graph/tools/code/parser.py",
    "src/mem_graph/tools/sandbox/session.py",
]

for file in files:
    with open(file, "r") as f:
        content = f.read()

    new_content = ""
    lines = content.split("\n")
    for line in lines:
        if "@mcp.tool" in line:
            continue
        new_content += line + "\n"
    
    # remove trailing newline since we re-joined using it
    if new_content.endswith("\n\n"):
        new_content = new_content[:-1]
        
    with open(file, "w") as f:
        f.write(new_content)

print("Removed @mcp.tool from internal tools.")
