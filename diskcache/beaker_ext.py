from beaker.container import NamespaceManager
from beaker.synchronization import file_synchronizer
from diskcache import Cache, Deque, DjangoCache, FanoutCache, Index


class DiskCacheManager(NamespaceManager):
    """Handles dictionary operations and locking for a namespace of
        values.

        :class:`.NamespaceManager` provides a dictionary-like interface,
        implementing ``__getitem__()``, ``__setitem__()``, and
        ``__contains__()``, as well as functions related to lock
        acquisition.

        The implementation for setting and retrieving the namespace data is
        handled by subclasses.

        NamespaceManager may be used alone, or may be accessed by
        one or more :class:`.Value` objects.  :class:`.Value` objects provide per-key
        services like expiration times and automatic recreation of values.

        Multiple NamespaceManagers created with a particular name will all
        share access to the same underlying datasource and will attempt to
        synchronize against a common mutex object.  The scope of this
        sharing may be within a single process or across multiple
        processes, depending on the type of NamespaceManager used.

        The NamespaceManager itself is generally threadsafe, except in the
        case of the DBMNamespaceManager in conjunction with the gdbm dbm
        implementation.

        """

    def __init__(self, namespace, diskcache_type=None, **dckwargs):
        """Creates a DiskCache namespace manager

        ``type``
            Type of DiskCache to implement. Currently only suppors
            diskcache.Core and diskcache.FanoutCache.
        ``dckwargs``
            Arguments to pass to the diskcache handlers.
        """
        NamespaceManager.__init__(self, namespace)

        self._is_new = False
        self.loaded = False
        self.cache = {
            'disk': Cache,
            'fanout': FanoutCache,
            'django': DjangoCache,
            'deque': Deque,
            'index': Index
        }[diskcache_type](**dckwargs)

    def get_creation_lock(self, key):
        return file_synchronizer(
            identifier="diskcache/funclock/%s/%s" % (
                self.namespace, key
            ),
            lock_dir=self.lock_dir)

    def do_remove(self):
        """Implement removal of the entire contents of this
        :class:`.NamespaceManager`.

        e.g. for a file-based namespace, this would remove
        all the files.

        The front-end to this method is the
        :meth:`.NamespaceManager.remove` method.

        """
        self.cache.clear()
        self.cache.close()

    def __getitem__(self, key):
        return self.cache.__getitem__(key)

    def __setitem__(self, key, value):
        return self.cache.set(key, value)

    def set_value(self, key, value, expiretime=None):
        """Sets a value in this :class:`.NamespaceManager`.

        This is the same as ``__setitem__()``, but
        also allows an expiration time to be passed
        at the same time.

        """
        return self.cache.set(key, value, expiretime)

    def __contains__(self, key):
        return self.cache.__contains__(key)

    def __delitem__(self, key):
        return self.cache.__delitem__(key)

    def keys(self):
        """Return the list of all keys.

        This method may not be supported by all
        :class:`.NamespaceManager` implementations.

        """
        return self.cache.keys()
