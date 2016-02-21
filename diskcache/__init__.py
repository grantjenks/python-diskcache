"DiskCache: disk and file-based cache."

from .core import Cache, Disk, EmptyDirWarning
from .core import LIMITS, DEFAULT_SETTINGS, EVICTION_POLICY
# from .djangocache import DjangoCache

__title__ = 'diskcache'
__version__ = '0.6.0'
__build__ = 0x000600
__author__ = 'Grant Jenks'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright 2016 Grant Jenks'
