"""Paths and constants shared by the whole app."""

import os
import re
import sys


# ============================================================
# 1. BASE PATH RESOLUTION
# ============================================================

# Nuitka's python_runtime_dir contains the files bundled inside the program.
# In --onefile mode this is the extraction directory, not the directory
# containing the outer Unity.bin executable.
try:
    _NUITKA_COMPILED = __compiled__
except NameError:
    _NUITKA_COMPILED = None

IS_COMPILED = _NUITKA_COMPILED is not None

if IS_COMPILED:
    _runtime_dir = getattr(_NUITKA_COMPILED, "python_runtime_dir", None)
    if not _runtime_dir:
        raise RuntimeError(
            "Nuitka runtime directory is unavailable; cannot locate bundled TSM files."
        )

    RUNTIME_DIR = os.path.abspath(_runtime_dir)
    REPO_DIR = RUNTIME_DIR
    PKG_DIR = os.path.join(RUNTIME_DIR, "Unity")
else:
    PKG_DIR = os.path.dirname(os.path.abspath(__file__))
    REPO_DIR = os.path.dirname(PKG_DIR)
    RUNTIME_DIR = REPO_DIR


DEVICES_DIR = os.path.join(PKG_DIR, "devices")
PROFILES_DIR = os.path.join(DEVICES_DIR, "profiles")
LOADERS_DIR = os.path.join(DEVICES_DIR, "loaders")


# ============================================================
# 2. TOOL DIRECTORIES
# ============================================================

# Non-code assets from third-party tool trees are bundled here.
# Python entry points are compiled to native executables by build.sh.
TOOLS_DIR = (
    os.environ.get("TSM_TOOLS_DIR")
    or os.path.join(RUNTIME_DIR, "vendor")
)

# Original proprietary Python scripts are development-only.
C_TOOLS_DIR = (
    os.environ.get("C_TSM_TOOLS_DIR")
    or os.path.join(PKG_DIR, "c_vendor")
)

# Compiled CLI tools are embedded under runtime/protected-tools/.
PROTECTED_TOOLS_DIR = (
    os.environ.get("TSM_PROTECTED_TOOLS_DIR")
    or os.path.join(RUNTIME_DIR, "protected-tools")
)

# Keys are the original script names used by the existing application.
# Values are executable names placed in protected-tools/ by build.sh.
PROTECTED_TOOL_BINARIES = {
    "unisoc_diag.py": "unisoc_diag",
    "meta.py": "meta",
    "edl.py": "edl",
    "mtk.py": "mtk",
    "spd.py": "spd",
    "mtp_trigger.py": "mtp_trigger",
}


# ============================================================
# 3. BRANDS / PLATFORMS
# ============================================================

BRANDS = [
    "Samsung",
    "Huawei",
    "Oppo",
    "Vivo",
    "Xiaomi",
    "Lg",
    "Nokia",
    "Lenovo",
    "Apple",
    "Infinix",
    "Tecno",
]


# ============================================================
# 4. PARTITION DEFINITIONS
# ============================================================

QCOM_EFS = [
    "modemst1",
    "modemst2",
    "fsg",
    "fsc",
]

MTK_NV = [
    "nvram",
    "nvdata",
    "protect1",
    "protect2",
    "proinfo",
]

MTK_NV_HINT = ", ".join(MTK_NV)

SPD_NV = [
    "fixnv1",
    "fixnv2",
    "runtimenv1",
    "runtimenv2",
    "prodnv",
]

SPD_NV_HINT = ", ".join(SPD_NV)


# ============================================================
# 5. BACKUP DIRECTORY
# ============================================================

if IS_COMPILED:
    # Do not store user backups inside the temporary onefile extraction tree.
    if sys.platform == "win32":
        _user_data_root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        _default_backup_dir = os.path.join(_user_data_root, "TSM", "backups")
    else:
        _user_data_root = (
            os.environ.get("XDG_DATA_HOME")
            or os.path.join(os.path.expanduser("~"), ".local", "share")
        )
        _default_backup_dir = os.path.join(_user_data_root, "Unity", "backups")
else:
    _default_backup_dir = os.path.join(REPO_DIR, "backups")

BACKUP_DIR = os.environ.get("TSM_BACKUP_DIR") or _default_backup_dir


# ============================================================
# 6. META SNAPSHOT PROPERTIES
# ============================================================

META_SNAPSHOT_PROPS = (
    "ro.build.display.id",
    "ro.build.fingerprint",
    "ro.product.model",
)


# ============================================================
# 7. ANDROID SPARSE IMAGE / FILE COMMANDS
# ============================================================

SPARSE_MAGIC = b"\x3a\xff\x26\xed"

WRITE_CMDS_WITH_FILE = {
    "w",
    "writepart",
    "write",
}

READ_CMDS_WITH_FILE = {
    "r",
    "readpart",
    "read",
}


# ============================================================
# 8. SYSTEM EXECUTABLE TOOLS
# ============================================================

SYS_TOOLS = {
    "adb",
    "fastboot",
    "heimdall",
    "tar",
    "lz4",
    "ideviceinfo",
    "idevicediagnostics",
    "idevicebackup2",
    "idevicerestore",
    "idevicecrashreport",
}


LOCAL_TOOL_DIRS = {
    "heimdall": [
        "Heimdall/build/bin",
        "heimdall/build/bin",
        "Heimdall/bin",
        "heimdall/bin",
    ],
}


# ============================================================
# 9. THIRD-PARTY PYTHON TOOL LOCATIONS (DEVELOPMENT MODE)
# ============================================================

SCRIPT_DIRS = {
    "mtk.py": [
        "mtkclient",
    ],
    "edl.py": [
        "edl",
        "mtkclient/edl",
    ],
    "spd.py": [
        "spd",
        "spdclient",
        "mtkclient/spd",
        "mtkclient/SpdClient",
        "mtkclient",
    ],
}


# ============================================================
# 10. CUSTOM PYTHON TOOL LOCATIONS (DEVELOPMENT MODE)
# ============================================================

C_SCRIPT_DIRS = {
    "mtp_trigger.py": [
        "mtpclient",
        "mtptool",
        "",
    ],
    "unisoc_diag.py": [
        "unisocdiag",
        "unisoc_diag",
        "",
    ],
    "meta.py": [
        "meta",
    ],
}


# ============================================================
# 11. LOGGING
# ============================================================

PROGRESS_RE = re.compile(r"\d{1,3}(?:\.\d+)?\s*%")
MAX_LOG_LINES = 3000
