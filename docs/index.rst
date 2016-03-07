DiskCache: Disk Backed Cache
============================

`DiskCache`_ is an Apache2 licensed disk and file backed cache library, written
in pure-Python, and compatible with Django.

The cloud-based computing of 2016 puts a premium on memory. Gigabytes of empty
space is left on disks as processes vie for memory. Among these processes is
Memcached (and sometimes Redis) which is used as a cache. Wouldn't it be nice
to leverage empty disk space for caching?

Django is Python's most popular web framework and ships with several caching
backends. Unfortunately the file-based cache in Django is essentially
broken. The culling method is random and large caches repeatedly scan a cache
directory which slows linearly with growth. Should it really take ~60ms to
store a key in a cache with a thousand items?

In Python, we can do better. And we can do it in pure-Python!

::

   In [1]: import pylibmc
   In [2]: client = pylibmc.Client(['127.0.0.1'], binary=True)
   In [3]: client[b'key'] = b'value'
   In [4]: %timeit client[b'key']

   10000 loops, best of 3: 25.4 µs per loop

   In [5]: import diskcache as dc
   In [6]: cache = dc.Cache('tmp')
   In [7]: cache[b'key'] = b'value'
   In [8]: %timeit cache[b'key']

   100000 loops, best of 3: 11.8 µs per loop

**Note:** Micro-benchmarks have their place but are not a substitute for real
measurements. DiskCache offers cache benchmarks to defend its performance
claims. Micro-optimizations are avoided but your mileage may vary.

DiskCache efficiently opens up gigabytes of storage space for caching. By
leveraging rock-solid database libraries and memory-mapped files, cache
performance can match and exceed industry standard solutions. There's no need
for a C compiler or running another process. Performance is a feature and
testing has 100% coverage with unit tests and hours of stress.

Testimonials
------------

Does your company or website use `DiskCache`_? Send us a message and let us
know.

Features
--------

- Pure-Python
- Fully Documented
- Benchmark comparisons (alternatives, Django cache backends)
- 100% test coverage
- Hours of stress testing
- Performance matters
- Django compatible API
- Thread-safe and process-safe
- Supports multiple eviction policies (LRU and LFU included)
- Keys support "tag" metadata and eviction
- Developed on Python 2.7
- Tested on CPython 2.7, 3.4, 3.5 and PyPy

Quickstart
----------

Installing DiskCache is simple with
`pip <http://www.pip-installer.org/>`_::

  $ pip install diskcache

You can access documentation in the interpreter with Python's built-in help
function::

  >>> from diskcache import Cache, FanoutCache, DjangoCache
  >>> help(Cache)
  >>> help(FanoutCache)
  >>> help(DjangoCache)

User Guide
----------

For those wanting more details, this part of the documentation describes
introduction, benchmarks, development, and API.

.. toctree::
   :maxdepth: 1

   tutorial
   cache-benchmarks
   djangocache-benchmarks
   api
   development

Reference and Indices
---------------------

* `DiskCache Documentation`_
* `DiskCache at PyPI`_
* `DiskCache at GitHub`_
* `DiskCache Issue Tracker`_
* :ref:`search`
* :ref:`genindex`

.. _`DiskCache Documentation`: http://www.grantjenks.com/docs/diskcache/
.. _`DiskCache at PyPI`: https://pypi.python.org/pypi/diskcache/
.. _`DiskCache at GitHub`: https://github.com/grantjenks/python-diskcache/
.. _`DiskCache Issue Tracker`: https://github.com/grantjenks/python-diskcache/issues/

Apache2 License
---------------

A large number of open source projects you find today are `GPL Licensed`_.
A project that is released as GPL cannot be used in any commercial product
without the product itself also being offered as open source.

The MIT, BSD, ISC, and Apache2 licenses are great alternatives to the GPL
that allow your open-source software to be used freely in proprietary,
closed-source software.

SortedContainers is released under terms of the `Apache2 License`_.

.. _`GPL Licensed`: http://www.opensource.org/licenses/gpl-license.php
.. _`Apache2 License`: http://opensource.org/licenses/Apache-2.0


DiskCache License
-----------------

.. include:: ../LICENSE

.. _`DiskCache`: http://www.grantjenks.com/docs/diskcache/
