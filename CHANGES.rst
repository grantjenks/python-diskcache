Changes
=======

6.0.0 (NEXT)
-------------

**Breaking Changes**

* Pickle deserialization is now restricted to safe built-in types only.
  This mitigates CVE-2025-69872, which allowed arbitrary code execution
  when an attacker with write access to the cache directory injected a
  crafted pickle payload.

  The following types are permitted during deserialization:

  - Python builtins: ``int``, ``float``, ``str``, ``bytes``, ``bytearray``,
    ``list``, ``dict``, ``tuple``, ``set``, ``frozenset``, ``complex``,
    ``range``, ``slice``, ``object``, ``bool``, ``None``
  - ``collections``: ``OrderedDict``, ``defaultdict``, ``deque``
  - ``datetime``: ``date``, ``datetime``, ``time``, ``timedelta``,
    ``timezone``
  - ``decimal.Decimal``
  - ``fractions.Fraction``
  - ``uuid.UUID``

  All other types will raise ``UnpicklingError`` on read.

* There is no opt-out mechanism. Users who need to cache custom types have
  two migration paths:

  1. Use ``JSONDisk`` for JSON-serializable data::

       cache = Cache('/tmp/my-cache', disk=JSONDisk)

  2. Subclass ``Disk`` and override ``get()`` and ``fetch()`` with a custom
     serialization strategy appropriate for your data.

**New Features**

* Added ``SafeUnpickler`` class for restricted pickle deserialization.
* Added ``UnpicklingError`` exception raised when a disallowed type is
  encountered during deserialization.

**Internal**

* ``SAFE_PICKLE_CLASSES`` uses ``frozenset`` values to prevent runtime
  modification.

5.6.3 (2023-08-31)
-------------------

* Previous release (see git history for details).
