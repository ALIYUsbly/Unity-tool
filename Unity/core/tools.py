"""Resolve external tools and construct QProcess commands.

Development mode can use the original Python scripts. Compiled mode launches
only the bundled native executables listed in PROTECTED_TOOL_BINARIES.
"""
import os
import shutil
import sys

from Unity.config import (
    C_SCRIPT_DIRS,
    C_TOOLS_DIR,
    DEVICES_DIR,
    LOCAL_TOOL_DIRS,
    PROTECTED_TOOL_BINARIES,
    PROTECTED_TOOLS_DIR,
    SCRIPT_DIRS,
    SYS_TOOLS,
    TOOLS_DIR,
    REPO_DIR,
    IS_COMPILED,
)


def is_system_tool(script):
    return script in SYS_TOOLS


def _protected_binary_path(script):
    """Return the bundled executable for a tool's original script name."""
    name = PROTECTED_TOOL_BINARIES.get(script)
    if not name:
        return None

    if sys.platform == "win32" and not name.lower().endswith(".exe"):
        name += ".exe"

    path = os.path.join(PROTECTED_TOOLS_DIR, name)
    if os.path.isfile(path) and os.access(path, os.X_OK):
        return path
    return None


def resolve_tool(script):
    """Return (path, working_dir), or (None, None) if unavailable."""

    # Compiled releases must use bundled native tools, never source .py files.
    if IS_COMPILED and script in PROTECTED_TOOL_BINARIES:
        path = _protected_binary_path(script)
        return (path, PROTECTED_TOOLS_DIR) if path else (None, None)

    # System tools (adb, fastboot, etc.) execute directly.
    if is_system_tool(script):
        exe = None

        for sub in LOCAL_TOOL_DIRS.get(script, []):
            candidate = os.path.join(TOOLS_DIR, *sub.split("/"), script)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                exe = candidate
                break

        exe = exe or shutil.which(script)

        if not exe:
            for sub in ("platform-tools", ""):
                candidate = os.path.join(TOOLS_DIR, sub, script) if sub else os.path.join(TOOLS_DIR, script)
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    exe = candidate
                    break

        return (exe, TOOLS_DIR) if exe else (None, None)

    # A compiled build must never fall back to external Python or source files.
    if IS_COMPILED:
        return None, None

    # Original proprietary scripts are available only in development mode.
    for sub in C_SCRIPT_DIRS.get(script, []):
        directory = os.path.join(C_TOOLS_DIR, *sub.split("/")) if sub else C_TOOLS_DIR
        path = os.path.join(directory, script)
        if os.path.isfile(path):
            return path, directory

    # Third-party Python scripts are used only in development mode.
    for sub in SCRIPT_DIRS.get(script, []):
        directory = os.path.join(TOOLS_DIR, *sub.split("/"))
        path = os.path.join(directory, script)
        if os.path.isfile(path):
            return path, directory

    return None, None


def python_for(cwd):
    """Find Python for development mode only."""
    if IS_COMPILED:
        return None

    candidates = []

    configured = os.environ.get("TSM_PYTHON")
    if configured:
        candidates.append(configured)

    if os.name == "nt":
        candidates.extend([
            os.path.join(cwd, ".venv", "Scripts", "python.exe"),
            os.path.join(cwd, ".venv", "Scripts", "python"),
        ])
    else:
        candidates.extend([
            os.path.join(cwd, ".venv", "bin", "python"),
            os.path.join(cwd, ".venv", "bin", "python3"),
        ])

    candidates.append(sys.executable)
    candidates.extend([shutil.which("python3"), shutil.which("python")])

    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.sep in candidate:
            candidate = os.path.abspath(candidate)
        if candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None


def make_command(script, args):
    """Return (program, argv, cwd, env), or None if the tool cannot be found."""
    path, cwd = resolve_tool(script)
    if not path:
        return None

    if is_system_tool(script) or (
        IS_COMPILED and script in PROTECTED_TOOL_BINARIES
    ):
        return path, list(args), cwd, None

    interpreter = python_for(cwd)
    if not interpreter:
        return None

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [REPO_DIR, env.get("PYTHONPATH")])
    )
    return interpreter, ["-u", path] + list(args), cwd, env


def resolve_profile_path(rel):
    """Resolve a profile from bundled devices/ or supported vendor folders."""
    if not rel:
        return None

    if os.path.isabs(rel):
        return rel if os.path.isfile(rel) else None

    bases = (
        DEVICES_DIR,
        *(os.path.join(TOOLS_DIR, d)
          for d in ("mtkclient", "edl", "spd", "spdclient")),
    )

    for base in bases:
        candidate = os.path.join(base, rel)
        if os.path.isfile(candidate):
            return candidate

    return None
