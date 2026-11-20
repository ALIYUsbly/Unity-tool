"""The Android 'bootloader message' written to the misc partition to tell the
bootloader/recovery what to do on the next boot - here, run a normal
recovery wipe (the same thing "Wipe data/factory reset" in the recovery menu
does). Struct and field sizes from AOSP's
bootable/recovery/bootloader_message/include/bootloader_message/bootloader_message.h

    struct bootloader_message {
        char command[32];
        char status[32];
        char recovery[768];
        char stage[32];
        char reserved[224];
    };                        // 1088 bytes

Only used by a tab's builder together with a backup of the real misc
partition (see qualcomm.py's BACKUP MISC PARTITION / SAFE FORMAT actions):
the backup's bytes AFTER this struct are left untouched, so any A/B
slot-control data some devices also keep on the misc partition survives.
"""

COMMAND_SIZE = 32
STATUS_SIZE = 32
RECOVERY_SIZE = 768
STAGE_SIZE = 32
RESERVED_SIZE = 224
MESSAGE_SIZE = COMMAND_SIZE + STATUS_SIZE + RECOVERY_SIZE + STAGE_SIZE + RESERVED_SIZE  # 1088


def _field(text: bytes, size: int) -> bytes:
    if len(text) > size:
        raise ValueError(f"{text!r} is longer than {size} bytes")
    return text.ljust(size, b"\0")


def build_wipe_data_message() -> bytes:
    """The message that makes the bootloader boot into recovery and recovery
    perform a normal data wipe, then reboot to system on its own."""
    command = _field(b"boot-recovery", COMMAND_SIZE)
    status = _field(b"", STATUS_SIZE)
    recovery = _field(b"recovery\n--wipe_data\n", RECOVERY_SIZE)
    stage = _field(b"", STAGE_SIZE)
    reserved = _field(b"", RESERVED_SIZE)
    msg = command + status + recovery + stage + reserved
    assert len(msg) == MESSAGE_SIZE
    return msg


def patch_misc_backup(backup_path: str, out_path: str) -> int:
    """Read a misc-partition backup, overwrite only the first MESSAGE_SIZE
    bytes with the wipe-data message, write the result to out_path. Returns
    the file size. Raises ValueError if the backup is smaller than the
    message (wrong partition / truncated read)."""
    with open(backup_path, "rb") as f:
        data = bytearray(f.read())
    if len(data) < MESSAGE_SIZE:
        raise ValueError(
            f"backup is only {len(data)} bytes, expected at least "
            f"{MESSAGE_SIZE} - re-read the misc partition first")
    data[:MESSAGE_SIZE] = build_wipe_data_message()
    with open(out_path, "wb") as f:
        f.write(bytes(data))
    return len(data)
