from beaker.container import NamespaceManager
from beaker.synchronization import file_synchronizer


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

    @classmethod
    def _init_dependencies(cls):
        """Initialize module-level dependent libraries required
        by this :class:`.NamespaceManager`."""

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
        raise NotImplementedError()

    def acquire_read_lock(self):
        """Establish a read lock.

        This operation is called before a key is read.    By
        default the function does nothing.

        """

    def release_read_lock(self):
        """Release a read lock.

        This operation is called after a key is read.    By
        default the function does nothing.

        """

    def acquire_write_lock(self, wait=True, replace=False):
        """Establish a write lock.

        This operation is called before a key is written.
        A return value of ``True`` indicates the lock has
        been acquired.

        By default the function returns ``True`` unconditionally.

        'replace' is a hint indicating the full contents
        of the namespace may be safely discarded. Some backends
        may implement this (i.e. file backend won't unpickle the
        current contents).

        """
        return True

    def release_write_lock(self):
        """Release a write lock.

        This operation is called after a new value is written.
        By default this function does nothing.

        """

    def has_key(self, key):
        """Return ``True`` if the given key is present in this
        :class:`.Namespace`.
        """
        return self.__contains__(key)

    def __getitem__(self, key):
        raise NotImplementedError()

    def __setitem__(self, key, value):
        raise NotImplementedError()

    def set_value(self, key, value, expiretime=None):
        """Sets a value in this :class:`.NamespaceManager`.

        This is the same as ``__setitem__()``, but
        also allows an expiration time to be passed
        at the same time.

        """
        self[key] = value

    def __contains__(self, key):
        raise NotImplementedError()

    def __delitem__(self, key):
        raise NotImplementedError()

    def keys(self):
        """Return the list of all keys.

        This method may not be supported by all
        :class:`.NamespaceManager` implementations.

        """
        raise NotImplementedError()

    def remove(self):
        """Remove the entire contents of this
        :class:`.NamespaceManager`.

        e.g. for a file-based namespace, this would remove
        all the files.
        """
        self.do_remove()
