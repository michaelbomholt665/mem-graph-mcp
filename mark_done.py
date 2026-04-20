with open("docs/planning/tasks/033-tool-system.md", "r") as f:
    content = f.read()
content = content.replace("- [ ]", "- [x]")
with open("docs/planning/tasks/033-tool-system.md", "w") as f:
    f.write(content)
