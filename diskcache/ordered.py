"Ordered cache to save keys in order."

import sqlite3

from .core import Cache, Disk, ENOVAL

class OrderedCache(Cache):
    "Cache that saves keys in order."
    def __init__(self, directory, timeout=60, disk=Disk(),
                 **settings):
        """Initialize OrderedCache instance.

        :param str filename: cache file
        :param float timeout: SQLite connection timeout
        :param disk: `Disk`: instance for serialization
        :param settings: any of `DEFAULT_SETTINGS`

        """

        super(self.__class__, self).__init__(directory, timeout, disk)


    def first(self, default=None):
        """ Return the first entry in cache """
        sql = self._sql

        row = sql('SELECT key FROM Cache ORDER BY rowid ASC').fetchone()

        if not row:
            return default

        (key), = row

        print key

        return self.get(key, default=default)


    def last(self, default=None):
        """ Return the last entry in cache """
        sql = self._sql

        row = sql('SELECT key FROM Cache ORDER BY rowid DESC').fetchone()

        if not row:
            return default

        (key), = row

        return self.get(key, default=default)
