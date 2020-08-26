"""
DiskCache API Reference
=======================

The :doc:`tutorial` provides a helpful walkthrough of most methods.

"""

from .core import (
    Cache, Disk, EmptyDirWarning, JSONDisk, UnknownFileWarning, Timeout
)
from .core import DEFAULT_SETTINGS, ENOVAL, EVICTION_POLICY, UNKNOWN
from .fanout import FanoutCache
from .persistent import Deque, Index
from .recipes import Averager, BoundedSemaphore, Lock, RLock
from .recipes import barrier, memoize_stampede, throttle

__all__ = [
    'Averager',
    'BoundedSemaphore',
    'Cache',
    'DEFAULT_SETTINGS',
    'Deque',
    'Disk',
    'ENOVAL',
    'EVICTION_POLICY',
    'EmptyDirWarning',
    'FanoutCache',
    'Index',
    'JSONDisk',
    'Lock',
    'RLock',
    'Timeout',
    'UNKNOWN',
    'UnknownFileWarning',
    'barrier',
    'memoize_stampede',
    'throttle',
]

try:
    from .djangocache import DjangoCache  # noqa
    __all__.append('DjangoCache')
except Exception:  # pylint: disable=broad-except
    # Django not installed or not setup so ignore.
    pass

__title__ = 'diskcache'
__version__ = '5.0.2'
__build__ = 0x050002
__author__ = 'Grant Jenks'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright 2016-2020 Grant Jenks'
