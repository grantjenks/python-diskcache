"Django-compatible disk and file backed cache."

from django.core.cache.backends.base import BaseCache

try:
    from django.core.cache.backends.base import DEFAULT_TIMEOUT
except ImportError:
    # For older versions of Django simply use 300 seconds.
    DEFAULT_TIMEOUT = 300

from .fanout import FanoutCache


class DjangoCache(BaseCache):
    "Django-compatible disk and file backed cache."
    def __init__(self, directory, params):
        """Initialize DjangoCache instance.

        :param str directory: cache directory
        :param dict params: cache parameters

        """
        super(DjangoCache, self).__init__(params)
        shards = params.get('SHARDS', 8)
        timeout = params.get('DATABASE_TIMEOUT', 0.025)
        options = params.get('OPTIONS', {})
        self._cache = FanoutCache(directory, shards, timeout, **options)


    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None,
            read=False, tag=None, retry=True):
        """Set a value in the cache if the key does not already exist. If
        timeout is given, that timeout will be used for the key; otherwise the
        default cache timeout will be used.

        Return True if the value was stored, False otherwise.

        :param key: key for item
        :param value: value for item
        :param float timeout: seconds until the item expires
            (default 300 seconds)
        :param int version: key version number (default None, cache parameter)
        :param bool read: read value as bytes from file (default False)
        :param str tag: text to associate with key (default None)
        :param bool retry: retry if database timeout expires (default True)
        :return: True if item is added

        """
        # pylint: disable=arguments-differ
        key = self.make_key(key, version=version)
        timeout = self.get_backend_timeout(timeout=timeout)
        return self._cache.add(key, value, timeout, read, tag, retry)


    def get(self, key, default=None, version=None, read=False,
            expire_time=False, tag=False, retry=False):
        """Fetch a given key from the cache. If the key does not exist, return
        default, which itself defaults to None.

        :param key: key for item
        :param default: return value if key is missing (default None)
        :param int version: key version number (default None, cache parameter)
        :param bool read: if True, return file handle to value
            (default False)
        :param float expire_time: if True, return expire_time in tuple
            (default False)
        :param tag: if True, return tag in tuple (default False)
        :param bool retry: retry if database timeout expires (default False)
        :return: value for item if key is found else default

        """
        # pylint: disable=arguments-differ
        key = self.make_key(key, version=version)
        return self._cache.get(key, default, read, expire_time, tag, retry)


    def read(self, key, version=None):
        """Return file handle corresponding to `key` from Cache.

        :param key: Python key to retrieve
        :param int version: key version number (default None, cache parameter)
        :return: file open for reading in binary mode
        :raises KeyError: if key is not found

        """
        key = self.make_key(key, version=version)
        return self._cache.read(key)


    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None,
            read=False, tag=None, retry=True):
        """Set a value in the cache. If timeout is given, that timeout will be
        used for the key; otherwise the default cache timeout will be used.

        :param key: key for item
        :param value: value for item
        :param float timeout: seconds until the item expires
            (default 300 seconds)
        :param int version: key version number (default None, cache parameter)
        :param bool read: read value as bytes from file (default False)
        :param str tag: text to associate with key (default None)
        :param bool retry: retry if database timeout expires (default True)
        :return: True if item is added

        """
        # pylint: disable=arguments-differ
        key = self.make_key(key, version=version)
        timeout = self.get_backend_timeout(timeout=timeout)
        return self._cache.set(key, value, timeout, read, tag, retry)


    def delete(self, key, version=None, retry=True):
        """Delete a key from the cache, failing silently.

        :param key: key for item
        :param int version: key version number (default None, cache parameter)
        :param bool retry: retry if database timeout expires (default True)
        :return: True if item is deleted

        """
        # pylint: disable=arguments-differ
        key = self.make_key(key, version=version)
        self._cache.delete(key, retry)


    def has_key(self, key, version=None):
        """Returns True if the key is in the cache and has not expired.

        :param key: key for item
        :param int version: key version number (default None, cache parameter)
        :return: True if key is found

        """
        key = self.make_key(key, version=version)
        return key in self._cache


    def clear(self, **kwargs):
        "Remove *all* values from the cache at once."
        # pylint: disable=unused-argument
        self._cache.clear()


    def close(self, **kwargs):
        "Close the cache connection."
        # pylint: disable=unused-argument
        self._cache.close()


    def get_backend_timeout(self, timeout=DEFAULT_TIMEOUT):
        """Return seconds to expiration.

        :param float timeout: seconds until the item expires
            (default 300 seconds)

        """
        if timeout == DEFAULT_TIMEOUT:
            timeout = self.default_timeout
        elif timeout == 0:
            # ticket 21147 - avoid time.time() related precision issues
            timeout = -1
        return None if timeout is None else timeout
