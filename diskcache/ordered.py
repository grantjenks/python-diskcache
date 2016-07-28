"Ordered cache to save keys in order."

import sqlite3

from .core import Cache, Disk, ENOVAL

class OrderedCache(Cache):
    "Cache that saves keys in order."
    def __init__(self, directory, timeout=60, disk=Disk(),
                 **settings):
        """Initialize OrderedCache instance.

        :param str directory: cache directory
        :param float timeout: SQLite connection timeout
        :param disk: `Disk`: instance for serialization
        :param settings: any of `DEFAULT_SETTINGS`

        """
        super(self.__class__, self).__init__(directory, timeout, disk)
        

    def first(self, default=ENOVAL):
        """Retrieve the first key in the cache based on age

        :param key default: default value if cache is empty
        """
        try:
            return next(iter(self))
        except StopIteration:
            return default


    def last(self, default=ENOVAL):
        """Retrieve the last key in the cache based on age

        :param key default: default value if cache is empty
        """
        try:
            return next(reversed(self))
        except StopIteration:
            return default
