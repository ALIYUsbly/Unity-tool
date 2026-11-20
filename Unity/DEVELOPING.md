# Developing TSM CLONE PRO

## Layout

```
__main__.py, app.py  entry point (python -m Unity, from the repo root)
config.py            paths, partition lists, brand names, tool folders
theme.py             colours + stylesheet
core/                no UI code
  actions.py         Action / Section / fixed() / batch()
  builders.py        builders shared by EDL and MTK (read/write/erase partition)
  runner.py          runs commands with QProcess
  tools.py           finds tools, builds the command line
  safety.py          sparse-image check + backup warning
  backups.py         backup folder scan + "was the read really written?" checks
  scatter.py         MTK scatter parser
  profiles.py        device profiles (yours, unchanged)
tabs/                one file per tab  <- you work here
  base.py            Tab base class (hooks)
  qualcomm.py  mediatek.py  spreadtrum.py  adb_fastboot.py  samsung.py
ui/                  widgets, dialogs, log panel, window (rarely touched)
```

Imports inside the package are absolute: `from Unity.core.actions import Action`.
Run everything from the repo root (`python -m Unity`, `python -m unittest ...`).

## Add a button (most common)

Open the tab file, e.g. `tabs/qualcomm.py`, and add one line to a `Section`:

```python
Action("PRINT GPT", fixed("printgpt")),                  # fixed command
Action("READ PARTITION...", B.read_partition),           # asks name + file
Action("WIPE CACHE", fixed("e", "cache"), "danger"),     # risk: safe|write|danger
Action("FACTORY RESET", batch(["e", "userdata"], ["e", "cache"]), "danger")
```

Add `report=True` to a read-only button (`Action("INFO", fixed("info"), report=True)`)
to save everything the tool prints to `backups/reports/<time>_<label>.txt`
when the run ends (also when it fails, marked INCOMPLETE).

Risk colours the button and decides whether the backup warning is shown:
`safe` = no warning, `write` = orange + warning, `danger` = red + warning.

## Add a button that asks questions

Write a *builder*: a function that gets `ui`, asks, and returns a list of
commands (each command is a list of arguments), or `None` to cancel.

```python
def read_two(ui):
  part = ui.ask_name("Read", "Partition name:")
  if not part:
    return None
  out = ui.pick_save("Save as", f"{part}.bin")
  return [["r", part, out]] if out else None

Action("READ ONE...", read_two)
```

`ui` offers: `ask_name`, `ask_text`, `pick_file`, `pick_dir`, `pick_save`,
`dialog`, `log`.

## Add an option (a setting in the top card of a tab)

In the tab's `options(self, form)`:

```python
form.check("fast", "Fast mode")
form.file("cert", "Certificate", "Select cert", "PEM (*.pem);;All Files (*)")
form.combo("speed", "Speed", ["", "slow", "fast"])
form.radio("mode", "Mode", [("Auto", ""), ("A", "a"), ("B", "b")])
form.entry("serial", "Serial")
form.note("Some help text")
```

Then use it in `extra_flags` (flags AFTER the command) or `pre_args`
(arguments BEFORE the command). `opts` holds all option values:

```python
def extra_flags(self, script, args, opts):
  flags = []
  if opts["fast"] and args and args[0] in ("w", "wl"):
    flags.append("--fast")
  return flags
```

## Add a new tab

1. Create `tabs/huawei.py` (copy `tabs/samsung.py` as a template). Set
   `title`, `sections`, optionally `platform` (matches `"platform"` in device
   profiles) and `config_title` + `options()`.
2. In `tabs/__init__.py` import it and add it to `ALL_TABS`.
3. Run the tests: `tests/test_qt_app.py` builds the whole window with every tab,
   so a broken import or a crash while building a tab shows up there.

## Add a new tool

- Python script: put it under `vendor/<name>/` and add its folder to
  `SCRIPT_DIRS` in `config.py`.
- Program (binary): add its name to `SYS_TOOLS` in `config.py`
  (and a vendor build folder to `LOCAL_TOOL_DIRS` if it is built from source).
- Use the name as the `Section` script: `Section("TITLE", "mytool", [...])`.

## Tab hooks (all optional)

| Hook | Use |
|---|---|
| `check_options(ui)` | validate settings before any dialog opens; return False to stop |
| `check_cmds(ui, cmds)` | validate the built commands |
| `pre_args(script, args, opts)` | arguments placed before the command |
| `extra_flags(script, args, opts)` | flags placed after the command |
| `risk_note(cmds)` | extra text in the backup warning |
| `before_run(ui, script, opts)` | runs once just before the commands start |
| `apply_profile(ui, p)` | fill options from a device profile |
