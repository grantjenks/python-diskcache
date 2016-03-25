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
        self._cache = FanoutCache(
            directory, shards=shards, timeout=timeout, **options
        )


    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None,
            read=False, tag=None):
        """Set a value in the cache if the key does not already exist. If timeout is
        given, that timeout will be used for the key; otherwise the default
        cache timeout will be used.

        Return True if the value was stored, False otherwise.

        """
        # pylint: disable=arguments-differ
        if self.has_key(key, version):
            return False
        return self.set(
            key, value, timeout=timeout, version=version, read=read, tag=tag
        )


    def get(self, key, default=None, version=None, read=False,
            expire_time=False, tag=False):
        """Fetch a given key from the cache. If the key does not exist, return
        default, which itself defaults to None.

        """
        # pylint: disable=arguments-differ
        key = self.make_key(key, version=version)
        return self._cache.get(
            key, default=default, read=read, expire_time=expire_time, tag=tag
        )


    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None,
            read=False, tag=None):
        """Set a value in the cache. If timeout is given, that timeout will be used
        for the key; otherwise the default cache timeout will be used.

        """
        # pylint: disable=arguments-differ
        key = self.make_key(key, version=version)
        timeout = self.get_backend_timeout(timeout=timeout)
        return self._cache.set(key, value, expire=timeout, read=read, tag=tag)


    def delete(self, key, version=None):
        "Delete a key from the cache, failing silently."
        key = self.make_key(key, version=version)
        self._cache.delete(key)


    def has_key(self, key, version=None):
        "Returns True if the key is in the cache and has not expired."
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

        :param float timeout: seconds to expire (default `DEFAULT_TIMEOUT`)

        """
        if timeout == DEFAULT_TIMEOUT:
            timeout = self.default_timeout
        elif timeout == 0:
            # ticket 21147 - avoid time.time() related precision issues
            timeout = -1
        return None if timeout is None else timeout
