"DiskCache: disk and file backed cache."

from .core import Cache, Disk, UnknownFileWarning, EmptyDirWarning, Timeout
from .core import DEFAULT_SETTINGS, ENOVAL, EVICTION_POLICY, UNKNOWN
from .fanout import FanoutCache
from .persistent import Deque, Index

__all__ = [
    'Cache',
    'Disk',
    'UnknownFileWarning',
    'EmptyDirWarning',
    'Timeout',
    'DEFAULT_SETTINGS',
    'ENOVAL',
    'EVICTION_POLICY',
    'UNKNOWN',
    'FanoutCache',
    'Deque',
    'Index',
]

try:
    from .djangocache import DjangoCache  # pylint: disable=wrong-import-position
    __all__.append('DjangoCache')
except Exception:  # pylint: disable=broad-except
    # Django not installed or not setup so ignore.
    pass


__title__ = 'diskcache'
__version__ = '3.0.1'
__build__ = 0x030001
__author__ = 'Grant Jenks'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright 2016 Grant Jenks'
