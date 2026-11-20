#!/usr/bin/env python3
"""
meta_fixed_v13.py - MediaTek META mode CLI for Transsion MTK devices.

Confirmed working on real hardware (KF7j, KM7j, X657):
  - META entry (preloader -> METAMETA -> ATEM0001 -> re-enumerate as 0e8d:2007)
  - Session open (0x08), device ID (0x7B), getprop (0x89), read-file (0xA3),
    write-file (0xA3 mode 02), shell (0x79 mode 03)
  - Full device-info report (matches AndroidUtility output)
  - Factory reset via shell dd on named userdata partition  (factory_reset_dd)
  - Factory reset via mode-01 shell frame                   (factory_reset_mode01)
  - Partition table gathering (auto-discovered from /sys/block and by-name)
  - FRP clearing via runtime-discovered frp/para start LBAs (frp-clear)

v13 changes:
  - gather_partitions(): reads /sys/block/mmcblk0/*/start + by-name symlinks,
    builds name -> {partnum, start, size}. Read-only, safe.
  - frp_clear(): uses gather_partitions() to find frp/para start LBAs, then
    dd zeros 4 KB at each. No hardcoded offsets. Dry-run by default.

Removed from v11 (each bricked or hung a device in testing):
  - factory_reset_safe()      - fabricated BCB, bricked X657
  - frp_and_factory_reset()   - hardcoded KF7j offsets, bricked X657
  - _restore_para_from_raw()  - dd if=mmcblk0 of=para hung on X657
"""

import argparse, glob, sys, termios, time, base64
import usb.core, usb.util
import serial

VID = 0x0E8D
PID_PRELOADER = 0x2000
PID_META = 0x2007
USB_TIMEOUT_MS = 500
READY = b"READY"
METAMETA = b"METAMETA"
METASLA = b"METASLA"
ATEM0001 = b"ATEM0001"
ATEMATEM = b"ATEMATEM"
DISCONNECT = b"DISCONNECT"
SYNC_MAGIC = bytes.fromhex("acdbcfe5")

META_SYNC = 0x55
META_ESCAPE = 0x5A
OP_SESSION_OPEN = 0x08
OP_SESSION_CLOSE = 0x0A
OP_FILE_IO = 0xA3
OP_SHELL_EXEC = 0x79

PARAM_WRITE = (2).to_bytes(4, "little")
PARAM_READ = (3).to_bytes(4, "little")
CHUNK = 0x6000
CHUNK_PREFIX = bytes.fromhex("0060010000000100")
CHUNK_HDR_LEN = 8
FLAG_FIRST = 3
FLAG_NEXT = 2


class MetaError(Exception):
    pass


def mtk_escape(d):
    out = bytearray()
    for b in d:
        if b == 0x5A:
            out.extend([0x5A, 0x5A])
        elif b == 0x55:
            out.extend([0x5A, 0x01])
        else:
            out.append(b)
    return bytes(out)


def mtk_unescape(d):
    out = bytearray()
    i = 0
    while i < len(d):
        if d[i] == 0x5A and i + 1 < len(d):
            nxt = d[i + 1]
            if nxt == 0x5A:
                out.append(0x5A)
            elif nxt == 0x01:
                out.append(0x55)
            else:
                out.extend([d[i], nxt])
            i += 2
        else:
            out.append(d[i])
            i += 1
    return bytes(out)


def meta_checksum(f):
    c = 0
    for b in f:
        c ^= b
    return c


def build_meta_frame(token, opcode, data=b"", peer_data=b"", is_reply=False):
    body = token.to_bytes(2, "little") + opcode.to_bytes(2, "little") + data + peer_data
    local_len = 4 + len(data)
    peer_len = len(peer_data)
    type_byte = 0x60 if is_reply else 0x66
    length = 2 + 2 + len(body) + (1 if is_reply else 0)
    frame = (bytes([0x55]) + length.to_bytes(2, "big") + bytes([type_byte])
             + local_len.to_bytes(2, "little") + peer_len.to_bytes(2, "little") + body)
    chk = meta_checksum(frame)
    frame_with_chk = frame + bytes([chk])
    return bytes([0x55]) + mtk_escape(frame_with_chk[1:])


def parse_meta_frame(wire):
    if not wire or wire[0] != 0x55:
        return None
    unescaped = mtk_unescape(wire[1:])
    if len(unescaped) < 8:
        return None
    full = bytes([0x55]) + unescaped
    length = int.from_bytes(full[1:3], "big")
    type_byte = full[3]
    local_len = int.from_bytes(full[4:6], "little")
    peer_len = int.from_bytes(full[6:8], "little")
    is_reply = (type_byte == 0x60)
    body_len = length - 4 - (1 if is_reply else 0)
    total_needed = 8 + body_len + 1
    if len(full) < total_needed:
        return None
    body = full[8:8 + body_len]
    if len(body) < 4:
        return None
    return {
        "local_len": local_len,
        "peer_len": peer_len,
        "token": int.from_bytes(body[0:2], "little"),
        "opcode": int.from_bytes(body[2:4], "little"),
        "data": body[4:],
        "is_reply": is_reply,
        "raw_len": total_needed,
    }


def find_device(pid):
    return usb.core.find(idVendor=VID, idProduct=pid)


def wait_for_ttyacm(timeout=10.0, verbose=False):
    sys.stderr.write("[meta] waiting for /dev/ttyACM*...\n")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ports = sorted(glob.glob("/dev/ttyACM*"))
        if ports:
            if verbose:
                print(f"[meta] found {ports[0]}", file=sys.stderr)
            return ports[0]
        time.sleep(0.1)
    return None


def configure_raw_tty(ser, verbose=False):
    try:
        attrs = termios.tcgetattr(ser.fd)
        attrs[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY
                      | termios.ICRNL | termios.INLCR | termios.IGNCR
                      | termios.ISTRIP | termios.INPCK)
        attrs[1] &= ~termios.OPOST
        attrs[2] &= ~termios.CRTSCTS
        attrs[3] &= ~(termios.ICANON | termios.ECHO | termios.ECHOE
                      | termios.ECHOK | termios.ECHONL | termios.ISIG)
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(ser.fd, termios.TCSANOW, attrs)
        termios.tcflush(ser.fd, termios.TCIOFLUSH)
    except Exception as e:
        if verbose:
            print(f"[meta] raw tty config failed: {e}", file=sys.stderr)


def _handle_atem(ep_in, ep_out, verbose=False, label="ATEM"):
    sys.stderr.write(f"[meta] handling {label} sequence\n")
    try:
        ep_out.write(bytes.fromhex("0400000001000000010000c0"), timeout=USB_TIMEOUT_MS)
        time.sleep(0.02)
        ep_out.write(bytes.fromhex("0400000001000000010000c0"), timeout=USB_TIMEOUT_MS)
        time.sleep(0.02)
        ep_out.write(bytes.fromhex("0600000001000000010000c000800000"), timeout=USB_TIMEOUT_MS)
        try:
            ready = bytes(ep_in.read(13, timeout=2000))
            if verbose:
                print(f"[meta] <- {ready!r} ({ready.hex()})", file=sys.stderr)
        except Exception:
            pass
        ep_out.write(DISCONNECT, timeout=USB_TIMEOUT_MS)
        sys.stderr.write(f"[meta] {label} sequence complete\n")
        return True
    except usb.core.USBError as e:
        sys.stderr.write(f"[meta] {label} error: {e}\n")
        return False


def enter_meta_mode(timeout=30.0, verbose=False):
    if find_device(PID_META) is not None:
        sys.stderr.write("[meta] device already in Meta mode\n")
        return True
    sys.stderr.write("[meta] waiting for Preloader (0e8d:2000)...\n")
    deadline = time.monotonic() + timeout
    dev = None
    while time.monotonic() < deadline:
        if find_device(PID_META) is not None:
            sys.stderr.write("[meta] Meta mode already active\n")
            return True
        dev = usb.core.find(idVendor=VID, idProduct=PID_PRELOADER)
        if dev is not None:
            break
        time.sleep(0.02)
    if dev is None:
        sys.stderr.write("[meta] Preloader did not appear\n")
        return False
    sys.stderr.write(f"[meta] Preloader found at addr {dev.address}\n")
    try:
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except (NotImplementedError, usb.core.USBError):
            pass
        dev.set_configuration()
        cfg = dev.get_active_configuration()
        intf = cfg[(0, 0)]
        ep_out = usb.util.find_descriptor(intf, custom_match=lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        ep_in = usb.util.find_descriptor(intf, custom_match=lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        if not ep_in or not ep_out:
            raise MetaError("endpoints not found")
    except Exception as e:
        sys.stderr.write(f"[meta] open error: {e}\n")
        return False
    sys.stderr.write("[meta] waiting for READY...\n")
    ready = False
    rd_dead = time.monotonic() + 10.0
    while time.monotonic() < rd_dead:
        try:
            data = bytes(ep_in.read(4096, timeout=500))
            if data:
                if verbose:
                    print(f"[meta] <- {data!r} ({data.hex()})", file=sys.stderr)
                if READY in data:
                    ready = True
                    break
        except usb.core.USBTimeoutError:
            continue
        except usb.core.USBError as e:
            sys.stderr.write(f"[meta] read error: {e}\n")
            return False
    if not ready:
        sys.stderr.write("[meta] READY never arrived\n")
        return False
    sys.stderr.write("[meta] got READY, sending METAMETA\n")
    try:
        ep_out.write(METAMETA, timeout=USB_TIMEOUT_MS)
    except usb.core.USBError as e:
        sys.stderr.write(f"[meta] METAMETA send failed: {e}\n")
        return False
    sys.stderr.write("[meta] watching for response...\n")
    resp_dead = time.monotonic() + 8.0
    while time.monotonic() < resp_dead:
        try:
            data = bytes(ep_in.read(4096, timeout=500))
            if data:
                if verbose:
                    print(f"[meta] <- {data!r} ({data.hex()})", file=sys.stderr)
                if ATEM0001 in data:
                    _handle_atem(ep_in, ep_out, verbose, "ATEM0001")
                    break
                if METASLA in data:
                    sys.stderr.write("[meta] SLA required - not supported in v13\n")
                    return False
                if ATEMATEM in data:
                    _handle_atem(ep_in, ep_out, verbose, "ATEMATEM")
                    break
        except usb.core.USBTimeoutError:
            continue
        except usb.core.USBError as e:
            if verbose:
                print(f"[meta] device disconnected: {e}", file=sys.stderr)
            break
    try:
        usb.util.dispose_resources(dev)
    except Exception:
        pass
    sys.stderr.write("[meta] waiting for Meta mode (0e8d:2007)...\n")
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if find_device(PID_META) is not None:
            sys.stderr.write("[meta] Meta mode appeared\n")
            return True
        time.sleep(0.1)
    sys.stderr.write("[meta] Meta mode did not appear\n")
    return False


class MetaSerialSession:
    INFO_PROPS = [
        ("Manufacturer",      "ro.product.manufacturer",           None),
        ("Brand",             "ro.product.brand",                  None),
        ("Model",             "ro.product.model",                  None),
        ("DevName",           "ro.product.device",                 None),
        ("Name",              "ro.product.name",                   None),
        ("Board",             "ro.product.board",                  None),
        ("SKU",               "ro.boot.product.hardware.sku",      None),
        ("Build ID",          "ro.build.display.id",               "ro.build.id"),
        ("Android Ver",       "ro.build.version.release",          None),
        ("Codename",          "ro.build.version.codename",         None),
        ("Sec Patch",         "ro.build.version.security_patch",   None),
        ("Build Type",        "ro.build.type",                     None),
        ("Hardware",          "ro.hardware",                       None),
        ("Chip ID",           "ro.board.platform",                 "ro.hardware"),
        ("SW Ver",            "ro.mediatek.version.release",       "ro.build.version.incremental"),
        ("Device State",      "ro.boot.flash.locked",              None),
        ("VerifiedBootState", "ro.boot.verifiedbootstate",         None),
        ("Veritymode",        "ro.boot.veritymode",                None),
        ("CryptState",        "ro.crypto.state",                   None),
        ("CryptType",         "ro.crypto.type",                    None),
        ("A/B device",        "ro.build.ab_update",                None),
        ("Active Slot",       "ro.boot.slot_suffix",               None),
        ("SDKVer",            "ro.build.version.sdk",              None),
        ("FRP Pst",           "ro.frp.pst",                        None),
        ("Bluetooth",         "persist.vendor.btstack.bdaddr",     "ro.bt.bdaddr"),
    ]

    BT_FALLBACK_KEYS = ("persist.vendor.btstack.bdaddr", "ro.bt.bdaddr",
                        "persist.bluetooth.bdaddr")
    BT_NVRAM_PATH = "data/nvram/APCFG/APRDEB/BT_Addr"
    BT_MISS_VALUES = ("", "unknown", "null", "0", "00:00:00:00:00:00")

    def __init__(self, verbose=False, baud=115200):
        self.verbose = verbose
        self.baud = baud
        self.ser = None
        self.seq = 0
        self._rebooted = False
        self.session_id = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def _log(self, msg):
        if self.verbose:
            print(f"[meta] {msg}", file=sys.stderr, flush=True)

    def _open_serial(self, port, wait=8.0):
        deadline = time.monotonic() + wait
        while True:
            try:
                return serial.Serial(
                    port=port, baudrate=self.baud,
                    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE, timeout=0.5, write_timeout=10.0)
            except serial.SerialException as e:
                if getattr(e, "errno", None) == 13:
                    if time.monotonic() < deadline:
                        self._log(f"permission denied on {port}, waiting for udev...")
                        time.sleep(0.25)
                        continue
                    raise MetaError(
                        f"permission denied on {port} after {wait:.0f}s - "
                        f"is your user in dialout/uucp?") from e
                raise

    def open(self):
        port = wait_for_ttyacm(timeout=10.0, verbose=self.verbose)
        if port is None:
            raise MetaError("no /dev/ttyACM* device found")
        self._log(f"opening {port} @ {self.baud}")
        self.ser = self._open_serial(port)
        configure_raw_tty(self.ser, verbose=self.verbose)
        try:
            self.ser.dtr = True
            self.ser.rts = True
        except Exception:
            pass
        time.sleep(0.2)
        try:
            self.ser.read(8192)
        except Exception:
            pass
        self._log(f"opened {port}")
        self.session_start()

    def close(self):
        if self.ser and self.ser.is_open and self._rebooted:
            try:
                self.ser.close()
            except Exception:
                pass
            return
        if self.ser and self.ser.is_open:
            try:
                frame = build_meta_frame(token=self._next_seq(), opcode=0x0A, data=b"")
                self.ser.write(frame)
                self.ser.flush()
                time.sleep(0.1)
                self.ser.write(SYNC_MAGIC)
                self.ser.write(SYNC_MAGIC)
                self.ser.flush()
            except Exception:
                pass
            try:
                self.ser.close()
            except Exception:
                pass
            self._log("serial closed")

    def _next_seq(self):
        s = self.seq
        self.seq = (self.seq + 1) & 0xFFFF
        return s

    def _drain(self, seconds=0.3):
        deadline = time.monotonic() + seconds
        total = 0
        last = time.monotonic()
        while time.monotonic() < deadline:
            try:
                chunk = self.ser.read(8192)
                if chunk:
                    total += len(chunk)
                    last = time.monotonic()
                else:
                    if total > 0 and time.monotonic() - last > 0.2:
                        break
                    time.sleep(0.02)
            except Exception:
                break
        return total

    def _read_one_chunk(self, timeout=0.5):
        deadline = time.monotonic() + timeout
        buf = bytearray()
        last = time.monotonic()
        while time.monotonic() < deadline:
            try:
                chunk = self.ser.read(4096)
                if chunk:
                    buf.extend(chunk)
                    last = time.monotonic()
                else:
                    if buf and time.monotonic() - last > 0.15:
                        break
            except serial.SerialException as e:
                raise MetaError(f"read failed: {e}") from e
        return bytes(buf)

    def _split_data(self, parsed):
        extra = parsed.get("data", b"")
        local_len = parsed.get("local_len", 0)
        peer_len = parsed.get("peer_len", 0)
        local_payload_len = max(0, local_len - 4)
        if len(extra) < local_payload_len:
            return extra, b""
        local_payload = extra[:local_payload_len]
        if peer_len > 0:
            peer_payload = extra[-peer_len:] if len(extra) >= peer_len else extra[local_payload_len:]
        else:
            peer_payload = b""
        return local_payload, peer_payload

    def _find_response_frame(self, raw, expected_opcode=None):
        last = None
        i = 0
        while i < len(raw):
            start = raw.find(bytes([0x55]), i)
            if start < 0:
                break
            parsed = parse_meta_frame(raw[start:])
            if parsed is None:
                i = start + 1
                continue
            if parsed["is_reply"]:
                if expected_opcode is None:
                    last = parsed
                else:
                    if parsed["opcode"] == expected_opcode or parsed["opcode"] == expected_opcode + 1:
                        return parsed
                    last = parsed
            i = start + 1
        return last

    def session_start(self):
        self._log("session init")
        frame1 = build_meta_frame(token=1, opcode=OP_SESSION_OPEN, data=b"\x00\x00\x00\x00")
        try:
            self.ser.write(frame1)
            self.ser.flush()
        except serial.SerialException as e:
            self._log(f" write error: {e}")
            return
        time.sleep(0.1)
        self.ser.write(SYNC_MAGIC + SYNC_MAGIC)
        self.ser.flush()
        time.sleep(0.1)
        frame2 = build_meta_frame(token=2, opcode=0x7B, data=b"\x00" * 4)
        try:
            self.ser.write(frame2)
            self.ser.flush()
        except Exception:
            pass
        deadline = time.monotonic() + 2.0
        resp = bytearray()
        while time.monotonic() < deadline:
            chunk = self._read_one_chunk(timeout=0.3)
            if chunk:
                resp.extend(chunk)
                pr = self._find_response_frame(bytes(resp), expected_opcode=0x7B)
                if pr is not None:
                    local, peer = self._split_data(pr)
                    self.session_id = (peer or local)
                    break
        if self.session_id:
            self._log(f" session id (0x7C): {self.session_id.hex()}")
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception:
            pass
        self.seq = 3

    def send(self, opcode, data=b"", peer_data=b"", expect_reply=True, timeout=5.0):
        token = self._next_seq()
        frame = build_meta_frame(token=token, opcode=opcode, data=data, peer_data=peer_data)
        self._log(f"-> token={token} opcode=0x{opcode:04x} local_len={len(data)+4} peer_len={len(peer_data)}")
        try:
            self.ser.reset_input_buffer()
            self.ser.write(frame)
            self.ser.flush()
        except serial.SerialException as e:
            raise MetaError(f"write failed: {e}") from e
        if not expect_reply:
            return b""
        deadline = time.monotonic() + timeout
        raw = bytearray()
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            chunk = self._read_one_chunk(timeout=min(remaining, 0.15))
            if chunk:
                raw.extend(chunk)
                if self._find_response_frame(bytes(raw)):
                    return bytes(raw)
            else:
                if raw:
                    break
        return bytes(raw)

    def shell(self, command, timeout=60.0, idle_timeout=2.0):
        b64_cmd = base64.b64encode(command.encode()).decode()
        wrapped = f"echo '{b64_cmd}' | base64 -d | sh"
        cmd_bytes = wrapped.encode()
        if len(cmd_bytes) > 65535:
            raise MetaError(f"shell command too long ({len(cmd_bytes)}B > 65535)")
        peer_header = len(cmd_bytes).to_bytes(2, "little") + bytes.fromhex("010000000100")
        peer_data = peer_header + cmd_bytes
        data = (0).to_bytes(4, "little") + (3).to_bytes(4, "little")
        token = self._next_seq()
        frame = build_meta_frame(token=token, opcode=OP_SHELL_EXEC, data=data, peer_data=peer_data)
        self._log(f"-> shell (0x79) token={token} cmd={command[:80]!r}")
        try:
            self._drain(0.2)
            self.ser.reset_input_buffer()
            self.ser.write(frame)
            self.ser.flush()
        except serial.SerialException as e:
            raise MetaError(f"write failed: {e}") from e
        deadline = time.monotonic() + timeout
        raw_buf = bytearray()
        result = bytearray()
        last_data = time.monotonic()
        while time.monotonic() < deadline:
            chunk = self._read_one_chunk(timeout=0.5)
            if chunk:
                raw_buf.extend(chunk)
                last_data = time.monotonic()
                self._log(f"  shell: raw chunk ({len(chunk)}B): {chunk[:64].hex()}")
                pos = 0
                while True:
                    s = raw_buf.find(b"\x55", pos)
                    if s < 0:
                        break
                    pr = parse_meta_frame(bytes(raw_buf[s:]))
                    if pr is None:
                        pos = s + 1
                        continue
                    if pr["opcode"] in (0x79, 0x7A, 0x0A, 0x7B, 0x8D, 0x8E):
                        local, peer = self._split_data(pr)
                        payload = peer if peer else local
                        if len(payload) > 8 and payload[0:2] == b"\xf0\x00":
                            payload = payload[8:]
                        payload = payload.rstrip(b"\x00")
                        if payload:
                            result.extend(payload)
                    pos = s + pr["raw_len"]
            else:
                if result and time.monotonic() - last_data >= idle_timeout:
                    break
                if not result and time.monotonic() >= deadline - 1.0:
                    break
        return result.decode("utf-8", errors="replace").strip()

    def _pop_frames(self, raw, pos):
        frames = []
        while True:
            s = raw.find(b"\x55", pos)
            if s < 0:
                return frames, len(raw)
            if len(raw) - s < 12:
                return frames, s
            type_byte = raw[s + 3]
            A = int.from_bytes(raw[s + 4:s + 6], "little")
            B = int.from_bytes(raw[s + 6:s + 8], "little")
            if type_byte not in (0x60, 0x66) or A < 4:
                pos = s + 1
                continue
            total = 9 + A + B
            if len(raw) - s < total:
                return frames, s
            fr = bytes(raw[s:s + total])
            frames.append({
                "local_len": A, "peer_len": B,
                "token": int.from_bytes(fr[8:10], "little"),
                "opcode": int.from_bytes(fr[10:12], "little"),
                "data": fr[12:8 + A + B],
                "is_reply": type_byte == 0x60,
                "raw_len": total,
            })
            pos = s + total

    def read_file(self, path, timeout=120.0, idle_timeout=3.0):
        path_b = path.encode() if isinstance(path, str) else path
        data = PARAM_READ + path_b.ljust(512, b"\x00")
        token = self._next_seq()
        frame = build_meta_frame(token=token, opcode=OP_FILE_IO, data=data, peer_data=b"")
        self._log(f"-> read_file token={token} path={path!r}")
        try:
            self._drain(0.2)
            self.ser.reset_input_buffer()
            self.ser.write(frame)
            self.ser.flush()
        except serial.SerialException as e:
            raise MetaError(f"write failed: {e}") from e
        deadline = time.monotonic() + timeout
        raw = bytearray()
        pos = 0
        result = bytearray()
        last_data = time.monotonic()
        while time.monotonic() < deadline:
            chunk = self._read_one_chunk(timeout=0.5)
            if chunk:
                raw.extend(chunk)
                frames, pos = self._pop_frames(raw, pos)
                if frames:
                    last_data = time.monotonic()
                for pr in frames:
                    if not (pr["is_reply"] and pr["opcode"] in (0xA3, 0xA4)):
                        continue
                    local, peer = self._split_data(pr)
                    self._log(f"  <- read_file reply: local_len={len(local)} peer_len={len(peer)} "
                              f"local[:16]={bytes(local[:16])!r}")
                    if peer:
                        result.extend(peer)
                    elif len(local) > 12:
                        result.extend(local[12:])
                    else:
                        return bytes(result)
            else:
                if result and time.monotonic() - last_data >= idle_timeout:
                    break
        return bytes(result)

    def _write_chunks(self, path, content, total_size, timeout=60.0):
        if isinstance(path, bytes):
            path = path.decode()
        if len(path.encode()) >= 256:
            raise MetaError("path too long")
        for n, off in enumerate(range(0, len(content), CHUNK)):
            chunk = content[off:off + CHUNK]
            local = (PARAM_WRITE + path.encode().ljust(256, b"\x00")
                     + total_size.to_bytes(4, "little")
                     + (FLAG_FIRST if n == 0 else FLAG_NEXT).to_bytes(4, "little")
                     + bytes(512 - 256 - 8))
            raw = self.send(OP_FILE_IO, data=local, peer_data=CHUNK_PREFIX + chunk, timeout=timeout)
            if self._find_response_frame(raw, expected_opcode=OP_FILE_IO) is None:
                raise MetaError(f"write chunk {n} to {path}: no reply")

    def write_file(self, path, content, total_size=None, timeout=60.0):
        self._write_chunks(path, content, total_size if total_size is not None else len(content), timeout)

    def getprop(self, name):
        data = name.encode("ascii") if isinstance(name, str) else name
        data = data[:64] if len(data) > 64 else data + b"\x00" * (64 - len(data))
        raw = self.send(0x89, data=data, timeout=5.0)
        parsed = self._find_response_frame(raw, expected_opcode=0x89)
        if parsed is None:
            return ""
        val = parsed.get("data", b"")
        idx = val.find(b"\x00")
        if idx >= 0:
            val = val[:idx]
        return val.decode("ascii", errors="replace")

    def full_info(self):
        values = {}
        raw_map = {}
        for label, key, fallback in self.INFO_PROPS:
            if label == "Bluetooth":
                values[label] = self._read_bluetooth()
                raw_map[label] = {"key": key, "fallback": fallback, "value": values[label]}
                continue
            val = self.getprop(key)
            if not val and fallback:
                val = self.getprop(fallback)
            values[label] = val
            raw_map[label] = {"key": key, "fallback": fallback, "value": val}
        if values.get("Active Slot", "").startswith("_"):
            values["Active Slot"] = values["Active Slot"][1:]
        values["RNID"] = self.session_id.hex() if self.session_id else ""
        return {"values": values, "raw": raw_map}

    def _read_bluetooth(self):
        for key in self.BT_FALLBACK_KEYS:
            val = self.getprop(key)
            if val and val.lower() not in self.BT_MISS_VALUES:
                return val
        try:
            data = self.read_file(self.BT_NVRAM_PATH, timeout=5.0, idle_timeout=0.5)
            if data and len(data) >= 6:
                return ":".join(f"{b:02x}" for b in data[:6])
        except MetaError:
            pass
        return ""
    def read_partition_map_from_device(self):
        """Read partition table from the device (best-effort; often denied in meta_tst).
        Returns dict: name -> {partnum, start_lba, size} or None if not readable."""
        script = (
            'echo BEGIN_SYS; '
            'for d in /sys/block/mmcblk0/mmcblk0p*; do '
            '  p=$(basename $d); '
            '  s=$(cat $d/start 2>/dev/null); '
            '  z=$(cat $d/size 2>/dev/null); '
            '  echo "$p $s $z"; '
            'done; '
            'echo BEGIN_BYNAME; '
            'ls -la /dev/block/by-name/; '
            'echo END'
        )
        self._log("reading /sys/block + by-name (may be denied by meta_tst)")
        out = self.shell(f'({script}) 2>&1', timeout=15.0)
        self._log(f"  raw output: {out[:200]!r}...")
        parts = {}
        names = {}
        section = None
        for line in out.splitlines():
            line = line.strip()
            if line == "BEGIN_SYS":
                section = "sys"; continue
            if line == "BEGIN_BYNAME":
                section = "byname"; continue
            if line == "END":
                break
            if section == "sys" and line.startswith("mmcblk0p"):
                toks = line.split()
                if len(toks) == 3:
                    try:
                        parts[toks[0]] = int(toks[1])  # start_lba
                    except ValueError:
                        pass
            elif section == "byname" and "->" in line:
                left, _, right = line.partition("->")
                name = left.split()[-1]
                tgt = right.strip().split("/")[-1]
                if tgt.startswith("mmcblk0p"):
                    names[name] = tgt
        result = {}
        for name, partnum in names.items():
            if partnum in parts:
                result[name] = {"partnum": partnum, "start_lba": parts[partnum]}
        return result if result else None


    def frp_clear(self, frp_lba=None, para_lba=None, reboot=True, dry_run=True,
                timeout=120.0):
        """Clear FRP + para by zeroing 4 KB at each partition's start LBA.
        
        Two modes:
        - If frp_lba and para_lba are given (from the device profile JSON), uses them.
        - If not given, attempts to read from the device (usually fails on meta_tst,
            in which case it raises with a clear message).
        
        Dry-run by default — no writes unless dry_run=False.
        """

        if frp_lba is None or para_lba is None:
            sys.stderr.write("no offsets provided, trying device discovery")
            parts = self.read_partition_map_from_device()
            if not parts:
                raise MetaError(
                    "Cannot determine frp/para offsets.\n"
                    "  The device's meta_tst shell cannot read /sys or by-name "
                    "(SELinux denies it on this device family).\n"
                    "  Fix: add frp_lba and para_lba to the device profile JSON, "
                    "using the values from AndroidUtility's log "
                    "(WIPE (frp)[...LBA:0x...] → seek = LBA_decimal).\n"
                    "  Or pass --frp-seek N --para-seek N on the CLI."
                )
            if "frp" not in parts or "para" not in parts:
                raise MetaError(
                    f"partitions not found in device map. "
                    f"Available: {sorted(parts.keys())}")
            frp_lba = parts["frp"]["start_lba"]
            para_lba = parts["para"]["start_lba"]
            self._log(f"device discovery: frp_lba={frp_lba} para_lba={para_lba}")
        
        print(f"frp_lba:{frp_lba}  (byte 0x{frp_lba*512:x})")
        print(f"para_lba:{para_lba}  (byte 0x{para_lba*512:x})")
        
        if dry_run:
            print()
            print("DRY RUN — no writes performed. Re-run with --yes to zero the headers.")
            return {"frp_lba": frp_lba, "para_lba": para_lba, "written": False}
        
        out = self.shell(
            f"dd if=/dev/zero of=/dev/block/mmcblk0 bs=512 count=8 seek={frp_lba} "
            f"conv=fsync,notrunc 2>/dev/null; "
            f"dd if=/dev/zero of=/dev/block/mmcblk0 bs=512 count=8 seek={para_lba} "
            f"conv=fsync,notrunc 2>/dev/null; "
            f"sync; echo WIPE_DONE",
            timeout=timeout,
        )
        self._log(f"  wipe output: {out!r}")
        if "WIPE_DONE" not in out:
            self._log("  WIPE_DONE not received — device may have re-enumerated after the para write")
        
        if reboot:
            try:
                self.reboot()
            except Exception as e:
                self._log(f"  reboot failed (device likely re-enumerated): {e}")
        
        return {"frp_lba": frp_lba, "para_lba": para_lba, "written": True}

   

    def factory_reset_dd(self, reboot=True, timeout=120.0):
        self._log("factory_reset_dd: zeroing /dev/block/by-name/userdata (4 MB)")
        out = self.shell(
            "dd if=/dev/zero of=/dev/block/by-name/userdata bs=1M count=4 2>&1; "
            "sync; echo USERDATA_DD_RC=$?",
            timeout=timeout,
        )
        self._log(f"  dd output: {out!r}")
        if "USERDATA_DD_RC=0" not in out:
            raise MetaError(f"factory_reset_dd failed. Output was: {out}")
        if reboot:
            self.reboot()

    def factory_reset_mode01(self, reboot=True, timeout=5.0):
        self._log("factory_reset_mode01: sending mode-01 wipe trigger")
        payload = bytes(1024)
        peer = len(payload).to_bytes(2, "little") + bytes.fromhex("010000000100") + payload
        local = (0).to_bytes(4, "little") + (1).to_bytes(4, "little")
        token = self._next_seq()
        frame = build_meta_frame(token=token, opcode=OP_SHELL_EXEC, data=local, peer_data=peer)
        self._log(f"-> factory_reset_mode01 (0x79, mode=1) token={token}")
        try:
            self._drain(0.2)
            self.ser.reset_input_buffer()
            self.ser.write(frame)
            self.ser.flush()
        except serial.SerialException as e:
            raise MetaError(f"write failed: {e}") from e
        try:
            raw = self._read_one_chunk(timeout=timeout)
            if raw:
                self._log(f"  <- trigger reply ({len(raw)}B): {raw[:64].hex()}")
        except Exception:
            pass
        if reboot:
            self.reboot()

    def reboot(self, vendor_ending=True):
        if vendor_ending:
            time.sleep(0.14)
            self._log("re-opening port with DTR/RTS low")
            try:
                self.ser.close()
                time.sleep(0.05)
                self.ser.open()
                configure_raw_tty(self.ser, verbose=self.verbose)
                self.ser.dtr = False
                self.ser.rts = False
            except Exception:
                pass
            time.sleep(0.01)
        frame = build_meta_frame(token=0, opcode=OP_SESSION_CLOSE, data=(2).to_bytes(4, "little"))
        self._log("-> session close / reboot (0x0A, arg=2)")
        self.ser.write(frame)
        self.ser.write(SYNC_MAGIC)
        self.ser.write(SYNC_MAGIC)
        self.ser.flush()
        time.sleep(1.0 if vendor_ending else 0.1)
        self._rebooted = True


def _build_parser():
    p = argparse.ArgumentParser(
        prog="meta_fixed_v13",
        description="MediaTek META mode CLI for Transsion MTK devices (v13 - with auto-discovered FRP clear)")
    p.add_argument("--wait", action="store_true")
    p.add_argument("--wait-timeout", type=float, default=60.0)
    p.add_argument("--direct", action="store_true")
    p.add_argument("--simple-ending", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-ports")
    sub.add_parser("info")
    sub.add_parser("reboot")
    sub.add_parser("factory-reset-dd", help="factory reset via shell dd on userdata")
    sub.add_parser("factory-reset-mode01", help="factory reset via mode-01 shell frame")
    sub.add_parser("partition-map", help="read-only: dump partition table (name, start LBA, size)")
    fc = sub.add_parser("frp-clear",
                    help="DESTRUCTIVE: clear FRP+para at known offsets (dry-run default)")
    fc.add_argument("--frp-seek", type=int, default=None,
                    help="FRP partition start LBA (from device profile or AndroidUtility log)")
    fc.add_argument("--para-seek", type=int, default=None,
                    help="PARA partition start LBA (from device profile or AndroidUtility log)")
    fc.add_argument("--board", type=str, default=None,
                        help="Unique board name")
    fc.add_argument("--yes", action="store_true",
                    help="actually write (default dry-run)")
    fc.add_argument("--no-reboot", action="store_true",
                    help="don't send reboot frame after writing")
    gp = sub.add_parser("getprop")
    gp.add_argument("name")
    rf = sub.add_parser("read-file")
    rf.add_argument("path")
    rf.add_argument("out_pos", nargs="?", default=None)
    rf.add_argument("--out", dest="out_opt", default=None)
    wf = sub.add_parser("write-file")
    wf.add_argument("path")
    wf.add_argument("src")
    sh = sub.add_parser("shell")
    sh.add_argument("command")
    return p
def print_info(report,s):
    values = report["values"]
    for label, _key, _fb in s.INFO_PROPS:
        print(f"{label:20s}: {values.get(label, '')}")
    if values.get("RNID"):
        print(f"{'RNID':20s}: {values['RNID']}")
    empties = [(label, data) for label, data in report["raw"].items()
                if not data["value"]]
    if empties:
        print()
        print("(empty fields - try these keys manually)")
        for label, data in empties:
            keys = data["key"]
            if data["fallback"]:
                keys += f"  (fallback: {data['fallback']})"
            print(f"  {label:20s} -> {keys}")

def main(argv=None):
    args = _build_parser().parse_args(argv)
    print(f"[debug] cmd={args.cmd!r} wait={args.wait} direct={args.direct} verbose={args.verbose}",
          file=sys.stderr)
    if args.cmd == "list-ports":
        sys.stderr.write(f"[meta] watching for MTK USB devices ({args.wait_timeout:.0f}s)...\n")
        seen = set()
        deadline = time.monotonic() + args.wait_timeout
        try:
            while time.monotonic() < deadline:
                current = set()
                for dev in usb.core.find(find_all=True, idVendor=VID):
                    key = (dev.bus, dev.address, dev.idProduct)
                    current.add(key)
                    if key not in seen:
                        print(f"bus {dev.bus} addr {dev.address:3d} pid=0x{dev.idProduct:04x}")
                for key in seen - current:
                    bus, addr, pid = key
                    print(f"bus {bus} addr {addr:3d} pid=0x{pid:04x} -- DISCONNECTED")
                seen = current
                time.sleep(0.05)
        except KeyboardInterrupt:
            sys.stderr.write("\n[meta] stopped\n")
            return 0
        return 0
    if args.wait:
        if not enter_meta_mode(timeout=args.wait_timeout, verbose=args.verbose):
            return 1
    else:
        if find_device(PID_META) is None:
            print(f"device {VID:04x}:{PID_META:04x} not present. Use --wait.", file=sys.stderr)
            return 1
    try:
        with MetaSerialSession(verbose=args.verbose) as s:
            if args.cmd == "info":
                report = s.full_info()
                print_info(report,s)
            elif args.cmd == "partition-map":
                parts = s.gather_partitions()
                print(f"{'name':20s} {'partnum':12s} {'start_LBA':>10s} {'size':>10s} {'byte_offset':>14s}")
                for name in sorted(parts.keys()):
                    info = parts[name]
                    print(f"{name:20s} {info['partnum']:12s} {info['start']:>10d} "
                          f"{info['size']:>10d} 0x{info['start']*512:>12x}")
                print()
                for key in ("frp", "para", "misc", "userdata"):
                    if key in parts:
                        info = parts[key]
                        print(f"  {key:10s} -> start_LBA={info['start']} byte_offset=0x{info['start']*512:x}")
            elif args.cmd == "getprop":
                print(s.getprop(args.name))
            elif args.cmd == "shell":
                print(s.shell(args.command))
            elif args.cmd == "read-file":
                data = s.read_file(args.path)
                out = args.out_opt or args.out_pos
                if out:
                    with open(out, "wb") as f:
                        f.write(data)
                    print(f"wrote {len(data)} bytes to {out}")
                else:
                    sys.stdout.buffer.write(data)
            elif args.cmd == "write-file":
                with open(args.src, "rb") as f:
                    content = f.read()
                print(f"writing {len(content)} bytes to {args.path}...")
                s.write_file(args.path, content)
                print("done")
            elif args.cmd == "factory-reset-dd":
                s.factory_reset_dd(reboot=False)
                s.reboot(vendor_ending=not args.simple_ending)
                print("factory reset via dd complete, reboot frame sent")
            elif args.cmd == "factory-reset-mode01":
                s.factory_reset_mode01(reboot=False)
                s.reboot(vendor_ending=not args.simple_ending)
                print("factory reset via mode-01 complete, reboot frame sent")
            elif args.cmd == "frp-clear":
                print("Reading device info...",flush=True)
                info=s.full_info()
                print_info(info,s)
                #important  to avoid device brick
                if info['values']['Board']!=args.board:
                    raise MetaError(f"board mismatch aboating\n\
                                    HDW:{info['values']['Board']}/{args.board}")
                if args.yes:
                    print("board matched reseting frp..",flush=True)
                result = s.frp_clear(
                    frp_lba=args.frp_seek,
                    para_lba=args.para_seek,
                    reboot=not args.no_reboot,
                    dry_run=not args.yes,
                )
                if result.get("written"):
                    print(f"FRP clear written (frp_lba={result['frp_lba']} para_lba={result['para_lba']})")
            elif args.cmd == "reboot":
                s.reboot(vendor_ending=not args.simple_ending)

        return 0
    except MetaError as e:
        print(f"device error: {e}", file=sys.stderr)
        return 1
    except Exception:
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())