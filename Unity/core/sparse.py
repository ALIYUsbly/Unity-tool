#!/usr/bin/env python3
"""
sparse2raw.py - convert an Android sparse image (system.img, vendor.img ...) to a RAW
image, with no extra tools. Same job as `simg2img`.

Why: scatter ROM packs ship system.img in sparse format. mtkclient writes the file
byte-for-byte, so a sparse system.img lands on the phone as junk and it bootloops.
The partition must receive the RAW image.

Use:   python sparse2raw.py system.img system_raw.img
       python sparse2raw.py --check system.img       (only says sparse / raw)
As a module (Unity/core/sparse.py):  is_sparse(path), unsparse(src, dst), raw_for(path)
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW, CHUNK_FILL, CHUNK_DONT_CARE, CHUNK_CRC32 = 0xCAC1, 0xCAC2, 0xCAC3, 0xCAC4
COPY_SIZE = 8 << 20


def is_sparse(path) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError:
        return False
    return len(head) == 4 and struct.unpack("<I", head)[0] == SPARSE_MAGIC


def _copy(src, dst, n):
    while n > 0:
        buf = src.read(min(COPY_SIZE, n))
        if not buf:
            raise ValueError("sparse image is truncated")
        dst.write(buf)
        n -= len(buf)


def unsparse(src_path, dst_path, progress=None) -> int:
    """Write the raw image to dst_path. Returns its size in bytes."""
    with open(src_path, "rb") as src, open(dst_path, "wb") as dst:
        hdr = src.read(28)
        if len(hdr) < 28:
            raise ValueError("not a sparse image (too short)")
        (magic, major, _minor, file_hdr, chunk_hdr, blk, total_blks, total_chunks,
         _crc) = struct.unpack("<IHHHHIIII", hdr)
        if magic != SPARSE_MAGIC:
            raise ValueError("not an Android sparse image")
        if major != 1:
            raise ValueError(f"unsupported sparse major version {major}")
        src.seek(file_hdr)
        blocks_done = 0
        for i in range(total_chunks):
            ch = src.read(12)
            if len(ch) < 12:
                raise ValueError("sparse image is truncated (chunk header)")
            ctype, _rsv, csz, tsz = struct.unpack("<HHII", ch)
            if chunk_hdr > 12:
                src.read(chunk_hdr - 12)
            nbytes = csz * blk
            if ctype == CHUNK_RAW:
                if tsz - chunk_hdr != nbytes:
                    raise ValueError(f"chunk {i}: bad raw size")
                _copy(src, dst, nbytes)
            elif ctype == CHUNK_FILL:
                pat = src.read(4)
                if len(pat) < 4:
                    raise ValueError("sparse image is truncated (fill)")
                if pat == b"\x00\x00\x00\x00":
                    dst.seek(nbytes, os.SEEK_CUR)          # hole = zeros
                else:
                    block = pat * (blk // 4)
                    for _ in range(csz):
                        dst.write(block)
            elif ctype == CHUNK_DONT_CARE:
                dst.seek(nbytes, os.SEEK_CUR)
            elif ctype == CHUNK_CRC32:
                src.read(4)
            else:
                raise ValueError(f"chunk {i}: unknown type {hex(ctype)}")
            if ctype != CHUNK_CRC32:
                blocks_done += csz
            if progress and i % 64 == 0:
                progress(blocks_done, total_blks)
        if blocks_done != total_blks:
            raise ValueError(f"block count mismatch ({blocks_done} != {total_blks})")
        dst.truncate(total_blks * blk)                     # also covers a trailing hole
        return total_blks * blk


def raw_for(path, cache_dir=None, progress=None) -> str:
    """Return a path that is safe to flash: `path` if already raw, else a converted copy."""
    path = str(path)
    if not is_sparse(path):
        return path
    cache = Path(cache_dir or Path.home() / ".cache" / "Unity" / "unsparse")
    cache.mkdir(parents=True, exist_ok=True)
    src = Path(path)
    out = cache / f"{src.stem}.{int(src.stat().st_mtime)}.{src.stat().st_size}.raw"
    if out.exists() and out.stat().st_size > 0:
        return str(out)                                    # already converted
    tmp = out.with_suffix(".part")
    unsparse(path, tmp, progress)
    tmp.replace(out)
    return str(out)


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) == 2 and a[0] == "--check":
        print("SPARSE (convert before flashing)" if is_sparse(a[1]) else "raw (ok to flash)")
        return 0
    if len(a) != 2:
        print(__doc__)
        return 1
    if not is_sparse(a[0]):
        print(f"{a[0]} is already a raw image - nothing to convert.")
        return 0

    def show(done, total):
        print(f"\r  {done * 100 // max(total, 1)}%", end="", flush=True)

    size = unsparse(a[0], a[1], show)
    print(f"\nWrote {a[1]}  ({size} bytes). Flash THIS file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
