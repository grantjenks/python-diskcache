"Core disk and file backed cache API."

import codecs
import errno
import functools as ft
import io
import os
import os.path as op
import sqlite3
import sys
import threading
import time
import warnings

if sys.hexversion < 0x03000000:
    import cPickle as pickle
    TextType = unicode
    BytesType = str
    INT_TYPES = int, long
    range = xrange # pylint: disable=redefined-builtin,invalid-name
else:
    import pickle
    TextType = str
    BytesType = bytes
    INT_TYPES = int,

DBNAME = 'cache.db'
ENOVAL = object()

MODE_NONE = 0
MODE_RAW = 1
MODE_BINARY = 2
MODE_TEXT = 3
MODE_PICKLE = 4

LIMITS = {
    u'min_int': -sys.maxsize - 1,
    u'max_int': sys.maxsize,
    u'pragma_timeout': 60,
}

DEFAULT_SETTINGS = {
    u'statistics': 0, # False
    u'eviction_policy': u'least-recently-stored',
    u'size_limit': 2 ** 30, # 1gb
    u'cull_limit': 10,
    u'large_value_threshold': 2 ** 10, # 1kb, min 8
    u'sqlite_synchronous': u'NORMAL',
    u'sqlite_journal_mode': u'WAL',
    u'sqlite_cache_size': 2 ** 13, # 8,192 pages
    u'sqlite_mmap_size': 2 ** 26,  # 64mb
}

METADATA = {
    u'count': 0,
    u'size': 0,
    u'hits': 0,
    u'misses': 0,
}

EVICTION_POLICY = {
    'least-recently-stored': {
        'init': (
            'CREATE INDEX IF NOT EXISTS Cache_store_time ON'
            ' Cache (store_time)'
        ),
        'get': None,
        'set': (
            'SELECT rowid, version, filename FROM Cache'
            ' ORDER BY store_time LIMIT ?'
        ),
    },
    'least-recently-used': {
        'init': (
            'CREATE INDEX IF NOT EXISTS Cache_access_time ON'
            ' Cache (access_time)'
        ),
        'get': (
            'UPDATE Cache SET'
            ' access_time = ((julianday("now") - 2440587.5) * 86400.0)'
            ' WHERE rowid = ?'
        ),
        'set': (
            'SELECT rowid, version, filename FROM Cache'
            ' ORDER BY access_time LIMIT ?'
        ),
    },
    'least-frequently-used': {
        'init': (
            'CREATE INDEX IF NOT EXISTS Cache_access_count ON'
            ' Cache (access_count)'
        ),
        'get': (
            'UPDATE Cache SET'
            ' access_count = access_count + 1'
            ' WHERE rowid = ?'
        ),
        'set': (
            'SELECT rowid, version, filename FROM Cache'
            ' ORDER BY access_count LIMIT ?'
        ),
    },
}


class Disk(object):
    "Cache key and value serialization for SQLite database and files."
    def __init__(self, pickle_protocol=pickle.HIGHEST_PROTOCOL):
        """Initialize `Disk` instance.

        :param int pickle_protocol: ``pickle.HIGHEST_PROTOCOL``

        """
        self._protocol = pickle_protocol


    def put(self, key):
        """Convert key to fields (key, raw) for Cache table.

        :param key: key to convert
        :return: (database key, raw boolean) pair

        """
        # pylint: disable=bad-continuation,unidiomatic-typecheck
        type_key = type(key)

        if type_key is BytesType:
            return sqlite3.Binary(key), True
        elif ((type_key is TextType)
                or (type_key in INT_TYPES
                    and LIMITS[u'min_int'] <= key <= LIMITS[u'max_int'])
                or (type_key is float)):
            return key, True
        else:
            result = pickle.dumps(key, protocol=self._protocol)
            return sqlite3.Binary(result), False


    def get(self, key, raw):
        """Convert fields (key, raw) from Cache table to key.

        :param key: database key to convert
        :param bool raw: flag indicating raw database storage
        :return: corresponding Python key

        """
        # pylint: disable=no-self-use,unidiomatic-typecheck
        if raw:
            return BytesType(key) if type(key) is sqlite3.Binary else key
        else:
            return pickle.load(io.BytesIO(key))


    def store(self, value, read, threshold, prep_file):
        """Return fields (size, mode, filename, value) for Cache table.

        :param value: value to convert
        :param bool read: True when value is file-like object
        :param int threshold: size threshold for large values
        :param callable prep_file: initialize (filename, full_path) pair
        :return: (size, mode, filename, value) tuple for Cache table.

        """
        # pylint: disable=unidiomatic-typecheck
        type_value = type(value)

        if ((type_value is TextType and len(value) < threshold)
                or (type_value in INT_TYPES
                    and LIMITS[u'min_int'] <= value <= LIMITS[u'max_int'])
                or (type_value is float)):
            return 0, MODE_RAW, None, value
        elif type_value is BytesType:
            if len(value) < threshold:
                return len(value), MODE_RAW, None, sqlite3.Binary(value)
            else:
                filename, full_path = prep_file()

                with io.open(full_path, 'wb') as writer:
                    writer.write(value)

                return len(value), MODE_BINARY, filename, None
        elif type_value is TextType:
            filename, full_path = prep_file()

            with io.open(full_path, 'w', encoding='UTF-8') as writer:
                writer.write(value)

            size = op.getsize(full_path)

            return size, MODE_TEXT, filename, None
        elif read:
            size = 0
            reader = ft.partial(value.read, 2 ** 22)
            filename, full_path = prep_file()

            with io.open(full_path, 'wb') as writer:
                for chunk in iter(reader, b''):
                    size += len(chunk)
                    writer.write(chunk)

            return size, MODE_BINARY, filename, None
        else:
            result = pickle.dumps(value, protocol=self._protocol)

            if len(result) < threshold:
                return 0, MODE_PICKLE, None, sqlite3.Binary(result)
            else:
                filename, full_path = prep_file()

                with io.open(full_path, 'wb') as writer:
                    writer.write(result)

                return len(result), MODE_PICKLE, filename, None


    def fetch(self, directory, mode, filename, value, read):
        """Convert fields (mode, filename, value) from Cache table to value.

        :param str directory: cache directory
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
                return io.open(op.join(directory, filename), 'rb')
            else:
                with io.open(op.join(directory, filename), 'rb') as reader:
                    return reader.read()
        elif mode == MODE_TEXT:
            full_path = op.join(directory, filename)
            with io.open(full_path, 'r', encoding='UTF-8') as reader:
                return reader.read()
        elif mode == MODE_PICKLE:
            if value is None:
                with io.open(op.join(directory, filename), 'rb') as reader:
                    return pickle.load(reader)
            else:
                return pickle.load(io.BytesIO(value))


class CachedAttr(object):
    "Data descriptor that caches get's and writes set's back to the database."
    # pylint: disable=too-few-public-methods
    def __init__(self, key):
        self._key = key
        self._value = '_' + key
        self._pragma = key.startswith('sqlite_') and key[7:]

    def __get__(self, cache, cache_type):
        return getattr(cache, self._value)

    def __set__(self, cache, value):
        "Cache attribute value and write back to database."
        # pylint: disable=protected-access,attribute-defined-outside-init
        sql = cache._sql
        query = 'UPDATE Settings SET value = ? WHERE key = ?'

        sql(query, (value, self._key))

        if self._pragma:

            # 2016-02-17 GrantJ - PRAGMA and autocommit_level=None don't always
            # play nicely together. Retry setting the PRAGMA. I think some
            # PRAGMA statements expect to immediately take an EXCLUSIVE lock on
            # the database. I can't find any documentation for this but without
            # the retry, stress will intermittently fail with multiple
            # processes.

            pause = 0.001
            error = sqlite3.OperationalError

            for _ in range(int(LIMITS[u'pragma_timeout'] / pause)):
                try:
                    sql('PRAGMA %s = %s' % (self._pragma, value)).fetchall()
                except sqlite3.OperationalError as exc:
                    error = exc
                    time.sleep(pause)
                else:
                    break
            else:
                raise error

            del error

        setattr(cache, self._value, value)

    def __delete__(self, cache):
        "Update descriptor value from database."
        # pylint: disable=protected-access,attribute-defined-outside-init
        query = 'SELECT value FROM Settings WHERE key = ?'
        (value,), = cache._sql(query, (self._key,)).fetchall()
        setattr(cache, self._value, value)


class CacheMeta(type):
    "Metaclass for Cache to make Settings into attributes."
    def __new__(mcs, name, bases, attrs):
        for key in DEFAULT_SETTINGS:
            attrs[key] = CachedAttr(key)
        for key in METADATA:
            attrs[key] = CachedAttr(key)
        return type.__new__(mcs, name, bases, attrs)


# Copied from bitbucket.org/gutworth/six/six.py Seems excessive to depend on
# `six` when only this snippet is needed. Metaclass syntax changed in Python 3.

def with_metaclass(meta, *bases):
    """Create a base class with a metaclass."""
    # This requires a bit of explanation: the basic idea is to make a dummy
    # metaclass for one level of class instantiation that replaces itself with
    # the actual metaclass.
    class DummyMetaclass(meta):
        "Dummy metaclass for Python 2 and Python 3 compatibility."
        # pylint: disable=too-few-public-methods
        def __new__(cls, name, _, attrs):
            return meta(name, bases, attrs)
    return type.__new__(DummyMetaclass, 'temporary_class', (), {})


class UnknownFileWarning(UserWarning):
    "Warning used by Cache.check for unknown files."
    pass


class EmptyDirWarning(UserWarning):
    "Warning used by Cache.check for empty directories."
    pass


class Cache(with_metaclass(CacheMeta, object)):
    "Disk and file backed cache."
    # pylint: disable=bad-continuation
    def __init__(self, directory, timeout=60, disk=Disk(), **settings):
        """Initialize Cache instance.

        :param str directory: cache directory
        :param float timeout: SQLite connection timeout
        :param disk: `Disk` instance for serialization
        :param settings: any of `DEFAULT_SETTINGS`

        """
        self._dir = directory
        self._timeout = 60    # Use 1 minute timeout for initialization.
        self._disk = disk
        self._local = threading.local()

        if not op.isdir(directory):
            try:
                os.makedirs(directory, 0o700)
            except OSError as error:
                if error.errno != errno.EEXIST:
                    raise EnvironmentError(
                        error.errno,
                        'Cache directory "%s" does not exist'
                        ' and could not be created' % self._dir
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

        # Set cached attributes: updates settings and sets pragmas.

        for key, value in sets.items():
            query = 'INSERT OR REPLACE INTO Settings VALUES (?, ?)'
            sql(query, (key, value))
            setattr(self, key, value)

        for key, value in METADATA.items():
            query = 'INSERT OR IGNORE INTO Settings VALUES (?, ?)'
            sql(query, (key, value))
            delattr(self, key)

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

        # Close and re-open database connection with given timeout.

        self.close()
        self._timeout = timeout
        assert self._sql


    @property
    def _sql(self):
        con = getattr(self._local, 'con', None)

        if con is None:
            con = self._local.con = sqlite3.connect(
                op.join(self._dir, DBNAME),
                timeout=self._timeout,
                isolation_level=None,
            )

        return con.execute


    def set(self, key, value, expire=None, read=False, tag=None):
        """Store key, value pair in cache.

        When `read` is `True`, `value` should be a file-like object opened
        for reading in binary mode.

        :param key: Python key to store
        :param value: Python value to store
        :param expire: seconds until the key expires (default None, no expiry)
        :param bool read: read value as raw bytes from file (default False)
        :param tag: text to associate with key (default None)
        :return: True if item was successfully committed

        """
        sql = self._sql

        db_key, raw = self._disk.put(key)

        # Lookup filename for existing key.

        rows = sql(
            'SELECT version, filename FROM Cache WHERE key = ? AND raw = ?',
            (db_key, raw),
        ).fetchall()

        if rows:
            (version, filename), = rows
        else:
            sql('INSERT OR IGNORE INTO Cache(key, raw) VALUES (?, ?)',
                (db_key, raw)
            )
            version, filename = 0, None

        # Remove existing file if present.

        if filename is not None:
            self._remove(filename)

        # Prepare value for disk storage.

        size, mode, filename, db_value = self._disk.store(
            value, read, self.large_value_threshold, self._prep_file
        )

        next_version = version + 1
        now = time.time()
        expire_time = None if expire is None else now + expire

        # Update the row. Two step process so that all files remain tracked.

        cursor = sql(
            'UPDATE Cache SET'
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
            ' WHERE key = ? AND raw = ? AND version = ?', (
                next_version,
                now,          # store_time
                expire_time,
                now,          # access_time
                0,            # access_count
                tag,
                size,
                mode,
                filename,
                db_value,
                db_key,
                raw,
                version,
            ),
        )

        if cursor.rowcount == 0:
            # Another Cache wrote the value before us so abort.
            if filename is not None:
                self._remove(filename)
            return False

        # Evict expired keys.

        cull_limit = self.cull_limit

        if cull_limit == 0:
            return True

        rows = sql(
            'SELECT rowid, version, filename FROM Cache'
            ' WHERE expire_time IS NOT NULL AND expire_time < ?'
            ' ORDER BY expire_time LIMIT ?',
            (now, cull_limit),
        ).fetchall()

        for rowid, version, filename in rows:
            deleted = self._delete(rowid, version, filename)
            cull_limit -= deleted

        if cull_limit == 0:
            return True

        if self.volume() < self.size_limit:
            return True

        # Evict keys by policy.

        query = EVICTION_POLICY[self.eviction_policy]['set']

        if query is not None:
            rows = sql(query, (cull_limit,))

            for rowid, version, filename in rows:
                self._delete(rowid, version, filename)

        return True

    __setitem__ = set


    def get(self, key, default=None, read=False, expire_time=False, tag=False):
        """Get key from cache. If key is missing, return default.

        :param key: Python key to retrieve
        :param default: value to return if key is missing (default None)
        :param bool read: if True, return file handle to value
            (default False)
        :param float expire_time: if True, return expire_time in tuple
            (default False)
        :param tag: if True, return tag in tuple (default False)
        :return: key or `default` if not found

        """
        sql = self._sql
        cache_hit = 'UPDATE Settings SET value = value + 1 WHERE key = "hits"'
        cache_miss = (
            'UPDATE Settings SET value = value + 1'
            ' WHERE key = "misses"'
        )

        if expire_time and tag:
            default = (default, None, None)
        elif expire_time or tag:
            default = (default, None)

        db_key, raw = self._disk.put(key)

        rows = sql(
            'SELECT rowid, store_time, expire_time, tag,'
            ' mode, filename, value'
            ' FROM Cache WHERE key = ? AND raw = ?',
            (db_key, raw),
        ).fetchall()

        if not rows:
            if self.statistics:
                sql(cache_miss)
            return default

        (rowid, store_time, db_expire_time, db_tag,
            mode, filename, db_value), = rows

        if store_time is None:
            if self.statistics:
                sql(cache_miss)
            return default

        now = time.time()

        if db_expire_time is not None and db_expire_time < now:
            if self.statistics:
                sql(cache_miss)
            return default

        try:
            value = self._disk.fetch(self._dir, mode, filename, db_value, read)
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

        query = EVICTION_POLICY[self.eviction_policy]['get']

        if query is not None:
            sql(query, (rowid,))

        if expire_time and tag:
            return (value, db_expire_time, db_tag)
        elif expire_time:
            return (value, db_expire_time)
        elif tag:
            return (value, db_tag)
        else:
            return value


    def __getitem__(self, key):
        "Return corresponding value for `key` from Cache."
        value = self.get(key, default=ENOVAL)
        if value is ENOVAL:
            raise KeyError(key)
        return value


    def __contains__(self, key):
        "Return True if `key` in Cache."
        sql = self._sql

        db_key, raw = self._disk.put(key)

        rows = sql(
            'SELECT store_time, expire_time FROM Cache'
            ' WHERE key = ? AND raw = ?',
            (db_key, raw),
        ).fetchall()

        if not rows:
            return False

        (store_time, expire_time), = rows

        if store_time is None:
            return False

        return expire_time is None or time.time() < expire_time


    def __delitem__(self, key):
        "Delete corresponding item for `key` from Cache."
        sql = self._sql

        db_key, raw = self._disk.put(key)

        rows = sql(
            'SELECT rowid, version, filename'
            ' FROM Cache WHERE key = ? AND raw = ?',
            (db_key, raw),
        ).fetchall()

        if rows:
            (rowid, version, filename), = rows
            return self._delete(rowid, version, filename)
        else:
            raise KeyError(key)


    def delete(self, key):
        """Delete corresponding item for `key` from Cache.

        Missing keys are ignored.

        """
        try:
            return self.__delitem__(key)
        except KeyError:
            return False


    def _delete(self, rowid, version, filename):
        cursor = self._sql(
            'DELETE FROM Cache WHERE rowid = ? AND version = ?',
            (rowid, version),
        )

        deleted = cursor.rowcount == 1

        if deleted and filename is not None:
            self._remove(filename)

        return deleted


    def _prep_file(self):
        hex_name = codecs.encode(os.urandom(16), 'hex').decode('utf-8')
        sub_dir = op.join(hex_name[:2], hex_name[2:4])
        name = hex_name[4:] + '.val'
        directory = op.join(self._dir, sub_dir)

        try:
            os.makedirs(directory)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise

        filename = op.join(sub_dir, name)
        full_path = op.join(self._dir, filename)

        return filename, full_path


    def _remove(self, filename):
        full_path = op.join(self._dir, filename)

        try:
            os.remove(full_path)
        except OSError as error:
            if error.errno != errno.ENOENT:
                # ENOENT may occur if two caches attempt to delete the same
                # file at the same time.
                raise


    def check(self, fix=False):
        """Check database and file system consistency.

        :param bool fix: fix inconsistencies
        :return: list of warnings

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

            # Check Settings.count against count of Cache rows.

            del self.count
            self_count = self.count
            (count,), = sql('SELECT COUNT(key) FROM Cache').fetchall()

            if self_count != count:
                message = 'Settings.count != COUNT(Cache.key); %d != %d'
                warnings.warn(message % (self_count, count))

                if fix:
                    self.count = count

            # Report uncommitted rows.

            rows = sql(
                'SELECT rowid, key, raw, version, filename FROM Cache'
                ' WHERE store_time IS NULL'
            ).fetchall()

            for rowid, key, raw, version, filename in rows:
                warnings.warn('row %d partially commited with key %r' % (
                    rowid, self._disk.get(key, raw)
                ))
                if fix:
                    self._delete(rowid, version, filename)

            # Check Cache.filename against file system.

            filenames = set()
            chunk = self.cull_limit
            rowid = 0
            total_size = 0

            while True:
                rows = sql(
                    'SELECT rowid, version, filename FROM Cache'
                    ' WHERE rowid > ? AND filename IS NOT NULL'
                    ' ORDER BY rowid LIMIT ?',
                    (rowid, chunk),
                ).fetchall()

                if not rows:
                    break

                for rowid, version, filename in rows:
                    full_path = op.join(self._dir, filename)
                    filenames.add(full_path)

                    if op.exists(full_path):
                        total_size += op.getsize(full_path)
                        continue

                    warnings.warn('file not found: %s' % full_path)

                    if fix:
                        self._delete(rowid, version, filename)

            del self.size
            self_size = self.size
            (size,), = sql(
                'SELECT COALESCE(SUM(size), 0) FROM Cache'
            ).fetchall()

            if self_size != size:
                message = 'Settings.size != SUM(Cache.size); %d != %d'
                warnings.warn(message % (self_size, size))

                if fix:
                    self.size = size

            # Check file system against Cache.filename.

            for dirpath, _, files in os.walk(self._dir):
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

            for dirpath, dirs, files in os.walk(self._dir):
                if not (dirs or files):
                    message = 'empty directory: %s' % dirpath
                    warnings.warn(message, EmptyDirWarning)

                    if fix:
                        os.rmdir(dirpath)

            return warns


    def expire(self):
        "Remove expired items from Cache."

        now = time.time()
        sql = self._sql
        chunk = self.cull_limit
        expire_time = 0
        count = 0

        while True:
            rows = sql(
                'SELECT rowid, version, expire_time, filename FROM Cache'
                ' WHERE ? < expire_time AND expire_time < ?'
                ' ORDER BY expire_time LIMIT ?',
                (expire_time, now, chunk),
            ).fetchall()

            if not rows:
                break

            for rowid, version, expire_time, filename in rows:
                count += self._delete(rowid, version, filename)

        return count


    def evict(self, tag):
        "Remove items with matching `tag` from Cache."

        sql = self._sql
        chunk = self.cull_limit
        rowid = 0
        count = 0

        sql('CREATE INDEX IF NOT EXISTS Cache_tag_rowid ON'
            ' Cache(tag, rowid)'
        )

        while True:
            rows = sql(
                'SELECT rowid, version, filename FROM Cache'
                ' WHERE tag = ? AND rowid > ? ORDER BY rowid LIMIT ?',
                (tag, rowid, chunk),
            ).fetchall()

            if not rows:
                break

            for rowid, version, filename in rows:
                count += self._delete(rowid, version, filename)

        return count


    def clear(self):
        "Remove all items from Cache."

        sql = self._sql
        chunk = self.cull_limit
        rowid = 0
        count = 0

        while True:
            rows = sql(
                'SELECT rowid, version, filename FROM Cache'
                ' WHERE rowid > ? ORDER BY rowid LIMIT ?',
                (rowid, chunk),
            ).fetchall()

            if not rows:
                break

            for rowid, version, filename in rows:
                count += self._delete(rowid, version, filename)

        return count


    def stats(self, enable=True, reset=False):
        """Return cache statistics pair: (hits, misses).

        :param bool enable: enable collecting statistics (default True)
        :param bool reset: reset hits and misses to 0 (default False)
        :return: (hits, misses)

        """
        # pylint: disable=E0203,W0201
        del self.hits
        del self.misses

        result = (self.hits, self.misses)

        if reset:
            self.hits = 0
            self.misses = 0

        self.statistics = enable

        return result


    def volume(self):
        """Return estimated total size of cache on disk.

        :return: size in bytes

        """
        (page_count,), = self._sql('PRAGMA page_count').fetchall()
        del self.size # Update value from database.
        total_size = self._page_size * page_count + self.size
        return total_size


    def close(self):
        "Close database connection."
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
        del self.count
        return self.count
