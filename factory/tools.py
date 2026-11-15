import os
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())).resolve()

FORBIDDEN_DIRS = [
    WORKSPACE_ROOT / "factory",
    WORKSPACE_ROOT / ".github",
    WORKSPACE_ROOT / ".git",
]

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache"}

MAX_FILE_SIZE = 1_000_000
MAX_MATCHES = 50
MAX_LINE_LENGTH = 200


def _is_safe(path: Path) -> bool:
    """Ensure path is within the workspace."""
    try:
        path.resolve().relative_to(WORKSPACE_ROOT)
        return True
    except ValueError:
        return False


def _is_forbidden(target: Path) -> bool:
    """Ensure path is not inside a protected directory (factory/, .github/, .git/)."""
    for forbidden in FORBIDDEN_DIRS:
        if target == forbidden or forbidden in target.parents:
            return True
    return False


def list_dir(path: str) -> str:
    """List the contents of a directory.

    Args:
        path: Directory path relative to the repository root, e.g. "." or "src".
    Returns:
        One entry per line, sorted; directories have a trailing "/".
        Returns an error string on failure.
    """
    target = (WORKSPACE_ROOT / path).resolve()
    if not _is_safe(target):
        return "Error: Path outside workspace"
    if _is_forbidden(target):
        return "Error: Access to forbidden directory"
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
    """Read the full text content of a file (truncated to 20000 characters).

    Args:
        path: File path relative to the repository root, e.g. "src/main.py".
    Returns:
        The file content, or an error string on failure.
    """
    target = (WORKSPACE_ROOT / path).resolve()
    if not _is_safe(target):
        return "Error: Path outside workspace"
    if _is_forbidden(target):
        return "Error: Access to forbidden directory"
    if not target.is_file():
        return "Error: Not a file"
    try:
        content = target.read_text(encoding='utf-8')
        return content[:20000]
    except Exception as e:
        return f"Error: {e}"

def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories.

    Args:
        path: File path relative to the repository root, e.g. "src/main.py".
        content: The complete new content of the file.
    Returns:
        "Success" or an error string.
    """
    target = (WORKSPACE_ROOT / path).resolve()

    # Security checks
    if not _is_safe(target):
        return "Error: Path outside workspace"
    if _is_forbidden(target):
        return "Error: Writing to forbidden directory"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return "Success"
    except Exception as e:
        return f"Error: {e}"

def replace_in_file(path: str, old: str, new: str) -> str:
    """Replace a unique text fragment in a file.

    Args:
        path: File path relative to the repository root, e.g. "src/main.py".
        old: The exact text to replace. Must be non-empty and occur exactly once.
        new: The text to replace it with.
    Returns:
        "Success" or an error string ("text not found" / "text occurs N times").
    """
    target = (WORKSPACE_ROOT / path).resolve()
    if not _is_safe(target):
        return "Error: Path outside workspace"
    if _is_forbidden(target):
        return "Error: Writing to forbidden directory"
    if not target.is_file():
        return "Error: Not a file"
    if not old:
        return "Error: old text is empty"

    try:
        content = target.read_text(encoding='utf-8')
        count = content.count(old)
        if count == 0:
            return "Error: text not found"
        if count > 1:
            return f"Error: text occurs {count} times, add more context to make it unique"
        target.write_text(content.replace(old, new, 1), encoding='utf-8')
        return "Success"
    except Exception as e:
        return f"Error: {e}"

def search_files(pattern: str, path: str = ".") -> str:
    """Search for a case-sensitive plain-text pattern in files under a directory.

    Args:
        pattern: Literal text to search for (not a regular expression).
        path: Directory to search in, relative to the repository root. Defaults to ".".
    Returns:
        Up to 50 matches as "relative/path:line_number:line text", one per line.
        Returns "No matches" when nothing is found.
    """
    if not pattern:
        return "Error: pattern is empty"

    root = (WORKSPACE_ROOT / path).resolve()
    if not _is_safe(root):
        return "Error: Path outside workspace"
    if _is_forbidden(root):
        return "Error: Access to forbidden directory"
    if not root.is_dir():
        return "Error: Not a directory"

    matches = []
    try:
        for file in root.rglob("*"):
            if not file.is_file():
                continue
            if any(part in SKIP_DIRS for part in file.relative_to(WORKSPACE_ROOT).parts):
                continue
            try:
                if file.stat().st_size > MAX_FILE_SIZE:
                    continue
                text = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            rel = file.relative_to(WORKSPACE_ROOT).as_posix()
            for lineno, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    matches.append(f"{rel}:{lineno}:{line.strip()[:MAX_LINE_LENGTH]}")
                    if len(matches) >= MAX_MATCHES:
                        matches.append("... truncated, refine the pattern")
                        return "\n".join(matches)
    except Exception as e:
        return f"Error: {e}"

    if not matches:
        return "No matches"
    return "\n".join(matches)

def run_command(command: str) -> str:
    """Execute a shell command inside the workspace.

    Args:
        command: The shell command to run, e.g. "pytest -q".
    Returns:
        Combined stdout and stderr (truncated to 4000 characters), or an error string.
    """
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
