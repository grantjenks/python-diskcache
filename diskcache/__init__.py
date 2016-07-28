"DiskCache: disk and file backed cache."

from .core import Cache, Disk, UnknownFileWarning, EmptyDirWarning
from .core import LIMITS, DEFAULT_SETTINGS, EVICTION_POLICY
from .fanout import FanoutCache

try:
    from .djangocache import DjangoCache
except Exception: # pylint: disable=broad-except
    # Django not installed or not setup so ignore.
    pass


__title__ = 'diskcache'
__version__ = '1.6.7'
__build__ = 0x010607
__author__ = 'Grant Jenks'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright 2016 Grant Jenks'
