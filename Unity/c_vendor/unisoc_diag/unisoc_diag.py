#!/usr/bin/env python3
"""
unisoc_diag_universal.py - Universal Unisoc DIAG tool (1782:4d00).

Works on SC9832E POS, SC9863A, UMS512, T606/T616, itel P661W, etc.
Fully parses platform info, cal (dual IMEIs + MACs), and PSN data.

Protocol (from Windows captures):
    HDLC framing: 0x7e <byte-stuffed body> 0x7e
    Frame body: ch(1) + 00 00 00 + len(1) + cmd(2 BE) + payload

Shell wrappers:
    AT+SHELL="<cmd>"  -> Android shell
    AT+SPDIAG="<cmd>" -> Privileged AT (Factory reset: AT+ETSRESET)
"""

from __future__ import annotations
import argparse, sys, threading, time, re
from dataclasses import dataclass
try:
    import usb.core, usb.util
except ImportError:
    sys.exit("pip install pyusb")

VID, PID = 0x1782, 0x4D00
FLAG, ESC, XOR = 0x7E, 0x7D, 0x20
ESCAPE_SET = {0x7E, 0x7D, 0x11, 0x13}

CMD_HANDSHAKE = 0x00FE
CMD_GET_INFO = 0x0000
CMD_READ_CAL = 0x005E
CMD_READ_PROD = 0x005F
CMD_DEVICE_ID = 0x0053
CMD_AT_SHELL = 0x0068
CMD_SHELL_OUT = 0x009C
CMD_TEARDOWN_1 = 0x00D5
CMD_TEARDOWN_2 = 0x0011

INFO_PREFIX = b"\x00\x0a"
USB_TIMEOUT_MS = 2000
HANDSHAKE_PAYLOAD = b"\x95"

PAYLOAD_INFO = b"\x00"
PAYLOAD_INFO_FINGERPRINT = b"\x02"
PAYLOAD_DEVICE_ID = b"\x32"
PAYLOAD_CAL = b"\xff\x00\x00"
PAYLOAD_PSN = b"\x81\x00\x00"

REENUM_TIMEOUT = 30.0
CTRL_LINE_STATE_VALUES = (0x0000, 0x0601)

SHELL_FORMATS = [
    b"\x00AT+SPAT=\"%b\"",
    b"\x00AT+SHELL=\"%b\"",
    b"AT+SPAT=\"%b\"",
    b"AT+SHELL=\"%b\"",
    b"\x00AT+SPATRM=\"%b\"",
    b"\x00AT+SG=\"%b\"",
    b"\x00AT+SPDIAG=\"%b\"",
]

DANGEROUS = (
    "rm ", "dd ", "mkfs", "wipe", "MASTER_CLEAR", "recovery",
    ">", ">>", "settings put", "setprop", "chmod", "chown",
    "pm uninstall", "pm disable", "am broadcast", "svc ",
    "etsreset", "spdiag",
)

class DiagError(Exception): pass
class UsageError(Exception): pass

def hdlc_escape(d):
    out = bytearray()
    for b in d:
        if b in ESCAPE_SET:
            out.extend([ESC, b ^ XOR])
        else:
            out.append(b)
    return bytes(out)

def hdlc_unescape(d):
    out = bytearray()
    i = 0
    while i < len(d):
        if d[i] == ESC and i + 1 < len(d):
            out.append(d[i + 1] ^ XOR)
            i += 2
        else:
            out.append(d[i])
            i += 1
    return bytes(out)

def build_frame(ch, cmd, payload=b""):
    body = bytes([ch, 0, 0, 0, len(payload) + 7, (cmd >> 8) & 0xFF, cmd & 0xFF]) + payload
    return bytes([FLAG]) + hdlc_escape(body) + bytes([FLAG])

@dataclass
class Frame:
    channel: int
    cmd: int
    payload: bytes

class UnisocDiag:
    def __init__(self, vid=VID, pid=PID, verbose=False):
        self.vid = vid
        self.pid = pid
        self.verbose = verbose
        self.dev = None
        self.ep_in = None
        self.ep_out = None
        self.channel = 0
        self._rx = bytearray()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *e):
        self.close()

    def _log(self, m):
        if self.verbose:
            print(f"[diag] {m}", file=sys.stderr, flush=True)

    def _send_control_line_state(self, w):
        try:
            self.dev.ctrl_transfer(0x21, 0x22, w, 0, 0, 1000)
            self._log(f"CTRL 0x{w:04x}")
        except Exception as e:
            self._log(f"CTRL fail {e}")

    def _enumerate_endpoints(self):
        cfg = self.dev.get_active_configuration()
        intf = cfg[(0, 0)]
        self.ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e:
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
                and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK,
        )
        self.ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e:
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK,
        )
        if not self.ep_in or not self.ep_out:
            raise DiagError("bulk not found")

    def open(self):
        self.dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
        if not self.dev:
            raise DiagError(f"{self.vid:04x}:{self.pid:04x} not found")
        try:
            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)
        except:
            pass
        try:
            self.dev.set_configuration()
        except Exception as e:
            self._log(f"set_cfg {e}")
        for w in CTRL_LINE_STATE_VALUES:
            self._send_control_line_state(w)
            time.sleep(0.02)
        self._enumerate_endpoints()
        self._log(f"opened {self.vid:04x}:{self.pid:04x} addr {self.dev.address} "
                  f"OUT 0x{self.ep_out.bEndpointAddress:02x} "
                  f"IN 0x{self.ep_in.bEndpointAddress:02x}")

    def close(self):
        if self.dev:
            try:
                usb.util.dispose_resources(self.dev)
            except:
                pass
        self.dev = None

    def _next_channel(self):
        ch = self.channel
        self.channel = (self.channel + 1) & 0xFF
        return ch

    def _write(self, data):
        self._log(f"OUT {len(data)} {data[:60].hex()}")
        self.ep_out.write(data, timeout=USB_TIMEOUT_MS)

    def _read_into_buffer(self, deadline):
        rem = deadline - time.monotonic()
        if rem <= 0:
            return
        to = max(20, int(rem * 1000))
        try:
            chunk = bytes(self.ep_in.read(4096, timeout=to))
            if chunk:
                self._log(f"IN {len(chunk)} {chunk[:80].hex()}")
                self._rx.extend(chunk)
        except usb.core.USBTimeoutError:
            return
        except Exception as e:
            raise DiagError(f"IN {e}")

    def _read_frame(self, deadline, ignore_heartbeat=True):
        while time.monotonic() < deadline:
            while True:
                s = self._rx.find(FLAG)
                if s < 0:
                    break
                e = self._rx.find(FLAG, s + 1)
                if e < 0:
                    if s > 0:
                        del self._rx[:s]
                    break
                raw = bytes(self._rx[s + 1:e])
                del self._rx[:e + 1]
                if len(raw) == 0:
                    continue
                try:
                    body = hdlc_unescape(raw)
                except:
                    continue
                if len(body) < 7:
                    continue
                if ignore_heartbeat and body[:3] == b"\x4e\x13\x0b":
                    continue
                return Frame(body[0], (body[5] << 8) | body[6], body[7:])
            self._read_into_buffer(deadline)
        return None

    def transact(self, cmd, payload=b"", timeout=5.0, expect=None, retries=1):
        for attempt in range(retries + 1):
            try:
                ch = self._next_channel()
                frm = build_frame(ch, cmd, payload)
                self._log(f"-> ch={ch} 0x{cmd:04X} {payload.hex()}")
                self._write(frm)
                dl = time.monotonic() + timeout
                while time.monotonic() < dl:
                    r = self._read_frame(dl)
                    if not r:
                        continue
                    if expect and r.cmd != expect:
                        self._log(f"skip 0x{r.cmd:04X}")
                        continue
                    self._log(f"<- ch={r.channel} 0x{r.cmd:04X} "
                              f"{len(r.payload)} {r.payload[:40].hex()}")
                    return r
                raise DiagError(f"timeout 0x{cmd:04X}")
            except DiagError:
                if attempt < retries:
                    self._log(f"retry 0x{cmd:04X}")
                    time.sleep(0.2)
                    continue
                raise

    def wait_for_reenumeration(self, old_addr, timeout=REENUM_TIMEOUT):
        self._log("wait re-enum")
        dl = time.monotonic() + timeout
        while time.monotonic() < dl:
            try:
                self.ep_in.read(4096, timeout=100)
            except usb.core.USBTimeoutError:
                pass
            except Exception as e:
                self._log(f"disc {e}")
                break
            dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
            if dev and dev.address != old_addr:
                self._log(f"new addr {dev.address}")
                try:
                    usb.util.dispose_resources(self.dev)
                except:
                    pass
                self.dev = None
                try:
                    self.open()
                    return True
                except Exception as e:
                    self._log(f"open fail {e}")
        self.close()
        time.sleep(0.5)
        dl = time.monotonic() + timeout
        while time.monotonic() < dl:
            dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
            if dev:
                try:
                    self.open()
                    return True
                except:
                    pass
            time.sleep(0.2)
        return False

    def handshake(self):
        old = self.dev.address
        self._log(f"BROM {old}")
        primed = {"data": None}

        def reader():
            try:
                primed["data"] = bytes(self.ep_in.read(4096, timeout=5000))
            except Exception:
                primed["data"] = None

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        time.sleep(0.05)
        self._write(build_frame(0, CMD_HANDSHAKE, HANDSHAKE_PAYLOAD))
        t.join(2.0)
        if primed["data"]:
            self._rx.extend(primed["data"])
        if not self.wait_for_reenumeration(old):
            raise DiagError("no re-enum")
        for w in CTRL_LINE_STATE_VALUES:
            self._send_control_line_state(w)
            time.sleep(0.02)
        self._enumerate_endpoints()
        self.channel = 0
        self._rx.clear()
        time.sleep(0.5) # settle delay for DIAG state machine
        self._log(f"Diag addr {self.dev.address}")

    def init_sequence(self):
        for _, fn in (("info", self.read_info),
                      ("cal", self.read_cal),
                      ("psn", self.read_psn),
                      ("fp", self.read_fingerprint),
                      ("devid", self.read_device_id)):
            try:
                fn()
            except Exception as e:
                self._log(f"{_} fail {e}")

    def read_info(self):
        r = self.transact(CMD_GET_INFO, PAYLOAD_INFO, 5.0)
        p = r.payload[2:] if r.payload[:2] == INFO_PREFIX else r.payload
        return p.rstrip(b"\x00").decode("ascii", "replace")

    def read_fingerprint(self):
        r = self.transact(CMD_GET_INFO, PAYLOAD_INFO_FINGERPRINT, 5.0)
        p = r.payload[2:] if r.payload[:2] == INFO_PREFIX else r.payload
        return p.rstrip(b"\x00").decode("ascii", "replace")

    def read_device_id(self):
        r = self.transact(CMD_DEVICE_ID, PAYLOAD_DEVICE_ID, 5.0)
        for _ in range(3):
            if len(r.payload) >= 10:
                break
            nxt = self._read_frame(time.monotonic() + 2.0)
            if not nxt:
                break
            r = nxt
        p = r.payload[2:] if r.payload[:2] == INFO_PREFIX else r.payload
        return p.rstrip(b"\x00").decode("ascii", "replace")

    def read_cal(self):
        r1 = self.transact(CMD_READ_CAL, PAYLOAD_CAL, 8.0)
        p1 = r1.payload
        frames = [p1]

        # Catch the second frame with a longer timeout
        for _ in range(3):
            try:
                nxt = self._read_frame(time.monotonic() + 2.0)
                if nxt and nxt.cmd == CMD_READ_CAL:
                    frames.append(nxt.payload)
                    self._log(f"cal extra {len(nxt.payload)} {nxt.payload.hex()[:80]}")
                else:
                    break
            except:
                break

        def bcd_imei(b):
            digits = []
            for byte in b:
                lo = byte & 0x0F
                hi = (byte >> 4) & 0x0F
                if lo <= 9:
                    digits.append(str(lo))
                if hi <= 9:
                    digits.append(str(hi))
            s = "".join(digits)
            if len(s) >= 11 and s[0] == "8" and s[1] in "0123456789":
                if len(s) > 14:
                    s = s[1:]
            return s[:15]

        def mac(b):
            if len(b) < 6:
                return "?"
            if all(x == 0 for x in b) or all(x == 0xFF for x in b):
                return "?"
            return ":".join(f"{x:02x}" for x in b)

        def is_blank(b):
            """True when this byte range carries no data (device didn't put
            anything here in this particular frame). An all-zero range still
            decodes to a length-15 BCD string of zeros, which used to be
            accepted as a "valid" IMEI - this is what must be rejected."""
            return all(x == 0 for x in b) or all(x == 0xFF for x in b)

        def score(p):
            return sum(1 for x in p if x not in (0, 0xFF))

        best = max(frames, key=score) if frames else p1

        imei1 = "?"
        imei2 = "?"
        imei1_hex = "?"
        imei2_hex = "?"
        wifi = "?"
        bt = "?"

        # The device splits cal data across the two frames it sends back for
        # this command: on this phone frame 1 carries the Wi-Fi/BT MACs (with
        # all-zero bytes where the IMEIs would be) and frame 2 carries the
        # IMEIs (with all-zero bytes where the MACs would be). Taking the
        # first "long enough" decode without checking it actually has data
        # meant the all-zero IMEI slice in frame 1 was accepted before frame
        # 2's real IMEIs were ever looked at. Skipping blank (all-zero /
        # all-0xFF) slices fixes that, for both fields, regardless of which
        # frame happens to carry which value on a given chipset.
        for p in frames:
            if len(p) >= 23 and wifi == "?":
                m = mac(p[17:23])
                if m != "?":
                    wifi = m
            if len(p) >= 94 and bt == "?":
                m = mac(p[88:94])
                if m != "?":
                    bt = m
            if len(p) >= 9 and imei1 == "?":
                raw = p[1:9]
                if not is_blank(raw):
                    cand = bcd_imei(raw)
                    if len(cand) >= 14:
                        imei1 = cand
                        imei1_hex = raw.hex()
            if len(p) >= 17 and imei2 == "?":
                raw = p[9:17]
                if not is_blank(raw):
                    cand = bcd_imei(raw)
                    if len(cand) >= 14:
                        imei2 = cand
                        imei2_hex = raw.hex()

        return {
            "wifi_mac": wifi,
            "bt_mac": bt,
            "imei1": imei1,
            "imei2": imei2,
        }

    def read_psn(self):
        r = self.transact(CMD_READ_PROD, PAYLOAD_PSN, 5.0)
        payloads = [r.payload]
        for _ in range(2):
            try:
                nxt = self._read_frame(time.monotonic() + 0.5)
                if nxt and nxt.cmd == CMD_READ_PROD:
                    payloads.append(nxt.payload)
            except:
                break
        full = b"".join(payloads)

        def ascii_clean(b):
            return "".join(chr(c) for c in b if 32 <= c < 127)

        printable = ascii_clean(full)

        # Match Android Utility's extraction logic
        psn_match = re.search(r"([A-Z0-9]{10,})", printable)
        phase_match = re.search(r"(90PS\d+)", printable)

        psn = psn_match.group(1) if psn_match else "?"
        phase = phase_match.group(1) if phase_match else "?"

        return {
            "psn": psn,
            "phasecheck": phase,
            "raw": printable,
        }

    def shell(self, command, timeout=10.0):
        if "\x00" in command:
            raise UsageError("no NUL")
        cmd_clean = command.strip().strip('"').strip("'")
        last_err = None
        last_out = None
        for fmt in SHELL_FORMATS:
            try:
                payload = fmt % cmd_clean.encode()
            except:
                payload = fmt.replace(b"%b", cmd_clean.encode())
            self._log(f"try {fmt}")
            self._write(build_frame(self._next_channel(), CMD_AT_SHELL, payload))
            dl = time.monotonic() + timeout
            out = []
            got_shell = False
            got_d5 = False
            while time.monotonic() < dl:
                r = self._read_frame(dl)
                if not r:
                    continue
                self._log(f"resp 0x{r.cmd:04X} {len(r.payload)} {r.payload[:60].hex()}")

                # 0x0068 is echo, 0x009C is output
                if r.cmd in (CMD_AT_SHELL, CMD_SHELL_OUT):
                    got_shell = True
                    p = r.payload[2:] if r.payload[:2] == INFO_PREFIX else r.payload
                    txt = p.rstrip(b"\x00").decode("utf-8", "replace")
                    if txt:
                        out.append(txt)
                    continue

                if r.cmd in (CMD_TEARDOWN_1, CMD_TEARDOWN_2):
                    if r.cmd == CMD_TEARDOWN_1:
                        got_d5 = True
                    time.sleep(0.05)
                    continue

                p = r.payload[2:] if r.payload[:2] == INFO_PREFIX else r.payload
                txt = p.rstrip(b"\x00").decode("utf-8", "replace")
                if txt and len(txt) > 2:
                    out.append(txt)

            if got_shell:
                return "\n".join(out) if out else ""

            last_err = f"{fmt} d5={got_d5} shell={got_shell} out={out}"
            if out:
                last_out = "\n".join(out)
            time.sleep(0.2)

        if last_out is not None:
            return last_out
        raise DiagError(f"all shell failed {last_err}")

    def teardown(self):
        for cmd in (CMD_TEARDOWN_1, CMD_TEARDOWN_2):
            try:
                self._write(build_frame(self._next_channel(), cmd))
                time.sleep(0.05)
            except:
                pass

def device_present(vid=VID, pid=PID):
    return usb.core.find(idVendor=vid, idProduct=pid) is not None

def wait_for_device_poll(vid=VID, pid=PID, timeout=60.0):
    dl = time.monotonic() + timeout
    while time.monotonic() < dl:
        if device_present(vid, pid):
            return True
        time.sleep(0.1)
    return False

def main(argv=None):
    p = argparse.ArgumentParser(prog="unisoc_diag_universal.py")
    p.add_argument("--wait", action="store_true")
    p.add_argument("--wait-timeout", type=float, default=60.0)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect")
    sub.add_parser("info")
    sub.add_parser("fullinfo")
    sub.add_parser("cal")
    sub.add_parser("psn")
    sh = sub.add_parser("shell")
    sh.add_argument("--danger", action="store_true")
    sh.add_argument("command")

    args = p.parse_args(argv)
    print(f"[debug] cmd={args.cmd} wait={args.wait}", file=sys.stderr)

    if args.cmd == "detect":
        present = device_present()
        print("present" if present else "not present")
        return 0 if present else 1

    if args.wait:
        if not wait_for_device_poll(timeout=args.wait_timeout):
            print("timeout", file=sys.stderr)
            return 1
    else:
        if not device_present():
            print("not present use --wait", file=sys.stderr)
            return 1

    if args.cmd == "shell" and any(t.lower() in args.command.lower()
                                   for t in DANGEROUS) and not args.danger:
        print(f"REFUSING {args.command} re-run --danger", file=sys.stderr)
        return 2

    try:
        with UnisocDiag(verbose=args.verbose) as d:
            d.handshake()

            if args.cmd == "info":
                print(d.read_info())
                return 0

            if args.cmd == "fullinfo":
                print("--- info ---")
                print(d.read_info())
                print("--- fp ---")
                print(d.read_fingerprint())
                print("--- devid ---")
                print(d.read_device_id())
                print("--- cal ---")
                for k, v in d.read_cal().items():
                    print(f"{k}: {v}")
                print("--- psn ---")
                for k, v in d.read_psn().items():
                    print(f"{k}: {v}")
                d.teardown()
                return 0

            if args.cmd == "cal":
                for k, v in d.read_cal().items():
                    print(f"{k}: {v}")
                d.teardown()
                return 0

            if args.cmd == "psn":
                for k, v in d.read_psn().items():
                    print(f"{k}: {v}")
                d.teardown()
                return 0

            if args.cmd == "shell":
                d.init_sequence()
                res = d.shell(args.command)
                print(f"[debug] {len(res)} chars", file=sys.stderr)
                print(res)
                d.teardown()
                return 0

    except Exception as e:
        print(f"error {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
