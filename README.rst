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

* `DiskCache Tutorial`_
* `DiskCache Cache Benchmarks`_
* `DiskCache DjangoCache Benchmarks`_
* `DiskCache API Reference`_
* `DiskCache Development`_

.. _`DiskCache Tutorial`: http://www.grantjenks.com/docs/diskcache/tutorial.html
.. _`DiskCache Cache Benchmarks`: http://www.grantjenks.com/docs/diskcache/cache-benchmarks.html
.. _`DiskCache DjangoCache Benchmarks`: http://www.grantjenks.com/docs/diskcache/djangocache-benchmarks.html
.. _`DiskCache API Reference`: http://www.grantjenks.com/docs/diskcache/api.html
.. _`DiskCache Development`: http://www.grantjenks.com/docs/diskcache/development.html

Reference and Indices
---------------------

* `DiskCache Documentation`_
* `DiskCache at PyPI`_
* `DiskCache at GitHub`_
* `DiskCache Issue Tracker`_

.. _`DiskCache Documentation`: http://www.grantjenks.com/docs/diskcache/
.. _`DiskCache at PyPI`: https://pypi.python.org/pypi/diskcache/
.. _`DiskCache at GitHub`: https://github.com/grantjenks/python-diskcache/
.. _`DiskCache Issue Tracker`: https://github.com/grantjenks/python-diskcache/issues/

DiskCache License
-----------------

Copyright 2016 Grant Jenks

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

.. _`DiskCache`: http://www.grantjenks.com/docs/diskcache/
