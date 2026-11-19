"""
DiskCache API Reference
=======================

The :doc:`tutorial` provides a helpful walkthrough of most methods.
"""

from .core import (
    DEFAULT_SETTINGS,
    ENOVAL,
    EVICTION_POLICY,
    UNKNOWN,
    Cache,
    Disk,
    EmptyDirWarning,
    JSONDisk,
    Timeout,
    UnknownFileWarning,
)
from .fanout import FanoutCache
from .persistent import Deque, Index
from .recipes import (
    Averager,
    BoundedSemaphore,
    Lock,
    RLock,
    barrier,
    memoize_stampede,
    throttle,
)

__all__ = [
    'Averager',
    'BoundedSemaphore',
    'Cache',
    'DEFAULT_SETTINGS',
    'Deque',
    'Disk',
    'DjangoCache',
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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .djangocache import DjangoCache


def __getattr__(name):
    if name == 'DjangoCache':
        from .djangocache import DjangoCache

        globals()['DjangoCache'] = DjangoCache
        return DjangoCache
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def __dir__():
    return sorted(set(globals()) | set(__all__))

__title__ = 'diskcache'
__version__ = '5.6.3'
__build__ = 0x050603
__author__ = 'Grant Jenks'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright 2016-2023 Grant Jenks'
