"""Tab registry. To add a new tab: create tabs/<name>.py with a Tab subclass,
import it here and add it to ALL_TABS (order = order on screen)."""
from .adb_fastboot import AdbFastbootTab
from .mediatek import MediatekTab
from .qualcomm import QualcommTab
from .samsung import SamsungTab
from .spreadtrum import SpreadtrumTab
from .unisoc_diag import UnisocDiagTab
from .mediatek_meta import MediatekMetaTab
ALL_TABS = [QualcommTab, MediatekTab,MediatekMetaTab, SpreadtrumTab, AdbFastbootTab,
            SamsungTab, UnisocDiagTab]
