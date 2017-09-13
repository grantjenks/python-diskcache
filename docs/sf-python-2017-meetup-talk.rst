SF Python 2017 Meetup Talk
==========================

* Can we have some fun together in this talk?
* Can I show you some code that I would not run in production?
* Story: Fun of Reinvention by David Beazley at PyCon Israel this year.
  * Encourages us to scratch our itch under the code phrase:
    "It's just a prototype." Not a bad place to start. Often how it ends :)


Landscape
---------


Backends
--------


Frameworks
----------


I can haz mor memory?
---------------------

* Redis is great technology: free, open source, fast.
  * But another process to manage and more memory required.

$ emacs talk/settings.py
$ emacs talk/urls.py
$ emacs talk/views.py

$ gunicorn --reload talk.wsgi

$ emacs benchmark.py

$ python benchmark.py

* I dislike benchmarks in general so don't copy this code. I kind of stole it
  from Beazley in another great talk he did on concurrency in Python. He said
  it was kind of lousy code but it's just so simple.

$ python manage.py shell

>>> import time
>>> from django.conf import settings
>>> from django.core.cache import caches
>>> for key in settings.CACHES.keys():
...     caches[key].clear()
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


Features
--------


Use Case: Static file serving with read()
-----------------------------------------


Use Case: Analytics with incr()/pop()
-------------------------------------


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

* Cache is a single shard. FanoutCache uses multiple shards. Trick is cross-platform hash.
* Pickle can actually be fast if you use a higher protocol. Default 0. Up to 4 now.
  * Don't choose higher than 2 if you want to be portable between Python 2 and 3.
* Size limit really indicates when to start culling. Limit number of items deleted.


SQLite
------

* Tradeoff cache latency and miss-rate using timeout.
* SQLite supports 64-bit integers and floats, UTF-8 text and binary blobs.
* Use a context manager for isolation level management.
  * Transactions are amazing though.
* Pragmas tune the behavior and performance of SQLite.

  * Default is very robust and slow.
  * Use write-ahead-log so writers don't block readers.
  * Memory-map pages for fast lookups.


Best way to make money in photography? Sell all your gear.
----------------------------------------------------------

- Story: Who saw eclipse? Awesome, right?
  - Hard to really photograph the experience.
  - This is me, staring up at the sun, blinding myself as I hold my glasses
    and my phone to take a photo. Clearly lousy.
- Software talks are hard to get right and I can't cover everything related
  to caching in 20 minutes. I hope you've learned something tonight or at
  least seen something interesting.


Conclusion
----------

- Windows support mostly "just worked"
  - SQLite is truly cross-platform
  - Filesystems are a little different
  - AppVeyor was about half as fast as Travis
  - check() to fix inconsistencies
- Caveats
  - Not well suited to queues (want read:write at 10:1 or higher)
  - NFS and SQLite do not play nice
- Alternative databases: BerkeleyDB, LMDB, RocksDB, LevelDB, etc.
- Engage with me on Github, find bugs, complain about performance.
- If you like the project, star-it on Github and share it with friends.
- Thanks for letting me share tonight. Questions?
