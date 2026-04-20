import os
import glob

files = glob.glob("src/mem_graph/tools/*/*.py")
for file in files:
    with open(file, "r") as f:
        content = f.read()
    
    if "from ...markers import" in content:
        content = content.replace("from ...markers import", "from ..markers import")
        with open(file, "w") as f:
            f.write(content)
        print(f"Fixed {file}")
