---
description: Mandatory Syntax Check Protocol to be run after every code edit.
---

# Syntax Check Protocol

**Trigger**: This workflow MUST be executed immediately after any tool call that modifies code (`write_to_file`, `replace_file_content`, etc.).

## 1. Identify Modified File
Determine the absolute path of the file that was just modified (e.g., `/path/to/file.py`).

## 2. Execute Check Based on File Type

### For Python Files (*.py)
Run the following command to compile the file and check for syntax errors without executing it.

```bash
python3 -m py_compile <absolute_path_to_file>
```

- **If Exit Code 0**: Syntax is valid. Report "Syntax Check: PASS" to the user.
- **If Exit Code != 0**: Syntax is INVALID. 
  - **CRITICAL**: You must **IMMEDIATELY** fix the error. 
  - Do NOT proceed to other tasks. 
  - Reading the error message from stdout/stderr is mandatory.
  - Apply the fix and re-run this check.

### For JavaScript/React Files (*.js, *.jsx)
If the project has a linting script, run it. If not, minimally rely on the build process or careful review.

```bash
# Example (if applicable)
# npx eslint <absolute_path_to_file>
```

## 3. Reporting
You must explicitly confirm to the user:
> "**Syntax Check Passed**: [filename]"
