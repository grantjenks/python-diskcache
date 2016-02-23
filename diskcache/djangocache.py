"Django-compatible disk and file-based cache."

from django.core.cache.backends.base import DEFAULT_TIMEOUT, BaseCache

from .core import Cache


class DjangoCache(BaseCache):
    "Django-compatible disk and file-based cache."
    def __init__(self, directory, params):
        super(DjangoCache, self).__init__(params)
        self._cache = Cache(directory)

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        if self.has_key(key, version):
            return False
        self.set(key, value, timeout, version)
        return True

    def get(self, key, default=None, version=None):
        key = self.make_key(key, version=version)
        self.validate_key(key)
        return self._cache.get(key, default=default)

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        key = self.make_key(key, version=version)
        self.validate_key(key)
        timeout = self.get_backend_timeout(timeout=timeout)
        self._cache.set(key, value, expire=timeout)

    def delete(self, key, version=None):
        key = self.make_key(key, version=version)
        self.validate_key(key)
        self._cache.delete(key)

    def has_key(self, key, version=None):
        key = self.make_key(key, version=version)
        self.validate_key(key)
        return key in self._cache

    def clear(self):
        self._cache.clear()

    def close(self):
        self._cache.close()

    def get_backend_timeout(self, timeout=DEFAULT_TIMEOUT):
        "Return seconds to expiration."
        if timeout == DEFAULT_TIMEOUT:
            timeout = self.default_timeout
        elif timeout == 0:
            # ticket 21147 - avoid time.time() related precision issues
            timeout = -1
        return None if timeout is None else timeout
