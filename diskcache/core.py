"""Core disk and file backed cache API.

"""

import codecs
import contextlib as cl
import errno
import functools as ft
import io
import os
import os.path as op
import sqlite3
import struct
import sys
import threading
import time
import warnings
import zlib

if sys.hexversion < 0x03000000:
    import cPickle as pickle
    # ISSUE #25 Fix for http://bugs.python.org/issue10211
    from cStringIO import StringIO as BytesIO
    TextType = unicode
    BytesType = str
    INT_TYPES = int, long
    range = xrange  # pylint: disable=redefined-builtin,invalid-name
    io_open = io.open  # pylint: disable=invalid-name
else:
    import pickle
    from io import BytesIO  # pylint: disable=ungrouped-imports
    TextType = str
    BytesType = bytes
    INT_TYPES = int,
    io_open = open  # pylint: disable=invalid-name

try:
    WindowsError
except NameError:
    class WindowsError(Exception):
        "Windows error place-holder on platforms without support."
        pass

class Constant(tuple):
    "Pretty display of immutable constant."
    def __new__(cls, name):
        return tuple.__new__(cls, (name,))

    def __repr__(self):
        return self[0]

DBNAME = 'cache.db'
ENOVAL = Constant('ENOVAL')

MODE_NONE = 0
MODE_RAW = 1
MODE_BINARY = 2
MODE_TEXT = 3
MODE_PICKLE = 4

DEFAULT_SETTINGS = {
    u'statistics': 0,  # False
    u'tag_index': 0,   # False
    u'eviction_policy': u'least-recently-stored',
    u'size_limit': 2 ** 30,  # 1gb
    u'cull_limit': 10,
    u'sqlite_cache_size': 2 ** 13,   # 8,192 pages
    u'sqlite_journal_mode': u'WAL',
    u'sqlite_mmap_size': 2 ** 26,    # 64mb
    u'sqlite_synchronous': u'NORMAL',
    u'disk_min_file_size': 2 ** 15,  # 32kb
    u'disk_pickle_protocol': pickle.HIGHEST_PROTOCOL,
}

METADATA = {
    u'count': 0,
    u'size': 0,
    u'hits': 0,
    u'misses': 0,
}

EVICTION_POLICY = {
    'none': {
        'init': None,
        'get': None,
        'cull': None,
    },
    'least-recently-stored': {
        'init': (
            'CREATE INDEX IF NOT EXISTS Cache_store_time ON'
            ' Cache (store_time)'
        ),
        'get': None,
        'cull': 'SELECT %s FROM Cache ORDER BY store_time LIMIT ?',
    },
    'least-recently-used': {
        'init': (
            'CREATE INDEX IF NOT EXISTS Cache_access_time ON'
            ' Cache (access_time)'
        ),
        'get': 'access_time = ((julianday("now") - 2440587.5) * 86400.0)',
        'cull': 'SELECT %s FROM Cache ORDER BY access_time LIMIT ?',
    },
    'least-frequently-used': {
        'init': (
            'CREATE INDEX IF NOT EXISTS Cache_access_count ON'
            ' Cache (access_count)'
        ),
        'get': 'access_count = access_count + 1',
        'cull': 'SELECT %s FROM Cache ORDER BY access_count LIMIT ?',
    },
}


class Disk(object):
    "Cache key and value serialization for SQLite database and files."
    def __init__(self, directory, min_file_size=0, pickle_protocol=0):
        """Initialize disk instance.

        :param str directory: directory path
        :param int min_file_size: minimum size for file use
        :param int pickle_protocol: pickle protocol for serialization

        """
        self._directory = directory
        self.min_file_size = min_file_size
        self.pickle_protocol = pickle_protocol


    def hash(self, key):
        """Compute portable hash for `key`.

        :param key: key to hash
        :return: hash value

        """
        mask = 0xFFFFFFFF
        disk_key, _ = self.put(key)
        type_disk_key = type(disk_key)

        if type_disk_key is sqlite3.Binary:
            return zlib.adler32(disk_key) & mask
        elif type_disk_key is TextType:
            return zlib.adler32(disk_key.encode('utf-8')) & mask  # pylint: disable=no-member
        elif type_disk_key in INT_TYPES:
            return disk_key % mask
        else:
            assert type_disk_key is float
            return zlib.adler32(struct.pack('!d', disk_key)) & mask


    def put(self, key):
        """Convert `key` to fields key and raw for Cache table.

        :param key: key to convert
        :return: (database key, raw boolean) pair

        """
        # pylint: disable=bad-continuation,unidiomatic-typecheck
        type_key = type(key)

        if type_key is BytesType:
            return sqlite3.Binary(key), True
        elif ((type_key is TextType)
                or (type_key in INT_TYPES
                    and -9223372036854775808 <= key <= 9223372036854775807)
                or (type_key is float)):
            return key, True
        else:
            result = pickle.dumps(key, protocol=self.pickle_protocol)
            return sqlite3.Binary(result), False


    def get(self, key, raw):
        """Convert fields `key` and `raw` from Cache table to key.

        :param key: database key to convert
        :param bool raw: flag indicating raw database storage
        :return: corresponding Python key

        """
        # pylint: disable=no-self-use,unidiomatic-typecheck
        if raw:
            return BytesType(key) if type(key) is sqlite3.Binary else key
        else:
            return pickle.load(BytesIO(key))


    def store(self, value, read):
        """Convert `value` to fields size, mode, filename, and value for Cache
        table.

        :param value: value to convert
        :param bool read: True when value is file-like object
        :return: (size, mode, filename, value) tuple for Cache table

        """
        # pylint: disable=unidiomatic-typecheck
        type_value = type(value)
        min_file_size = self.min_file_size

        if ((type_value is TextType and len(value) < min_file_size)
                or (type_value in INT_TYPES
                    and -9223372036854775808 <= value <= 9223372036854775807)
                or (type_value is float)):
            return 0, MODE_RAW, None, value
        elif type_value is BytesType:
            if len(value) < min_file_size:
                return 0, MODE_RAW, None, sqlite3.Binary(value)
            else:
                filename, full_path = self.filename()

                with open(full_path, 'wb') as writer:
                    writer.write(value)

                return len(value), MODE_BINARY, filename, None
        elif type_value is TextType:
            filename, full_path = self.filename()

            with io_open(full_path, 'w', encoding='UTF-8') as writer:
                writer.write(value)

            size = op.getsize(full_path)
            return size, MODE_TEXT, filename, None
        elif read:
            size = 0
            reader = ft.partial(value.read, 2 ** 22)
            filename, full_path = self.filename()

            with open(full_path, 'wb') as writer:
                for chunk in iter(reader, b''):
                    size += len(chunk)
                    writer.write(chunk)

            return size, MODE_BINARY, filename, None
        else:
            result = pickle.dumps(value, protocol=self.pickle_protocol)

            if len(result) < min_file_size:
                return 0, MODE_PICKLE, None, sqlite3.Binary(result)
            else:
                filename, full_path = self.filename()

                with open(full_path, 'wb') as writer:
                    writer.write(result)

                return len(result), MODE_PICKLE, filename, None


    def fetch(self, mode, filename, value, read):
        """Convert fields `mode`, `filename`, and `value` from Cache table to
        value.

        :param int mode: value mode raw, binary, text, or pickle
        :param str filename: filename of corresponding value
        :param value: database value
        :param bool read: when True, return an open file handle
        :return: corresponding Python value

        """
        # pylint: disable=no-self-use,unidiomatic-typecheck
        if mode == MODE_RAW:
            return BytesType(value) if type(value) is sqlite3.Binary else value
        elif mode == MODE_BINARY:
            if read:
                return open(op.join(self._directory, filename), 'rb')
            else:
                with open(op.join(self._directory, filename), 'rb') as reader:
                    return reader.read()
        elif mode == MODE_TEXT:
            full_path = op.join(self._directory, filename)
            with io_open(full_path, 'r', encoding='UTF-8') as reader:
                return reader.read()
        elif mode == MODE_PICKLE:
            if value is None:
                with open(op.join(self._directory, filename), 'rb') as reader:
                    return pickle.load(reader)
            else:
                return pickle.load(BytesIO(value))


    def filename(self):
        """Return filename and full-path tuple for file storage.

        Filename will be a randomly generated 28 character hexadecimal string
        with ".val" suffixed. Two levels of sub-directories will be used to
        reduce the size of directories. On older filesystems, lookups in
        directories with many files are slow.

        """
        hex_name = codecs.encode(os.urandom(16), 'hex').decode('utf-8')
        sub_dir = op.join(hex_name[:2], hex_name[2:4])
        name = hex_name[4:] + '.val'
        directory = op.join(self._directory, sub_dir)

        try:
            os.makedirs(directory)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise

        filename = op.join(sub_dir, name)
        full_path = op.join(self._directory, filename)
        return filename, full_path


    def remove(self, filename):
        """Remove a file given by `filename`.

        This method is cross-thread and cross-process safe. If an "error no
        entry" occurs, it is suppressed.

        :param str filename: relative path to file

        """
        full_path = op.join(self._directory, filename)

        try:
            os.remove(full_path)
        except WindowsError:
            pass
        except OSError as error:
            if error.errno != errno.ENOENT:
                # ENOENT may occur if two caches attempt to delete the same
                # file at the same time.
                raise


class Timeout(Exception):
    "Database timeout expired."
    pass


class UnknownFileWarning(UserWarning):
    "Warning used by Cache.check for unknown files."
    pass


class EmptyDirWarning(UserWarning):
    "Warning used by Cache.check for empty directories."
    pass


class Cache(object):
    "Disk and file backed cache."
    # pylint: disable=bad-continuation
    def __init__(self, directory, timeout=60, disk=Disk, **settings):
        """Initialize cache instance.

        :param str directory: cache directory
        :param float timeout: SQLite connection timeout
        :param disk: Disk type or subclass for serialization
        :param settings: any of DEFAULT_SETTINGS

        """
        try:
            assert issubclass(disk, Disk)
        except (TypeError, AssertionError):
            raise ValueError('disk must subclass diskcache.Disk')

        self._directory = directory
        self._timeout = 60    # Use 1 minute timeout for initialization.
        self._local = threading.local()

        if not op.isdir(directory):
            try:
                os.makedirs(directory, 0o755)
            except OSError as error:
                if error.errno != errno.EEXIST:
                    raise EnvironmentError(
                        error.errno,
                        'Cache directory "%s" does not exist'
                        ' and could not be created' % self._directory
                    )

        sql = self._sql

        # Setup Settings table.

        sql('CREATE TABLE IF NOT EXISTS Settings ('
            ' key TEXT NOT NULL UNIQUE,'
            ' value)'
        )

        current_settings = dict(sql(
            'SELECT key, value FROM Settings'
        ).fetchall())

        sets = DEFAULT_SETTINGS.copy()
        sets.update(current_settings)
        sets.update(settings)

        for key in METADATA:
            sets.pop(key, None)

        # Setup Disk object (must happen after settings initialized).

        kwargs = {
            key[5:]: value for key, value in sets.items()
            if key.startswith('disk_')
        }
        self._disk = disk(directory, **kwargs)

        # Set cached attributes: updates settings and sets pragmas.

        for key, value in sets.items():
            query = 'INSERT OR REPLACE INTO Settings VALUES (?, ?)'
            sql(query, (key, value))
            self.reset(key, value)

        for key, value in METADATA.items():
            query = 'INSERT OR IGNORE INTO Settings VALUES (?, ?)'
            sql(query, (key, value))
            self.reset(key)

        (self._page_size,), = sql('PRAGMA page_size').fetchall()

        # Setup Cache table.

        sql('CREATE TABLE IF NOT EXISTS Cache ('
            ' rowid INTEGER PRIMARY KEY,'
            ' key BLOB,'
            ' raw INTEGER,'
            ' version INTEGER DEFAULT 0,'
            ' store_time REAL,'
            ' expire_time REAL,'
            ' access_time REAL,'
            ' access_count INTEGER DEFAULT 0,'
            ' tag BLOB,'
            ' size INTEGER DEFAULT 0,'
            ' mode INTEGER DEFAULT 0,'
            ' filename TEXT,'
            ' value BLOB)'
        )

        sql('CREATE UNIQUE INDEX IF NOT EXISTS Cache_key_raw ON'
            ' Cache(key, raw)'
        )

        sql('CREATE INDEX IF NOT EXISTS Cache_expire_time ON'
            ' Cache (expire_time)'
        )

        query = EVICTION_POLICY[self.eviction_policy]['init']

        if query is not None:
            sql(query)

        # Use triggers to keep Metadata updated.

        sql('CREATE TRIGGER IF NOT EXISTS Settings_count_insert'
            ' AFTER INSERT ON Cache FOR EACH ROW BEGIN'
            ' UPDATE Settings SET value = value + 1'
            ' WHERE key = "count"; END'
        )

        sql('CREATE TRIGGER IF NOT EXISTS Settings_count_delete'
            ' AFTER DELETE ON Cache FOR EACH ROW BEGIN'
            ' UPDATE Settings SET value = value - 1'
            ' WHERE key = "count"; END'
        )

        sql('CREATE TRIGGER IF NOT EXISTS Settings_size_insert'
            ' AFTER INSERT ON Cache FOR EACH ROW BEGIN'
            ' UPDATE Settings SET value = value + NEW.size'
            ' WHERE key = "size"; END'
        )

        sql('CREATE TRIGGER IF NOT EXISTS Settings_size_update'
            ' AFTER UPDATE ON Cache FOR EACH ROW BEGIN'
            ' UPDATE Settings'
            ' SET value = value + NEW.size - OLD.size'
            ' WHERE key = "size"; END'
        )

        sql('CREATE TRIGGER IF NOT EXISTS Settings_size_delete'
            ' AFTER DELETE ON Cache FOR EACH ROW BEGIN'
            ' UPDATE Settings SET value = value - OLD.size'
            ' WHERE key = "size"; END'
        )

        # Create tag index if requested.

        if self.tag_index:  # pylint: disable=no-member
            self.create_tag_index()
        else:
            self.drop_tag_index()

        # Close and re-open database connection with given timeout.

        self.close()
        self._timeout = timeout
        assert self._sql


    @property
    def directory(self):
        """Cache directory."""
        return self._directory


    @property
    def timeout(self):
        """SQLite connection timeout value in seconds."""
        return self._timeout


    @property
    def disk(self):
        """Disk used for serialization."""
        return self._disk


    @property
    def _sql(self):
        con = getattr(self._local, 'con', None)

        if con is None:
            con = self._local.con = sqlite3.connect(
                op.join(self._directory, DBNAME),
                timeout=self._timeout,
                isolation_level=None,
            )

        return con.execute


    @cl.contextmanager
    def _transact(self, filename=None):
        sql = self._sql
        filenames = []
        _disk_remove = self._disk.remove

        try:
            sql('BEGIN IMMEDIATE')
        except sqlite3.OperationalError:
            if filename is not None:
                _disk_remove(filename)
            raise Timeout

        try:
            yield sql, filenames.append
        except BaseException:
            sql('ROLLBACK')
            raise
        else:
            sql('COMMIT')
            for filename in filenames:
                if filename is not None:
                    _disk_remove(filename)


    def set(self, key, value, expire=None, read=False, tag=None):
        """Set `key` and `value` item in cache.

        When `read` is `True`, `value` should be a file-like object opened
        for reading in binary mode.

        :param key: key for item
        :param value: value for item
        :param float expire: seconds until item expires
            (default None, no expiry)
        :param bool read: read value as bytes from file (default False)
        :param str tag: text to associate with key (default None)
        :return: True if item was set
        :raises Timeout: if database timeout expires

        """
        now = time.time()
        db_key, raw = self._disk.put(key)
        expire_time = None if expire is None else now + expire
        size, mode, filename, db_value = self._disk.store(value, read)
        columns = (expire_time, tag, size, mode, filename, db_value)

        # The order of SELECT, UPDATE, and INSERT is important below.
        #
        # Typical cache usage pattern is:
        #
        # value = cache.get(key)
        # if value is None:
        #     value = expensive_calculation()
        #     cache.set(key, value)
        #
        # Cache.get does not evict expired keys to avoid writes during lookups.
        # Commonly used/expired keys will therefore remain in the cache making
        # an UPDATE the preferred path.
        #
        # The alternative is to assume the key is not present by first trying
        # to INSERT and then handling the IntegrityError that occurs from
        # violating the UNIQUE constraint. This optimistic approach was
        # rejected based on the common cache usage pattern.
        #
        # INSERT OR REPLACE aka UPSERT is not used because the old filename may
        # need cleanup.

        with self._transact(filename) as (sql, cleanup):
            rows = sql(
                'SELECT rowid, filename FROM Cache'
                ' WHERE key = ? AND raw = ?',
                (db_key, raw),
            ).fetchall()

            if rows:
                (rowid, old_filename), = rows
                cleanup(old_filename)
                self._row_update(rowid, now, columns)
            else:
                self._row_insert(db_key, raw, now, columns)

            self._cull(now, sql, cleanup)

            return True


    __setitem__ = set


    def _row_update(self, rowid, now, columns):
        sql = self._sql
        expire_time, tag, size, mode, filename, value = columns
        sql('UPDATE Cache SET'
            ' version = ?,'
            ' store_time = ?,'
            ' expire_time = ?,'
            ' access_time = ?,'
            ' access_count = ?,'
            ' tag = ?,'
            ' size = ?,'
            ' mode = ?,'
            ' filename = ?,'
            ' value = ?'
            ' WHERE rowid = ?', (
                0,            # version
                now,          # store_time
                expire_time,
                now,          # access_time
                0,            # access_count
                tag,
                size,
                mode,
                filename,
                value,
                rowid,
            ),
        )


    def _row_insert(self, key, raw, now, columns):
        sql = self._sql
        expire_time, tag, size, mode, filename, value = columns
        sql('INSERT INTO Cache('
            ' key, raw, version, store_time, expire_time, access_time,'
            ' access_count, tag, size, mode, filename, value'
            ') VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (
                key,
                raw,
                0,           # version
                now,         # store_time
                expire_time,
                now,         # access_time
                0,           # access_count
                tag,
                size,
                mode,
                filename,
                value,
            ),
        )


    def _cull(self, now, sql, cleanup):
        cull_limit = self.cull_limit

        if cull_limit == 0:
            return

        # Evict expired keys.

        select_expired_template = (
            'SELECT %s FROM Cache'
            ' WHERE expire_time IS NOT NULL AND expire_time < ?'
            ' ORDER BY expire_time LIMIT ?'
        )

        select_expired = select_expired_template % 'filename'
        rows = sql(select_expired, (now, cull_limit)).fetchall()

        if rows:
            delete_expired = (
                'DELETE FROM Cache WHERE rowid IN (%s)'
                % (select_expired_template % 'rowid')
            )
            sql(delete_expired, (now, cull_limit))

            for filename, in rows:
                cleanup(filename)

            cull_limit -= len(rows)

            if cull_limit == 0:
                return

        # Evict keys by policy.

        select_policy_template = EVICTION_POLICY[self.eviction_policy]['cull']

        if select_policy_template is None or self.volume() < self.size_limit:
            return

        select_policy = select_policy_template % 'filename'

        rows = sql(select_policy, (cull_limit,)).fetchall()

        if rows:
            delete_policy = (
                'DELETE FROM Cache WHERE rowid IN (%s)'
                % (select_policy_template % 'rowid')
            )
            sql(delete_policy, (cull_limit,))

            for filename, in rows:
                cleanup(filename)


    def add(self, key, value, expire=None, read=False, tag=None):
        """Add `key` and `value` item to cache.

        Similar to `set`, but only add to cache if key not present.

        Operation is atomic. Only one concurrent add operation for a given key
        will succeed.

        When `read` is `True`, `value` should be a file-like object opened
        for reading in binary mode.

        :param key: key for item
        :param value: value for item
        :param float expire: seconds until the key expires
            (default None, no expiry)
        :param bool read: read value as bytes from file (default False)
        :param str tag: text to associate with key (default None)
        :return: True if item was added
        :raises Timeout: if database timeout expires

        """
        now = time.time()
        db_key, raw = self._disk.put(key)
        expire_time = None if expire is None else now + expire
        size, mode, filename, db_value = self._disk.store(value, read)
        columns = (expire_time, tag, size, mode, filename, db_value)

        with self._transact(filename) as (sql, cleanup):
            rows = sql(
                'SELECT rowid, filename, expire_time FROM Cache'
                ' WHERE key = ? AND raw = ?',
                (db_key, raw),
            ).fetchall()

            if rows:
                (rowid, old_filename, old_expire_time), = rows

                if old_expire_time is None or old_expire_time > now:
                    cleanup(filename)
                    return False

                cleanup(old_filename)
                self._row_update(rowid, now, columns)
            else:
                self._row_insert(db_key, raw, now, columns)

            self._cull(now, sql, cleanup)

            return True


    def incr(self, key, delta=1, default=0):
        """Increment value by delta for item with key.

        If key is missing and default is None then raise KeyError. Else if key
        is missing and default is not None then use default for value.

        Operation is atomic. All concurrent increment operations will be
        counted individually.

        Assumes value may be stored in a SQLite column. Most builds that target
        machines with 64-bit pointer widths will support 64-bit signed
        integers.

        :param key: key for item
        :param int delta: amount to increment (default 1)
        :param int default: value if key is missing (default None)
        :return: new value for item
        :raises KeyError: if key is not found and default is None
        :raises Timeout: if database timeout expires

        """
        now = time.time()
        db_key, raw = self._disk.put(key)
        select = (
            'SELECT rowid, expire_time, filename, value FROM Cache'
            ' WHERE key = ? AND raw = ?'
        )

        with self._transact() as (sql, cleanup):
            rows = sql(select, (db_key, raw)).fetchall()

            if not rows:
                if default is None:
                    raise KeyError(key)

                value = default + delta
                columns = (None, None) + self._disk.store(value, False)
                self._row_insert(db_key, raw, now, columns)
                self._cull(now, sql, cleanup)
                return value

            (rowid, expire_time, filename, value), = rows

            if expire_time is not None and expire_time < now:
                if default is None:
                    raise KeyError(key)

                value = default + delta
                columns = (None, None) + self._disk.store(value, False)
                self._row_update(rowid, now, columns)
                self._cull(now, sql, cleanup)
                cleanup(filename)
                return value

            value += delta

            columns = 'store_time = ?, value = ?'
            update_column = EVICTION_POLICY[self.eviction_policy]['get']
            columns += '' if update_column is None else ', ' + update_column
            update = 'UPDATE Cache SET %s WHERE rowid = ?' % columns
            sql(update, (now, value, rowid))

            return value


    def decr(self, key, delta=1, default=0):
        """Decrement value by delta for item with key.

        If key is missing and default is None then raise KeyError. Else if key
        is missing and default is not None then use default for value.

        Operation is atomic. All concurrent decrement operations will be
        counted individually.

        Unlike Memcached, negative values are supported. Value may be
        decremented below zero.

        Assumes value may be stored in a SQLite column. Most builds that target
        machines with 64-bit pointer widths will support 64-bit signed
        integers.

        :param key: key for item
        :param int delta: amount to decrement (default 1)
        :param int default: value if key is missing (default 0)
        :return: new value for item
        :raises KeyError: if key is not found and default is None
        :raises Timeout: if database timeout expires

        """
        return self.incr(key, -delta, default)


    def get(self, key, default=None, read=False, expire_time=False, tag=False):
        """Retrieve value from cache. If `key` is missing, return `default`.

        :param key: key for item
        :param default: value to return if key is missing (default None)
        :param bool read: if True, return file handle to value
            (default False)
        :param bool expire_time: if True, return expire_time in tuple
            (default False)
        :param bool tag: if True, return tag in tuple (default False)
        :return: value for item or default if key not found
        :raises Timeout: if database timeout expires

        """
        db_key, raw = self._disk.put(key)
        update_column = EVICTION_POLICY[self.eviction_policy]['get']
        update = 'UPDATE Cache SET %s WHERE rowid = ?'
        select = (
            'SELECT rowid, expire_time, tag, mode, filename, value'
            ' FROM Cache WHERE key = ? AND raw = ?'
            ' AND (expire_time IS NULL OR expire_time > ?)'
        )

        if expire_time and tag:
            default = (default, None, None)
        elif expire_time or tag:
            default = (default, None)

        if not self.statistics and update_column is None:
            # Fast path, no transaction necessary.

            rows = self._sql(select, (db_key, raw, time.time())).fetchall()

            if not rows:
                return default

            (rowid, db_expire_time, db_tag, mode, filename, db_value), = rows

            try:
                value = self._disk.fetch(mode, filename, db_value, read)
            except IOError as error:
                if error.errno == errno.ENOENT:
                    # Key was deleted before we could retrieve result.
                    return default
                else:
                    raise

        else:  # Slow path, transaction required.

            cache_hit = (
                'UPDATE Settings SET value = value + 1 WHERE key = "hits"'
            )
            cache_miss = (
                'UPDATE Settings SET value = value + 1 WHERE key = "misses"'
            )

            with self._transact() as (sql, _):
                rows = sql(select, (db_key, raw, time.time())).fetchall()

                if not rows:
                    if self.statistics:
                        sql(cache_miss)
                    return default

                (rowid, db_expire_time, db_tag,
                     mode, filename, db_value), = rows

                try:
                    value = self._disk.fetch(mode, filename, db_value, read)
                except IOError as error:
                    if error.errno == errno.ENOENT:
                        # Key was deleted before we could retrieve result.
                        if self.statistics:
                            sql(cache_miss)
                        return default
                    else:
                        raise

                if self.statistics:
                    sql(cache_hit)

                if update_column is not None:
                    sql(update % update_column, (rowid,))

        if expire_time and tag:
            return (value, db_expire_time, db_tag)
        elif expire_time:
            return (value, db_expire_time)
        elif tag:
            return (value, db_tag)
        else:
            return value


    def __getitem__(self, key):
        """Return corresponding value for `key` from cache.

        :param key: key matching item
        :return: corresponding value
        :raises KeyError: if key is not found
        :raises Timeout: if database timeout expires

        """
        value = self.get(key, default=ENOVAL)
        if value is ENOVAL:
            raise KeyError(key)
        return value


    def read(self, key):
        """Return file handle value corresponding to `key` from cache.

        :param key: key matching item
        :return: file open for reading in binary mode
        :raises KeyError: if key is not found
        :raises Timeout: if database timeout expires

        """
        handle = self.get(key, default=ENOVAL, read=True)
        if handle is ENOVAL:
            raise KeyError(key)
        return handle


    def __contains__(self, key):
        """Return `True` if `key` matching item is found in cache.

        :param key: key matching item
        :return: True if key matching item

        """
        sql = self._sql
        db_key, raw = self._disk.put(key)
        select = (
            'SELECT rowid FROM Cache'
            ' WHERE key = ? AND raw = ?'
            ' AND (expire_time IS NULL OR expire_time > ?)'
        )

        rows = sql(select, (db_key, raw, time.time())).fetchall()

        return bool(rows)


    def pop(self, key, default=None, expire_time=False, tag=False):
        """Remove corresponding item for `key` from cache and return value.

        If `key` is missing, return `default`.

        Operation is atomic. Concurrent operations will be serialized.

        :param key: key for item
        :param default: value to return if key is missing (default None)
        :param bool expire_time: if True, return expire_time in tuple
            (default False)
        :param bool tag: if True, return tag in tuple (default False)
        :return: value for item or default if key not found
        :raises Timeout: if database timeout expires

        """
        db_key, raw = self._disk.put(key)
        select = (
            'SELECT rowid, expire_time, tag, mode, filename, value'
            ' FROM Cache WHERE key = ? AND raw = ?'
            ' AND (expire_time IS NULL OR expire_time > ?)'
        )

        if expire_time and tag:
            default = default, None, None
        elif expire_time or tag:
            default = default, None

        with self._transact() as (sql, _):
            rows = sql(select, (db_key, raw, time.time())).fetchall()

            if not rows:
                return default

            (rowid, db_expire_time, db_tag, mode, filename, db_value), = rows

            sql('DELETE FROM Cache WHERE rowid = ?', (rowid,))

        try:
            value = self._disk.fetch(mode, filename, db_value, False)
        except IOError as error:
            if error.errno == errno.ENOENT:
                # Key was deleted before we could retrieve result.
                return default
            else:
                raise
        finally:
            if filename is not None:
                self._disk.remove(filename)

        if expire_time and tag:
            return value, db_expire_time, db_tag
        elif expire_time:
            return value, db_expire_time
        elif tag:
            return value, db_tag
        else:
            return value


    def __delitem__(self, key):
        """Delete corresponding item for `key` from cache.

        :param key: key matching item
        :raises KeyError: if key is not found
        :raises Timeout: if database timeout expires

        """
        db_key, raw = self._disk.put(key)

        with self._transact() as (sql, cleanup):
            rows = sql(
                'SELECT rowid, filename FROM Cache'
                ' WHERE key = ? AND raw = ?'
                ' AND (expire_time IS NULL OR expire_time > ?)',
                (db_key, raw, time.time()),
            ).fetchall()

            if not rows:
                raise KeyError(key)

            (rowid, filename), = rows
            sql('DELETE FROM Cache WHERE rowid = ?', (rowid,))
            cleanup(filename)

            return True


    def delete(self, key):
        """Delete corresponding item for `key` from cache.

        Missing keys are ignored.

        :param key: key matching item
        :return: True if item was deleted
        :raises Timeout: if database timeout expires

        """
        try:
            return self.__delitem__(key)
        except KeyError:
            return False


    def push(self, value, prefix=None, side='back', expire=None, read=False,
             tag=None):
        """Push `value` onto `side` of queue identified by `prefix` in cache.

        When prefix is None, integer keys are used. Otherwise, string keys are
        used in the format "prefix-integer". Integer starts at 500 trillion.

        Defaults to pushing value on back of queue. Set side to 'front' to push
        value on front of queue. Side must be one of 'back' or 'front'.

        Operation is atomic. Concurrent operations will be serialized.

        When `read` is `True`, `value` should be a file-like object opened
        for reading in binary mode.

        See also `Cache.pull`.

        >>> cache = Cache('/tmp/test')
        >>> _ = cache.clear()
        >>> print(cache.push('first value'))
        500000000000000
        >>> cache.get(500000000000000)
        'first value'
        >>> print(cache.push('second value'))
        500000000000001
        >>> print(cache.push('third value', side='front'))
        499999999999999
        >>> cache.push(1234, prefix='userids')
        'userids-500000000000000'

        :param value: value for item
        :param str prefix: key prefix (default None, key is integer)
        :param str side: either 'back' or 'front' (default 'back')
        :param float expire: seconds until the key expires
            (default None, no expiry)
        :param bool read: read value as bytes from file (default False)
        :param str tag: text to associate with key (default None)
        :return: key for item in cache
        :raises Timeout: if database timeout expires

        """
        if prefix is None:
            min_key = 0
            max_key = 999999999999999
        else:
            min_key = prefix + '-000000000000000'
            max_key = prefix + '-999999999999999'

        now = time.time()
        raw = True
        expire_time = None if expire is None else now + expire
        size, mode, filename, db_value = self._disk.store(value, read)
        columns = (expire_time, tag, size, mode, filename, db_value)
        order = {'back': 'DESC', 'front': 'ASC'}
        select = (
            'SELECT key FROM Cache'
            ' WHERE ? < key AND key < ? AND raw = ?'
            ' ORDER BY key %s LIMIT 1'
        ) % order[side]

        with self._transact(filename) as (sql, cleanup):
            rows = sql(select, (min_key, max_key, raw)).fetchall()

            if rows:
                (key,), = rows

                if prefix is not None:
                    num = int(key[(key.rfind('-') + 1):])
                else:
                    num = key

                if side == 'back':
                    num += 1
                else:
                    assert side == 'front'
                    num -= 1
            else:
                num = 500000000000000

            if prefix is not None:
                db_key = '{0}-{1:015d}'.format(prefix, num)
            else:
                db_key = num

            self._row_insert(db_key, raw, now, columns)
            self._cull(now, sql, cleanup)

            return db_key


    def pull(self, prefix=None, default=(None, None), side='front',
             expire_time=False, tag=False):
        """Pull key and value item pair from `side` of queue in cache.

        When prefix is None, integer keys are used. Otherwise, string keys are
        used in the format "prefix-integer". Integer starts at 500 trillion.

        If queue is empty, return default.

        Defaults to pulling key and value item pairs from front of queue. Set
        side to 'back' to pull from back of queue. Side must be one of 'front'
        or 'back'.

        Operation is atomic. Concurrent operations will be serialized.

        See also `Cache.push` and `Cache.get`.

        >>> cache = Cache('/tmp/test')
        >>> _ = cache.clear()
        >>> cache.pull()
        (None, None)
        >>> for letter in 'abc':
        ...     print(cache.push(letter))
        500000000000000
        500000000000001
        500000000000002
        >>> key, value = cache.pull()
        >>> print(key)
        500000000000000
        >>> value
        'a'
        >>> _, value = cache.pull(side='back')
        >>> value
        'c'
        >>> cache.push(1234, 'userids')
        'userids-500000000000000'
        >>> _, value = cache.pull('userids')
        >>> value
        1234

        :param str prefix: key prefix (default None, key is integer)
        :param default: value to return if key is missing
            (default (None, None))
        :param str side: either 'front' or 'back' (default 'front')
        :param bool expire_time: if True, return expire_time in tuple
            (default False)
        :param bool tag: if True, return tag in tuple (default False)
        :return: key and value item pair or default if queue is empty
        :raises Timeout: if database timeout expires

        """
        if prefix is None:
            min_key = 0
            max_key = 999999999999999
        else:
            min_key = prefix + '-000000000000000'
            max_key = prefix + '-999999999999999'

        order = {'front': 'ASC', 'back': 'DESC'}
        select = (
            'SELECT rowid, key, expire_time, tag, mode, filename, value'
            ' FROM Cache WHERE ? < key AND key < ? AND raw = 1'
            ' ORDER BY key %s LIMIT 1'
        ) % order[side]

        if expire_time and tag:
            default = default, None, None
        elif expire_time or tag:
            default = default, None

        while True:
            with self._transact() as (sql, cleanup):
                rows = sql(select, (min_key, max_key)).fetchall()

                if not rows:
                    return default

                (rowid, key, db_expire, db_tag, mode, name, db_value), = rows

                sql('DELETE FROM Cache WHERE rowid = ?', (rowid,))

                if db_expire is not None and db_expire < time.time():
                    cleanup(name)
                else:
                    break

        try:
            value = self._disk.fetch(mode, name, db_value, False)
        except IOError as error:
            if error.errno == errno.ENOENT:
                # Key was deleted before we could retrieve result.
                return default
            else:
                raise
        finally:
            if name is not None:
                self._disk.remove(name)

        if expire_time and tag:
            return (key, value), db_expire, db_tag
        elif expire_time:
            return (key, value), db_expire
        elif tag:
            return (key, value), db_tag
        else:
            return key, value


    def check(self, fix=False):
        """Check database and file system consistency.

        Intended for use in testing and post-mortem error analysis.

        While checking the Cache table for consistency, a writer lock is held
        on the database. The lock blocks other cache clients from writing to
        the database. For caches with many file references, the lock may be
        held for a long time. For example, local benchmarking shows that a
        cache with 1,000 file references takes ~60ms to check.

        :param bool fix: correct inconsistencies
        :return: list of warnings
        :raises Timeout: if database timeout expires

        """
        # pylint: disable=access-member-before-definition,W0201
        with warnings.catch_warnings(record=True) as warns:
            sql = self._sql

            # Check integrity of database.

            rows = sql('PRAGMA integrity_check').fetchall()

            if len(rows) != 1 or rows[0][0] != u'ok':
                for message, in rows:
                    warnings.warn(message)

            if fix:
                sql('VACUUM')

            with self._transact() as (sql, _):

                # Check Cache.filename against file system.

                filenames = set()
                select = (
                    'SELECT rowid, size, filename FROM Cache'
                    ' WHERE filename IS NOT NULL'
                )

                rows = sql(select).fetchall()

                for rowid, size, filename in rows:
                    full_path = op.join(self._directory, filename)
                    filenames.add(full_path)

                    if op.exists(full_path):
                        real_size = op.getsize(full_path)

                        if size != real_size:
                            message = 'wrong file size: %s, %d != %d'
                            args = full_path, real_size, size
                            warnings.warn(message % args)

                            if fix:
                                sql('UPDATE Cache SET size = ?'
                                    ' WHERE rowid = ?',
                                    (real_size, rowid),
                                )

                        continue

                    warnings.warn('file not found: %s' % full_path)

                    if fix:
                        sql('DELETE FROM Cache WHERE rowid = ?', (rowid,))

                # Check file system against Cache.filename.

                for dirpath, _, files in os.walk(self._directory):
                    paths = [op.join(dirpath, filename) for filename in files]
                    error = set(paths) - filenames

                    for full_path in error:
                        if DBNAME in full_path:
                            continue

                        message = 'unknown file: %s' % full_path
                        warnings.warn(message, UnknownFileWarning)

                        if fix:
                            os.remove(full_path)

                # Check for empty directories.

                for dirpath, dirs, files in os.walk(self._directory):
                    if not (dirs or files):
                        message = 'empty directory: %s' % dirpath
                        warnings.warn(message, EmptyDirWarning)

                        if fix:
                            os.rmdir(dirpath)

                # Check Settings.count against count of Cache rows.

                self.reset('count')
                (count,), = sql('SELECT COUNT(key) FROM Cache').fetchall()

                if self.count != count:
                    message = 'Settings.count != COUNT(Cache.key); %d != %d'
                    warnings.warn(message % (self.count, count))

                    if fix:
                        sql('UPDATE Settings SET value = ? WHERE key = ?',
                            (count, 'count'),
                        )

                # Check Settings.size against sum of Cache.size column.

                self.reset('size')
                select_size = 'SELECT COALESCE(SUM(size), 0) FROM Cache'
                (size,), = sql(select_size).fetchall()

                if self.size != size:
                    message = 'Settings.size != SUM(Cache.size); %d != %d'
                    warnings.warn(message % (self.size, size))

                    if fix:
                        sql('UPDATE Settings SET value = ? WHERE key =?',
                            (size, 'size'),
                        )

            return warns


    def create_tag_index(self):
        """Create tag index on cache database.

        It is better to initialize cache with `tag_index=True` than use this.

        :raises Timeout: if database timeout expires

        """
        sql = self._sql
        sql('CREATE INDEX IF NOT EXISTS Cache_tag_rowid ON Cache(tag, rowid)')
        self.reset('tag_index', 1)


    def drop_tag_index(self):
        """Drop tag index on cache database.

        :raises Timeout: if database timeout expires

        """
        sql = self._sql
        sql('DROP INDEX IF EXISTS Cache_tag_rowid')
        self.reset('tag_index', 0)


    def evict(self, tag):
        """Remove items with matching `tag` from cache.

        Removing items is an iterative process. In each iteration, a subset of
        items is removed. Concurrent writes may occur between iterations.

        If a :exc:`Timeout` occurs, the first element of the exception's
        `args` attribute will be the number of items removed before the
        exception occurred.

        :param str tag: tag identifying items
        :return: count of rows removed
        :raises Timeout: if database timeout expires

        """
        select = (
            'SELECT rowid, filename FROM Cache'
            ' WHERE tag = ? AND rowid > ?'
            ' ORDER BY rowid LIMIT ?'
        )
        args = [tag, 0, 100]
        return self._select_delete(select, args, arg_index=1)


    def expire(self, now=None):
        """Remove expired items from cache.

        Removing items is an iterative process. In each iteration, a subset of
        items is removed. Concurrent writes may occur between iterations.

        If a :exc:`Timeout` occurs, the first element of the exception's
        `args` attribute will be the number of items removed before the
        exception occurred.

        :param float now: current time (default None, ``time.time()`` used)
        :return: count of items removed
        :raises Timeout: if database timeout expires

        """
        select = (
            'SELECT rowid, expire_time, filename FROM Cache'
            ' WHERE ? < expire_time AND expire_time < ?'
            ' ORDER BY expire_time LIMIT ?'
        )
        args = [0, now or time.time(), 100]
        return self._select_delete(select, args, row_index=1)


    def clear(self):
        """Remove all items from cache.

        Removing items is an iterative process. In each iteration, a subset of
        items is removed. Concurrent writes may occur between iterations.

        If a :exc:`Timeout` occurs, the first element of the exception's
        `args` attribute will be the number of items removed before the
        exception occurred.

        :return: count of rows removed
        :raises Timeout: if database timeout expires

        """
        select = (
            'SELECT rowid, filename FROM Cache'
            ' WHERE rowid > ?'
            ' ORDER BY rowid LIMIT ?'
        )
        args = [0, 100]
        return self._select_delete(select, args)


    def _select_delete(self, select, args, row_index=0, arg_index=0):
        count = 0
        delete = 'DELETE FROM Cache WHERE rowid IN (%s)'

        try:
            while True:
                with self._transact() as (sql, cleanup):
                    rows = sql(select, args).fetchall()

                    if not rows:
                        break

                    count += len(rows)
                    sql(delete % ','.join(str(row[0]) for row in rows))

                    for row in rows:
                        args[arg_index] = row[row_index]
                        cleanup(row[-1])

        except Timeout:
            raise Timeout(count)

        return count


    def iterkeys(self, reverse=False):
        """Iterate Cache keys in database sort order.

        >>> cache = Cache('/tmp/diskcache')
        >>> _ = cache.clear()
        >>> for key in [4, 1, 3, 0, 2]:
        ...     cache[key] = key
        >>> list(cache.iterkeys())
        [0, 1, 2, 3, 4]
        >>> list(cache.iterkeys(reverse=True))
        [4, 3, 2, 1, 0]

        :param bool reverse: reverse sort order (default False)
        :return: iterator of Cache keys

        """
        sql = self._sql
        limit = 100
        _disk_get = self._disk.get

        if reverse:
            select = (
                'SELECT key, raw FROM Cache'
                ' ORDER BY key DESC, raw DESC LIMIT 1'
            )
            iterate = (
                'SELECT key, raw FROM Cache'
                ' WHERE key = ? AND raw < ? OR key < ?'
                ' ORDER BY key DESC, raw DESC LIMIT ?'
            )
        else:
            select = (
                'SELECT key, raw FROM Cache'
                ' ORDER BY key ASC, raw ASC LIMIT 1'
            )
            iterate = (
                'SELECT key, raw FROM Cache'
                ' WHERE key = ? AND raw > ? OR key > ?'
                ' ORDER BY key ASC, raw ASC LIMIT ?'
            )

        row = sql(select).fetchall()

        if row:
            (key, raw), = row
        else:
            return

        yield _disk_get(key, raw)

        while True:
            rows = sql(iterate, (key, raw, key, limit)).fetchall()

            if not rows:
                break

            for key, raw in rows:
                yield _disk_get(key, raw)


    def _iter(self, ascending=True):
        sql = self._sql
        rows = sql('SELECT MAX(rowid) FROM Cache').fetchall()
        (max_rowid,), = rows
        yield  # Signal ready.

        if max_rowid is None:
            return

        bound = max_rowid + 1
        limit = 100
        _disk_get = self._disk.get
        rowid = 0 if ascending else bound
        select = (
            'SELECT rowid, key, raw FROM Cache'
            ' WHERE ? < rowid AND rowid < ?'
            ' ORDER BY rowid %s LIMIT ?'
        ) % ('ASC' if ascending else 'DESC')

        while True:
            if ascending:
                args = (rowid, bound, limit)
            else:
                args = (0, rowid, limit)

            rows = sql(select, args).fetchall()

            if not rows:
                break

            for rowid, key, raw in rows:
                yield _disk_get(key, raw)


    def __iter__(self):
        "Iterate keys in cache including expired items."
        iterator = self._iter()
        next(iterator)
        return iterator


    def __reversed__(self):
        "Reverse iterate keys in cache including expired items."
        iterator = self._iter(ascending=False)
        next(iterator)
        return iterator


    def stats(self, enable=True, reset=False):
        """Return cache statistics hits and misses.

        :param bool enable: enable collecting statistics (default True)
        :param bool reset: reset hits and misses to 0 (default False)
        :return: (hits, misses)

        """
        # pylint: disable=E0203,W0201
        result = (self.reset('hits'), self.reset('misses'))

        if reset:
            self.reset('hits', 0)
            self.reset('misses', 0)

        self.reset('statistics', enable)

        return result


    def volume(self):
        """Return estimated total size of cache on disk.

        :return: size in bytes

        """
        (page_count,), = self._sql('PRAGMA page_count').fetchall()
        total_size = self._page_size * page_count + self.reset('size')
        return total_size


    def close(self):
        """Close database connection.

        """
        con = getattr(self._local, 'con', None)

        if con is None:
            return

        con.close()

        try:
            delattr(self._local, 'con')
        except AttributeError:
            pass


    def __enter__(self):
        return self


    def __exit__(self, *exception):
        self.close()


    def __len__(self):
        "Count of items in cache including expired items."
        return self.reset('count')


    def __getstate__(self):
        return (self.directory, self.timeout, type(self.disk))


    def __setstate__(self, state):
        self.__init__(*state)


    def reset(self, key, value=ENOVAL):
        """Reset `key` and `value` item from Settings table.

        If `value` is not given, it is reloaded from the Settings
        table. Otherwise, the Settings table is updated.

        Settings attributes on cache objects are lazy-loaded and
        read-only. Use `reset` to update the value.

        Settings with the ``disk_`` prefix correspond to Disk
        attributes. Updating the value will change the unprefixed attribute on
        the associated Disk instance.

        Settings with the ``sqlite_`` prefix correspond to SQLite
        pragmas. Updating the value will execute the corresponding PRAGMA
        statement.

        :param str key: Settings key for item
        :param value: value for item (optional)
        :return: updated value for item
        :raises Timeout: if database timeout expires

        """
        if value is ENOVAL:
            select = 'SELECT value FROM Settings WHERE key = ?'
            (value,), = self._sql(select, (key,)).fetchall()
            setattr(self, key, value)
            return value
        else:
            with self._transact() as (sql, _):
                update = 'UPDATE Settings SET value = ? WHERE key = ?'
                sql(update, (value, key))

            if key.startswith('sqlite_'):

                # 2016-02-17 GrantJ - PRAGMA and autocommit_level=None
                # don't always play nicely together. Retry setting the
                # PRAGMA. I think some PRAGMA statements expect to
                # immediately take an EXCLUSIVE lock on the database. I
                # can't find any documentation for this but without the
                # retry, stress will intermittently fail with multiple
                # processes.

                pause = 0.001
                count = 60000  # 60 / 0.001
                error = sqlite3.OperationalError
                pragma = key[7:]

                for _ in range(count):
                    try:
                        args = pragma, value
                        sql('PRAGMA %s = %s' % args).fetchall()
                    except sqlite3.OperationalError as exc:
                        error = exc
                        time.sleep(pause)
                    else:
                        break
                else:
                    raise error

                del error

            elif key.startswith('disk_'):
                attr = key[5:]
                setattr(self._disk, attr, value)

            setattr(self, key, value)
            return value
