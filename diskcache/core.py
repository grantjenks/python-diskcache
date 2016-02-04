"Core disk and file-based cache API."

import errno
import functools as ft
import io
import os
import os.path as path
import sqlite3
import sys
import time
import uuid

try:
    import cPickle as pickle
except ImportError:
    import pickle

MIN_INT = -sys.maxsize - 1
MAX_INT = sys.maxsize

DEFAULT_SETTINGS = {
    u'statistics': 0, # False
    u'eviction_policy': u'least-recently-stored',
    u'size_limit': 2 ** 30, # 1gb
    u'cull_limit': 10,
    u'large_value_threshold': 2 ** 10, # 2kb, min 8
    u'sqlite_cache_size': 2 ** 25, # 32mb
    u'sqlite_mmap_size': 2 ** 27, # 128mb
}

DEFAULT_METADATA = {
    u'count': 0,
    u'size': 0,
    u'hits': 0,
    u'misses': 0,
}

EVICTION_POLICY = {
    'least-recently-stored': {
        'get': None,
        'set': (
            'SELECT rowid, version, filename FROM Cache'
            ' WHERE store_time IS NOT NULL'
            ' ORDER BY store_time LIMIT ?'
        ),
    },
    'least-recently-used': {
        'get': (
            'UPDATE Cache SET'
            ' access_time = ((julianday("now") - 2440587.5) * 86400.0)'
            ' WHERE rowid = ?'
        ),
        'set': (
            'SELECT rowid, version, filename FROM Cache'
            ' WHERE store_time IS NOT NULL'
            ' ORDER BY access_time LIMIT ?'
        ),
    },
    'least-frequently-used': {
        'get': (
            'UPDATE Cache SET'
            ' access_count = access_count + 1'
            ' WHERE rowid = ?'
        ),
        'set': (
            'SELECT rowid, version, filename FROM Cache'
            ' WHERE store_time IS NOT NULL'
            ' ORDER BY access_count LIMIT ?'
        ),
    },
}


class CachedAttr(object):
    "Data descriptor that caches get's and writes set's back to the database."
    # pylint: disable=too-few-public-methods
    def __init__(self, table, key):
        self._table = table
        self._key = key
        self._value = '_' + key

    def __get__(self, cache, cache_type):
        try:
            return getattr(cache, self._value)
        except AttributeError:
            self.__delete__(cache)
            return getattr(cache, self._value)

    def __set__(self, cache, value):
        "Cache attribute value and write back to database."
        # pylint: disable=protected-access,attribute-defined-outside-init
        query = 'UPDATE %s SET value = ? WHERE key = ?' % self._table
        cache._sql.execute(query, (value, self._key))
        setattr(cache, self._value, value)

    def __delete__(self, cache):
        "Update descriptor value from database."
        # pylint: disable=protected-access,attribute-defined-outside-init
        query = 'SELECT value FROM %s WHERE key = ?' % self._table
        value, = cache._sql.execute(query, (self._key,)).fetchone()
        setattr(cache, self._value, value)


class CacheMeta(type):
    "Metaclass for Cache to make Settings and Metadata into attributes."
    def __new__(mcs, name, bases, attrs):
        for key in DEFAULT_SETTINGS:
            attrs[key] = CachedAttr('Settings', key)

        for key in DEFAULT_METADATA:
            attrs[key] = CachedAttr('Metadata', key)

        return type.__new__(mcs, name, bases, attrs)


# Copied from bitbucket.org/gutworth/six/six.py Seems excessive to depend on
# `six` when only this snippet is needed. Metaclass syntax changed in Python 3.

def with_metaclass(meta, *bases):
    """Create a base class with a metaclass."""
    # This requires a bit of explanation: the basic idea is to make a dummy
    # metaclass for one level of class instantiation that replaces itself with
    # the actual metaclass.
    class metaclass(meta):
        def __new__(cls, name, this_bases, d):
            return meta(name, bases, d)
    return type.__new__(metaclass, 'temporary_class', (), {})


class Cache(with_metaclass(CacheMeta, object)):
    "Disk and file-based cache."
    # pylint: disable=bad-continuation
    def __init__(self, directory, **settings):
        self._dir = directory

        if not path.isdir(directory):
            try:
                os.makedirs(directory, 0o700)
            except OSError as error:
                if error.errno != errno.EEXIST:
                    raise EnvironmentError(
                        error.errno,
                        'Cache directory "%s" does not exist'
                        ' and could not be created' % self._dir
                    )

        _sql = self._sql = sqlite3.connect(
            path.join(directory, 'cache.sqlite3'),
            timeout=1.0,
            isolation_level=None,
        )
        sql = _sql.execute

        # As a cache, durability is not all-important. So modify SQLite
        # pragmas for a balance of speed and reliability.

        sql('PRAGMA synchronous = NORMAL')
        sql('PRAGMA journal_mode = WAL')

        # Setup Settings table.

        sql('CREATE TABLE IF NOT EXISTS Settings ('
            ' key TEXT NOT NULL UNIQUE,'
            ' value)'
        )

        current_settings = dict(sql(
            'SELECT key, value FROM Settings'
        ).fetchall())

        temp = DEFAULT_SETTINGS.copy()
        temp.update(current_settings)
        temp.update(settings)

        _sql.executemany(
            'INSERT OR REPLACE INTO Settings VALUES (?, ?)',
            temp.items(),
        )

        # Change cache_size as specified in Settings.

        self._page_size = sql('PRAGMA page_size').fetchone()[0]
        pages = (self.sqlite_cache_size / self._page_size)
        sql('PRAGMA cache_size = %d' % pages)

        # Change mmap_size as specified in Settings.

        sql('PRAGMA mmap_size = %d' % self.sqlite_mmap_size)

        # Setup Cache table.

        sql('CREATE TABLE IF NOT EXISTS Cache ('
            ' key BLOB UNIQUE,'
            ' version INTEGER DEFAULT 0,'
            ' store_time REAL,'
            ' expire_time REAL,'
            ' access_time REAL,'
            ' access_count INTEGER DEFAULT 0,'
            ' value_size INTEGER DEFAULT 0,'
            ' tag TEXT,'
            ' raw INTEGER,'
            ' filename TEXT,'
            ' value BLOB)'
        )

        sql('CREATE INDEX IF NOT EXISTS Cache_expire_time ON'
            ' Cache (expire_time)'
        )

        sql('CREATE INDEX IF NOT EXISTS Cache_store_time ON'
            ' Cache (store_time)'
        )

        sql('CREATE INDEX IF NOT EXISTS Cache_access_time ON'
            ' Cache (access_time)'
        )

        sql('CREATE INDEX IF NOT EXISTS Cache_access_count ON'
            ' Cache (access_count)'
        )

        sql('CREATE INDEX IF NOT EXISTS Cache_tag ON'
            ' Cache (tag)'
        )

        # Setup Metadata table.

        sql('CREATE TABLE IF NOT EXISTS Metadata ('
            ' key TEXT NOT NULL UNIQUE,'
            ' value INTEGER NOT NULL)'
        )

        current_metadata = dict(sql(
            'SELECT key, value from Metadata'
        ).fetchall())

        temp = DEFAULT_METADATA.copy()
        temp.update(current_metadata)

        _sql.executemany(
            'INSERT OR REPLACE INTO Metadata VALUES (?, ?)',
            temp.items(),
        )

        # Use triggers to keep Metadata updated.

        sql('CREATE TRIGGER IF NOT EXISTS Metadata_count_insert'
            ' AFTER INSERT ON Cache FOR EACH ROW BEGIN'
            ' UPDATE Metadata SET value = value + 1'
            ' WHERE key = "count"; END'
        )

        sql('CREATE TRIGGER IF NOT EXISTS Metadata_count_delete'
            ' AFTER DELETE ON Cache FOR EACH ROW BEGIN'
            ' UPDATE Metadata SET value = value - 1'
            ' WHERE key = "count"; END'
        )

        sql('CREATE TRIGGER IF NOT EXISTS Metadata_size_insert'
            ' AFTER INSERT ON Cache FOR EACH ROW BEGIN'
            ' UPDATE Metadata SET value = value + NEW.value_size'
            ' WHERE key = "size"; END'
        )

        sql('CREATE TRIGGER IF NOT EXISTS Metadata_size_update'
            ' AFTER UPDATE ON Cache FOR EACH ROW BEGIN'
            ' UPDATE Metadata'
            ' SET value = value + NEW.value_size - OLD.value_size'
            ' WHERE key = "size"; END'
        )

        sql('CREATE TRIGGER IF NOT EXISTS Metadata_size_delete'
            ' AFTER DELETE ON Cache FOR EACH ROW BEGIN'
            ' UPDATE Metadata SET value = value - OLD.value_size'
            ' WHERE key = "size"; END'
        )


    def __getitem__(self, key):
        sql = self._sql.execute
        cache_hit = 'UPDATE Metadata SET value = value + 1 WHERE key = "hits"'
        cache_miss = 'UPDATE Metadata SET value = value + 1 WHERE key = "misses"'

        db_key, _ = self._python_to_sqlite(key)

        row = sql(
            'SELECT rowid, version, store_time, expire_time,'
            ' raw, filename, value'
            ' FROM Cache WHERE key = ?',
            (db_key,),
        ).fetchone()

        if row is None:
            if self.statistics:
                sql(cache_miss)
            raise KeyError(key)

        rowid, version, store_time, expire_time, raw, filename, value = row

        if store_time is None:
            if self.statistics:
                sql(cache_miss)
            raise KeyError(key)

        now = time.time()

        if expire_time is not None and expire_time < now:
            self._delete(rowid, version, filename)

            if self.statistics:
                sql(cache_miss)

            raise KeyError(key)

        if filename is None:
            result = self._sqlite_to_python(value)
        else:
            full_path = path.join(self._dir, filename)

            try:
                with io.open(full_path, 'rb') as reader:
                    if raw:
                        result = reader.read()
                    else:
                        result = pickle.load(reader)
            except IOError as error:
                if error.errno == errno.ENOENT:
                    # Key was deleted before we could retrieve result.
                    if self.statistics:
                        sql(cache_miss)
                    raise KeyError(key)
                else:
                    raise

        if self.statistics:
            sql(cache_hit)

        query = EVICTION_POLICY[self.eviction_policy]['get']

        if query is not None:
            sql(query, (rowid,))

        return result


    def get(self, key, default=None):
        """Get key from cache. If key is missing, return default.

        Keyword arguments:
        default -- value to return if key is missing (default None)
        """
        try:
            return self[key]
        except KeyError:
            return default


    def set(self, key, value, raw=False, expire=None, tag=None):
        """Store key, value pair in cache.

        Keyword arguments:
        raw -- store value in file as raw bytes (default False)
        expire -- seconds until the key expires (default None)
        tag -- text to associate with key (default None)
        """
        sql = self._sql.execute

        db_key, _ = self._python_to_sqlite(key)

        # Lookup filename for existing key.

        row = sql(
            'SELECT version, filename FROM Cache WHERE key = ?',
            (db_key,)
        ).fetchone()

        if row:
            version, filename = row
        else:
            sql('INSERT OR IGNORE INTO Cache(key) VALUES (?)', (db_key,))
            version, filename = 0, None

        # Remove existing file if present.

        if filename is not None:
            self._remove(filename)

        # Store value in file if raw or large.

        if raw:
            filename, full_path = self._filename()

            with io.open(full_path, 'wb') as writer:
                reader = ft.partial(value.read, 2 ** 22)
                for chunk in iter(reader, b''):
                    writer.write(chunk)

            db_value = None
            value_size = path.getsize(full_path)
        else:
            db_value, value_size = self._python_to_sqlite(value)

            if value_size > self.large_value_threshold:
                filename, full_path = self._filename()
                with io.open(full_path, 'wb') as writer:
                    writer.write(db_value)
                db_value = None
            else:
                filename = None
                value_size = 0

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
            ' value_size = ?,'
            ' tag = ?,'
            ' raw = ?,'
            ' filename = ?,'
            ' value = ?'
            ' WHERE key = ? AND version = ?', (
                next_version,
                now,          # store_time
                expire_time,
                now,          # access_time
                0,            # access_count
                value_size,
                tag,
                raw,
                filename,
                db_value,
                db_key,
                version,
            ),
        )

        if cursor.rowcount == 0:
            # Another Cache wrote the value before us. Let them win.
            # Delete the file we created, if any.
            if filename is not None:
                self._remove(filename)
            return

        # Evict expired keys.

        cull_limit = self.cull_limit

        rows = sql(
            'SELECT rowid, version, filename FROM Cache'
            ' WHERE expire_time IS NOT NULL AND expire_time < ?'
            ' ORDER BY expire_time LIMIT ?',
            (now, cull_limit),
        ).fetchall()

        for rowid, version, filename in rows:
            deleted = self._delete(rowid, version, filename)
            if deleted:
                cull_limit -= 1

        if cull_limit == 0:
            return

        # Calculate total size.

        page_count = sql('PRAGMA page_count').fetchone()[0]
        del self.size # Update value from database.
        total_size = self._page_size * page_count + self.size

        if total_size < self.size_limit:
            return

        # Evict keys by policy.

        query = EVICTION_POLICY[self.eviction_policy]['set']

        if query is not None:
            rows = sql(query, (cull_limit,))

            for rowid, version, filename in rows:
                self._delete(rowid, version, filename)

    __setitem__ = set


    def _filename(self):
        hex_name = uuid.uuid4().hex
        sub_dir = path.join(hex_name[:2], hex_name[2:4])
        name = hex_name[4:] + '.val'
        directory = path.join(self._dir, sub_dir)

        try:
            os.makedirs(directory)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise

        filename = path.join(sub_dir, name)
        full_path = path.join(self._dir, filename)

        return filename, full_path


    def __delitem__(self, key):
        sql = self._sql.execute

        db_key, _ = self._python_to_sqlite(key)

        row = sql(
            'SELECT rowid, version, filename'
            ' FROM Cache WHERE key = ?',
            (db_key,),
        ).fetchone()

        if row is None:
            raise KeyError(key)
        else:
            self._delete(*row)


    def _delete(self, rowid, version, filename):
        cursor = self._sql.execute(
            'DELETE FROM Cache WHERE rowid = ? AND version = ?',
            (rowid, version),
        )

        deleted = cursor.rowcount == 1

        if deleted and filename:
            self._remove(filename)

        return deleted


    def _remove(self, filename):
        full_path = path.join(self._dir, filename)

        try:
            os.remove(full_path)
        except OSError as error:
            if error.errno != errno.ENOENT:
                # ENOENT may occur if two caches attempt to delete the same
                # file at the same time.
                raise


    def delete(self, key):
        "Delete key from cache. Missing keys are ignored."
        try:
            del self[key]
        except KeyError:
            pass


    def check(self):
        "Check database and file system consistency."
        # Delete rows with store_time = None
        # Delete files not referenced by database.
        # Call this clean or check?
        # Remove empty directories.
        # Run VACUUM
        pass


    def evict(self, tag):
        "Evict keys with matching tag."
        # Fetch a thousand rows at a time and delete the files.
        pass


    def clear(self):
        "Remove all items from Cache."
        # Fetch a thousand rows at a time and delete the files.
        # Remember to VACUUM.
        # Just rmdir, mkdir and re-init?
        #   - Then other connections are corrupted.
        pass


    def close(self):
        "Close database connection."
        self._sql.close()


    def stats(self, enable=True, reset=False):
        """Return cache statistics pair: hits, misses.

        Keyword arguments:
        enable - Enable collecting statistics (default True)
        reset - Reset hits and misses to 0 (default False)
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


    def path(self, key):
        """Return file path for corresponding value.

        When value is stored in database, return None. If key not found in
        Cache, raise KeyError.
        """
        sql = self._sql.execute
        db_key, _ = self._python_to_sqlite(key)

        row = sql(
            'SELECT store_time, filename'
            ' FROM Cache WHERE key = ?',
            (db_key,),
        ).fetchone()

        if not row:
            raise KeyError(key)

        store_time, filename = row

        if not store_time:
            raise KeyError(key)

        if filename:
            return path.join(self._dir, filename)
        else:
            return None


    def __len__(self):
        del self.count
        return self.count


    if sys.hexversion < 0x03000000:

        def _python_to_sqlite(self, value):
            """Convert any Python value to its SQLite-compatible counterpart.

            Return a pair (converted value, size estimate).
            """
            type_value = type(value)

            if ((type_value is int)
                    or (type_value is long and MIN_INT <= value <= MAX_INT)
                    or (type_value is float)):
                return value, 8
            elif type_value is unicode:
                size = len(value.encode('utf-8'))
                if size > self.large_value_threshold:
                    # Pickle large values to store outside the database.
                    result = pickle.dumps(value, protocol=2)
                    return buffer(result), len(result)
                else:
                    return value, size
            else:
                result = pickle.dumps(value, protocol=2)
                return buffer(result), len(result)


        def _sqlite_to_python(self, value):
            "Convert any SQLite value into its original Python counterpart."
            # pylint: disable=no-self-use
            type_value = type(value)

            if ((type_value is unicode)
                    or (type_value is int)
                    or (type_value is float)):
                return value
            else:
                return pickle.loads(str(value))

    else:

        def _python_to_sqlite(self, value):
            """Convert any Python value to its SQLite-compatible counterpart.

            Return a pair (converted value, size estimate).
            """
            type_value = type(value)

            if ((type_value is int and MIN_INT <= value <= MAX_INT)
                    or (type_value is float)):
                return value, 8
            elif type_value is str:
                size = len(value.encode('utf-8'))
                if size > self.large_value_threshold:
                    # Pickle large values to store outside the database.
                    result = pickle.dumps(value, protocol=2)
                    return result, len(result)
                else:
                    return value, size
            else:
                result = pickle.dumps(value, protocol=2)
                return result, len(result)


        def _sqlite_to_python(self, value):
            "Convert any SQLite value into its original Python counterpart."
            # pylint: disable=no-self-use
            type_value = type(value)

            if ((type_value is str)
                    or (type_value is int)
                    or (type_value is float)):
                return value
            else:
                return pickle.loads(bytes(value))
