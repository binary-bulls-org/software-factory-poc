import os
import subprocess
from pathlib import Path
from typing import Union

WORKSPACE_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())).resolve()

def _is_safe(path: Path) -> bool:
    """Ensure path is within the workspace."""
    try:
        path.resolve().relative_to(WORKSPACE_ROOT)
        return True
    except ValueError:
        return False

def list_dir(path: str) -> str:
    """List contents of a directory."""
    target = (WORKSPACE_ROOT / path).resolve()
    if not _is_safe(target):
        return "Error: Path outside workspace"
    if not target.is_dir():
        return "Error: Not a directory"
    try:
        items = []
        for f in target.iterdir():
            name = f.name + ("/" if f.is_dir() else "")
            items.append(name)
        return "\n".join(sorted(items))
    except Exception as e:
        return f"Error: {e}"

def read_file(path: str) -> str:
    """Read file content."""
    target = (WORKSPACE_ROOT / path).resolve()
    if not _is_safe(target):
        return "Error: Path outside workspace"
    if not target.is_file():
        return "Error: Not a file"
    try:
        content = target.read_text(encoding='utf-8')
        return content[:20000]
    except Exception as e:
        return f"Error: {e}"

def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories."""
    target = (WORKSPACE_ROOT / path).resolve()
    
    # Security checks
    if not _is_safe(target):
        return "Error: Path outside workspace"
    
    forbidden_dirs = [
        WORKSPACE_ROOT / "factory",
        WORKSPACE_ROOT / ".github",
        WORKSPACE_ROOT / ".git"
    ]
    
    for forbidden in forbidden_dirs:
        if target == forbidden or forbidden in target.parents:
            return "Error: Writing to forbidden directory"
            
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return "Success"
    except Exception as e:
        return f"Error: {e}"

def run_command(command: str) -> str:
    """Execute a shell command."""
    allowed_keys = {"PATH", "HOME", "LANG", "LC_ALL", "VIRTUAL_ENV", "UV_CACHE_DIR"}
    env = {k: v for k, v in os.environ.items() if k in allowed_keys}
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE_ROOT,
            env=env,
            timeout=60,
            capture_output=True,
            text=True
        )
        output = (result.stdout + result.stderr)[:4000]
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out"
    except Exception as e:
        return f"Error: {e}"
