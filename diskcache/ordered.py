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


    def first(self, default=None, key=False, read=False, expire_time=False, tag=False):
        """ Return the first entry in cache """
        sql = self._sql

        row = sql('SELECT key FROM Cache ORDER BY rowid ASC').fetchone()

        if not row:
            return default

        (cache_key), = row

        value = self.get(cache_key, default=default, read=read, expire_time=expire_time, tag=tag)

        if key:
            return (cache_key, value)
        else:
            return value


    def last(self, default=None, key=False, read=False, expire_time=False, tag=False):
        """ Return the last entry in cache """
        sql = self._sql

        row = sql('SELECT key FROM Cache ORDER BY rowid DESC').fetchone()

        if not row:
            return default

        (cache_key), = row

        value = self.get(cache_key, default=default, read=read, expire_time=expire_time, tag=tag)

        if key:
            return (cache_key, value)
        else:
            return value
