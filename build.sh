#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"

BUILD_DIR="protected-tools/build"
RELEASE_DIR="protected-tools/release"
OUTPUT_DIR="release-build"

echo "======================================"
echo " TSM ONEFILE BUILD"
echo "======================================"

rm -rf "$BUILD_DIR" "$RELEASE_DIR" "$OUTPUT_DIR"
mkdir -p "$BUILD_DIR" "$RELEASE_DIR" "$OUTPUT_DIR"

compile_tool() {
    tool_name="$1"
    source_file="$2"
    shift 2

    if [ ! -f "$source_file" ]; then
        echo "ERROR: required tool source not found: $source_file" >&2
        exit 1
    fi

    echo
    echo "[BUILD] $tool_name from $source_file"

    uv run nuitka \
        --standalone \
        --onefile \
        --output-dir="$BUILD_DIR" \
        --output-filename="$tool_name" \
        "$@" \
        "$source_file"

    if [ ! -f "$BUILD_DIR/$tool_name" ]; then
        echo "ERROR: Nuitka did not create $BUILD_DIR/$tool_name" >&2
        exit 1
    fi

    cp "$BUILD_DIR/$tool_name" "$RELEASE_DIR/$tool_name"
    chmod 755 "$RELEASE_DIR/$tool_name"
}

find_first_file() {
    for candidate in "$@"; do
        if [ -f "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

# Protected first-party tools.
compile_tool unisoc_diag \
    Unity/c_vendor/unisoc_diag/unisoc_diag.py

compile_tool meta_readonly \
    Unity/c_vendor/meta/meta_readonly.py

# Third-party Python entry points are compiled too, so the target host
# does not need a separately installed Python interpreter.
EDL_SOURCE="$(find_first_file \
    vendor/edl/edl.py \
    vendor/mtkclient/edl/edl.py)" || {
        echo "ERROR: could not locate EDL entry point." >&2
        exit 1
    }
compile_tool edl "$EDL_SOURCE"

MTK_SOURCE="$(find_first_file \
    vendor/mtkclient/mtk.py)" || {
        echo "ERROR: could not locate MTKClient entry point." >&2
        exit 1
    }
compile_tool mtk "$MTK_SOURCE"

# SPD is optional in the current configuration; compile it if present.
SPD_SOURCE="$(find_first_file \
    vendor/spd/spd.py \
    vendor/spdclient/spd.py \
    vendor/mtkclient/spd.py \
    vendor/mtkclient/SpdClient/spd.py)" || SPD_SOURCE=""

if [ -n "$SPD_SOURCE" ]; then
    compile_tool spd "$SPD_SOURCE"
else
    echo "WARNING: SPD entry point not found; SPD will not be available in this release."
    rm -f "$RELEASE_DIR/spd"
fi

# MTP trigger is configured as a feature; compile it if present.
MTP_SOURCE="$(find Unity/c_vendor -type f -name mtp_trigger.py -print -quit 2>/dev/null || true)"
if [ -n "$MTP_SOURCE" ] && [ -f "$MTP_SOURCE" ]; then
    compile_tool mtp_trigger "$MTP_SOURCE"
else
    echo "WARNING: mtp_trigger.py not found; MTP trigger will not be available."
    rm -f "$RELEASE_DIR/mtp_trigger"
fi

echo
echo "[BUILD] Compiling TSM GUI as onefile..."

# Nuitka deliberately excludes .py files from data-dir inclusion because
# Python source is code, not data. Entry points above are compiled separately.
# This option includes vendor non-code assets (loaders, JSON, binaries, etc.).
uv run nuitka \
    --standalone \
    --onefile \
    --enable-plugin=pyside6 \
    --include-package=Unity \
    --include-package=customtkinter \
    --include-data-dir=vendor=vendor \
    --include-data-dir=Unity/devices=Unity/devices \
    --include-data-dir="$RELEASE_DIR"=protected-tools \
    --output-dir="$OUTPUT_DIR" \
    --output-filename=Unity.bin \
    Unity

if [ ! -f "$OUTPUT_DIR/Unity.bin" ]; then
    echo "ERROR: final TSM binary was not created." >&2
    exit 1
fi

echo
echo "======================================"
echo " BUILD COMPLETED"
echo "======================================"
ls -lh "$OUTPUT_DIR/Unity.bin"
echo "Output: $ROOT/$OUTPUT_DIR/Unity.bin"
echo
echo "Packaged protected tools:"
ls -lh "$RELEASE_DIR"
