"""MediaTek scatter-file parsing."""
import re

# Partitions NOT ticked by default (bootloader / IMEI / user data)
SCATTER_SKIP = {"preloader", "userdata", "cache", "nvram", "nvdata",
                "protect1", "protect2", "proinfo", "seccfg"}
# scatter `region:` value -> mtk.py --parttype value
SCATTER_PARTTYPE = {"EMMC_BOOT_1": "boot1", "EMMC_BOOT_2": "boot2",
                    "EMMC_RPMB": "rpmb", "UFS_LU0": "lu0", "UFS_LU1": "lu1"}


def parse_scatter(path):
  """Parse a MediaTek scatter file ('- partition_index:' format)."""
  with open(path, encoding="utf-8", errors="replace") as f:
    text = f.read()
  parts = []
  for blk in re.split(r"-\s*partition_index:", text)[1:]:
    def g(k):
      m = re.search(rf"^\s*{k}:\s*(\S+)", blk, re.M)
      return m.group(1) if m else ""
    name, fn = g("partition_name"), g("file_name")
    if name and fn and fn.upper() != "NONE":
      parts.append({"name": name, "file": fn, "region": g("region"),
                    "dl": g("is_download").lower() == "true"})
  return parts
