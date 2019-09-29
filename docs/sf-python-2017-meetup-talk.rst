Talk: All Things Cached - SF Python 2017 Meetup
===============================================

* `Python All Things Cached Slides`_
* Can we have some fun together in this talk?
* Can I show you some code that I would not run in production?
* Great talk by David Beazley at PyCon Israel this year.

  * Encourages us to scratch our itch under the code phrase: "It's just a
    prototype." Not a bad place to start. Often how it ends :)


Landscape
---------

* At face value, caches seem simple: get/set/delete.
* But zoom in a little and you find just more and more detail.


Backends
--------

* Backends have different designs and tradeoffs.


Frameworks
----------

* Caches have broad applications.
* Web and scientific communities reach for them first.


I can haz mor memory?
---------------------

* Redis is great technology: free, open source, fast.
* But another process to manage and more memory required.

::

    $ emacs talk/settings.py
    $ emacs talk/urls.py
    $ emacs talk/views.py

::

    $ gunicorn --reload talk.wsgi

::

    $ emacs benchmark.py

::

    $ python benchmark.py

* I dislike benchmarks in general so don't copy this code. I kind of stole it
  from Beazley in another great talk he did on concurrency in Python. He said
  not to copy it so I'm telling you not to copy it.

::

    $ python manage.py shell

.. code-block:: pycon

    >>> import time
    >>> from django.conf import settings
    >>> from django.core.cache import caches

.. code-block:: pycon

    >>> for key in settings.CACHES.keys():
    ...     caches[key].clear()

::

    >>> while True:
    ...     !ls /tmp/filebased | wc -l
    ...     time.sleep(1)


Fool me once, strike one. Feel me twice? Strike three.
------------------------------------------------------

* Filebased cache has two severe drawbacks.

  1. Culling is random.
  2. set() uses glob.glob1() which slows linearly with directory size.


DiskCache
---------

* Wanted to solve Django-filebased cache problems.
* Felt like something was missing in the landscape.
* Found an unlikely hero in SQLite.


I'd rather drive a slow car fast than a fast car slow
-----------------------------------------------------

* Story: driving down the Grapevine in SoCal in friend's 1960s VW Bug.


Features
--------

* Lot's of features. Maybe a few too many. Ex: never used the tag metadata and
  eviction feature.


Use Case: Static file serving with read()
-----------------------------------------

* Some fun features. Data is stored in files and web servers are good at
  serving files.


Use Case: Analytics with incr()/pop()
-------------------------------------

* Tried to create really functional APIs.
* All write operations are atomic.


Case Study: Baby Web Crawler
----------------------------

* Convert from ephemeral, single-process to persistent, multi-process.


"get" Time vs Percentile
------------------------

* Tradeoff cache latency and miss-rate using timeout.


"set" Time vs Percentile
------------------------

* Django-filebased cache so slow, can't plot.


Design
------

* Cache is a single shard. FanoutCache uses multiple shards. Trick is
  cross-platform hash.
* Pickle can actually be fast if you use a higher protocol. Default 0. Up to 4
  now.

  * Don't choose higher than 2 if you want to be portable between Python 2
    and 3.

* Size limit really indicates when to start culling. Limit number of items
  deleted.


SQLite
------

* Tradeoff cache latency and miss-rate using timeout.
* SQLite supports 64-bit integers and floats, UTF-8 text and binary blobs.
* Use a context manager for isolation level management.
* Pragmas tune the behavior and performance of SQLite.

  * Default is robust and slow.
  * Use write-ahead-log so writers don't block readers.
  * Memory-map pages for fast lookups.


Best way to make money in photography? Sell all your gear.
----------------------------------------------------------

* Who saw eclipse? Awesome, right?

  * Hard to really photograph the experience.
  * This is me, staring up at the sun, blinding myself as I hold my glasses and
    my phone to take a photo. Clearly lousy.

* Software talks are hard to get right and I can't cover everything related to
  caching in 20 minutes. I hope you've learned something tonight or at least
  seen something interesting.


Conclusion
----------

* Windows support mostly "just worked".

  * SQLite is truly cross-platform.
  * Filesystems are a little different.
  * AppVeyor was about half as fast as Travis.
  * check() to fix inconsistencies.

* Caveats:

  * NFS and SQLite do not play nice.
  * Not well suited to queues (want read:write at 10:1 or higher).

* Alternative databases: BerkeleyDB, LMDB, RocksDB, LevelDB, etc.
* Engage with me on Github, find bugs, complain about performance.
* If you like the project, star-it on Github and share it with friends.
* Thanks for letting me share tonight. Questions?

.. _`Python All Things Cached Slides`: http://bit.ly/dc-2017-slides
