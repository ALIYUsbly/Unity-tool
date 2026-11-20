# UNITY-TOOL

Phone service GUI (PySide6) that wraps command-line tools kept in `vendor/`:

| Tab | Tool | Where it comes from |
|---|---|---|
| Qualcomm (EDL) | `edl.py` | `vendor/edl` (git submodule) |
| MediaTek (MTK) | `mtk.py` | `vendor/mtkclient` (git submodule) |
| MediaTek Meta (read-only) | `meta_readonly.py` | `vendor/meta` (own script, not a submodule) |
| Spreadtrum (SPD) | `spd.py` | `vendor/spd` or `vendor/spdclient` |
| ADB / Fastboot | `adb`, `fastboot` | system packages (on PATH) |
| Samsung (Odin) | `heimdall`, `tar`, `lz4` | `vendor/Heimdall` (submodule, built once) |
| Apple / iOS | `ideviceinfo`, `idevicediagnostics`, `idevicebackup2`, `idevicerestore`, `idevicecrashreport` | system packages (`libimobiledevice`, on PATH) |

## Folder layout

```
Unity/                      <- repo root
  Unity/                    <- the app package
    __main__.py, app.py   <- start-up:  python -m Unity
    core/profiles.py
    devices/profiles/*.json
  tests/
  backups/                <- default folder for partition backups (git-ignored)
  vendor/
    mtkclient/
    edl/
    spd/ (or spdclient/)
    meta/
      meta.py    <- own script, just commit it; not a submodule
    spd_dump/             <- prebuilt spd_dump binary (committed directly)
    Heimdall/             <- built binary: build/bin/heimdall
```

The app finds tools in `vendor/` next to the package. To use another folder,
set `UNITY_TOOLS_DIR=/path/to/vendor`.

## Setting up a new system (Debian / Ubuntu)

### 1. Clone with submodules

```
git clone --recursive <your-repo-url> Unity
cd Unity
# if you forgot --recursive:
git submodule update --init --recursive
```

`vendor/meta/meta_readonly.py` isn't a submodule — it's committed directly in
this repo, so it comes along with the normal clone, no extra step.

### 2. System packages

```
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git \
    build-essential cmake pkg-config libusb-1.0-0-dev zlib1g-dev \
    adb fastboot lz4 tar \
    usbmuxd libimobiledevice-utils libimobiledevice6
```

Other distros: Fedora `cmake gcc-c++ make libusb1-devel zlib-devel android-tools lz4 usbmuxd libimobiledevice`,
Arch `cmake base-devel libusb zlib android-tools lz4 usbmuxd libimobiledevice`.

### 3. Python environment for the GUI

```
python3 -m venv .venv
source .venv/bin/activate
pip install PySide6
```

### 4. Python dependencies of the vendored tools

Each tool has its own requirements. Follow the README inside each folder; the
usual way is:

```
pip install -r vendor/mtkclient/requirements.txt
pip install -r vendor/edl/requirements.txt
```

`vendor/meta/meta_readonly.py` is a plain script with two dependencies:

```
pip install pyusb pyserial
```

The app prefers a tool's own virtualenv when it has one
(`vendor/edl/.venv/bin/python`), so you can also keep one venv per tool.

### 5. Build Heimdall (once per machine)

```
cd vendor/Heimdall
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release -DDISABLE_FRONTEND=ON ..
make -j$(nproc)
ls bin/heimdall        # must exist
cd ../../..
```

Rebuild only when you move to another OS / CPU type, or after updating the
Heimdall submodule. Never commit the `build/` folder.

### 6. USB permissions

Heimdall (Samsung):

```
sudo cp vendor/Heimdall/heimdall/60-heimdall.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

MediaTek and Qualcomm: install the udev rules shipped with `mtkclient` and
`edl` (see the README / setup folder of each tool). The same rules cover the
MediaTek Meta tab (`meta_readonly.py`) — it's the same `0e8d` vendor ID in
Preloader/Meta mode, no separate rule needed.

Groups, then log out and back in:

```
sudo usermod -aG plugdev,dialout $USER
```

Spreadtrum uses serial ports (`/dev/ttyUSB*`, `/dev/ttyACM*`), which need the
`dialout` group. The MediaTek Meta tab also uses a serial port
(`/dev/ttyACM*` while in Meta mode) — same group covers it.

iPhones don't need udev rules or group membership; `usbmuxd` handles pairing
on its own once it's installed and running (step 2).

### 7. Stop ModemManager grabbing download-mode devices

```
sudo systemctl stop ModemManager
sudo systemctl disable ModemManager
```

Or keep it and use udev rules that mark the devices as ignored. This also
covers the MediaTek Meta tab's serial port, which can otherwise get grabbed
the same way the Spreadtrum ports do.

### 8. Run

```
source .venv/bin/activate
python -m Unity          # from the repo root
```

With `uv` instead of pip: `uv sync` installs the app and the Python packages the
vendored tools need (see `[dependency-groups]` in `pyproject.toml`), then
`uv run python -m Unity`.

Tests: `python -m unittest discover -s tests -t .` (the Qt tests run offscreen
and are skipped if PySide6 is not installed).

## Quick checks

```
adb version
fastboot --version
vendor/Heimdall/build/bin/heimdall version
lz4 --version
systemctl status usbmuxd     # should be active (running)
ideviceinfo -s               # with an iPhone attached and trusted
```

In the app: SAMSUNG tab > DETECT DEVICE with a phone in Download Mode,
ADB tab > LIST DEVICES with USB debugging on, APPLE / iOS tab > SIMPLE INFO
with an iPhone attached.

## Troubleshooting

- **`heimdall not found`**: the binary is not at `vendor/Heimdall/build/bin/heimdall`.
  Build it (step 5) or symlink it:
  `sudo ln -s "$PWD/vendor/Heimdall/build/bin/heimdall" /usr/local/bin/heimdall`
- **`cmake: command not found`**: install the packages from step 2.
- **Permission denied / device not detected**: udev rules and groups (step 6),
  then unplug and replug the phone.
- **Serial port not found (SPD, or MediaTek Meta tab)**: check cable and
  download/meta mode, stop ModemManager (step 7), be in the `dialout` group.
- **Tool script not found**: check that submodules are initialised
  (`git submodule update --init --recursive`) and that `vendor/` is where the
  app expects it (or set `TSM_TOOLS_DIR`).
- **After a big system upgrade Heimdall fails with a shared-library error**:
  rebuild it (step 5).
- **iPhone not detected / `No device found`**: confirm `usbmuxd` is running
  (`systemctl status usbmuxd`), the cable supports data (not charge-only),
  and "Trust This Computer" has been accepted on the device's screen.
- **`idevicerestore` refuses the IPSW**: Apple has stopped signing that iOS
  version — same restriction iTunes/Finder would hit with the same file.

## Safety notes

- Always back up EFS / NVRAM / NV partitions before writing or erasing
  (the app's warning dialogs list the usual ones). Backup pickers start in
  `backups/` (override with `TSM_BACKUP_DIR`); the write/erase warning shows
  what is in that folder, and after every read the app checks that the output
  file exists and is not empty. `backups/` holds customer IMEI/NV data and is
  git-ignored - never commit it.
- Before any operation on a MediaTek phone, run one of the snapshots (both are
  read-only):
  - MEDIATEK tab > **PRE-OP SNAPSHOT (NV BACKUP + INFO)** (BROM/Preloader): backs
    up nvram, nvdata, protect1, protect2 and proinfo into a new
    `backups/snapshot-<time>/` folder, reads the partition table, and saves
    everything the tool printed while connecting (chip, secure-boot flags,
    MEID ...) in a report.
  - MEDIATEK META tab > **SNAPSHOT (INFO + BUILD)**: DEVICE INFO plus the build
    properties listed in `META_SNAPSHOT_PROPS` (`config.py`), saved the same way.
  Reports are plain text in `backups/reports/`. They contain IMEI/MEID, so
  treat them like the backups: never commit them (the folder is git-ignored).
- The Spreadtrum built-in partition table is generic. Use
  LIST PARTS (FROM DEVICE) before writing.
- Heimdall works mostly on older Samsung models; newer ones may need Odin or Thor.
- MTK scatter flashing leaves the bootloader, IMEI and user-data partitions
  unticked by default. Tick them only if you know why.
- The MediaTek Meta tab is read-only by design (device info, a single
  property, a single small file) — it does not flash, erase, or run
  arbitrary commands on the device.
- `RESTORE FROM IPSW (erase)` on the Apple / iOS tab wipes the device, same
  caution as `FACTORY RESET` on the other tabs.
