DiskCache Cache Benchmarks
==========================

Accurately measuring performance is a difficult task. The benchmarks on this
page are synthetic in the sense that they were designed to stress getting,
setting, and deleting items repeatedly. Measurements in production systems are
much harder to reproduce reliably. So take the following data with a `grain of
salt`_. A stated feature of :doc:`DiskCache <index>` is performance so we would
be remiss not to produce this page with comparisons.

The source for all benchmarks can be found under the "tests" directory in the
source code repository. Measurements are reported by percentile: median, 90th
percentile, 99th percentile, and maximum along with total time and miss
rate. The average is not reported as its less useful in response-time
scenarios. Each process in the benchmark executes 100,000 operations with ten
times as many sets as deletes and ten times as many gets as sets.

Each comparison includes `Memcached`_ and `Redis`_ with default client and
server settings. Note that these backends work differently as they communicate
over the localhost network. The also require a server process running and
maintained. All keys and values are short byte strings to reduce the network
impact.

.. _`grain of salt`: https://en.wikipedia.org/wiki/Grain_of_salt
.. _`Memcached`: http://memcached.org/
.. _`Redis`: http://redis.io/

Single Access
-------------

The single access workload starts one worker processes which performs all
operations. No concurrent cache access occurs.

Get
...

.. image:: _static/core-p1-get.png

Above displays cache access latency at three percentiles. Notice the
performance of :doc:`DiskCache <index>` is faster than highly optimized
memory-backed server solutions.

Set
...

.. image:: _static/core-p1-set.png

Above displays cache store latency at three percentiles. The cost of writing to
disk is higher but still sub-millisecond. All data in :doc:`DiskCache <index>`
is persistent.

Delete
......

.. image:: _static/core-p1-delete.png

Above displays cache delete latency at three percentiles. As above, deletes
require disk writes but latency is still sub-millisecond.

Timing Data
...........

Not all data is easily displayed in the graphs above. Miss rate, maximum
latency and total latency is recorded below.

========= ========= ========= ========= ========= ========= ========= =========
Timings for diskcache.Cache
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get     88966      9705  17.881us  28.849us  41.962us 472.069us   1.701s
      set      9021         0 300.884us 338.078us 394.106us 658.989us   2.736s
   delete      1012       104 261.068us 299.931us 338.078us 598.907us 248.081ms
    Total     98999                                                     4.686s
========= ========= ========= ========= ========= ========= ========= =========

The generated workload includes a ~1% cache miss rate. All items were stored
with no expiry. The miss rate is due entirely to gets after deletes.

========= ========= ========= ========= ========= ========= ========= =========
Timings for diskcache.FanoutCache(shards=4, timeout=1.0)
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get     88966      9705  15.974us  28.133us  41.962us 522.852us   1.605s
      set      9021         0 281.096us 318.050us 388.145us   5.438ms   2.537s
   delete      1012       104 237.942us 283.003us 345.945us   2.058ms 231.609ms
    Total     98999                                                     4.374s
========= ========= ========= ========= ========= ========= ========= =========

The high maximum store latency is likely an artifact of disk/OS interactions.

========= ========= ========= ========= ========= ========= ========= =========
Timings for diskcache.FanoutCache(shards=8, timeout=0.025)
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get     88966      9705  15.974us  27.895us  41.008us 562.906us   1.570s
      set      9021         0 281.811us 316.858us 398.159us   1.189ms   2.526s
   delete      1012       104 240.803us 283.003us 321.150us 499.964us 229.842ms
    Total     98999                                                     4.326s
========= ========= ========= ========= ========= ========= ========= =========

Notice the low overhead of the :class:`FanoutCache
<diskcache.FanoutCache>`. Even without concurrent access, a slight benefit is
observable.

========= ========= ========= ========= ========= ========= ========= =========
Timings for pylibmc.Client
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get     88966      9705  25.988us  30.041us  41.962us 269.890us   2.407s
      set      9021         0  28.133us  31.948us  45.061us  88.930us 262.482ms
   delete      1012       104  25.988us  29.087us  39.101us  65.804us  27.031ms
    Total     98999                                                     2.697s
========= ========= ========= ========= ========= ========= ========= =========

Memcached performance is low latency and very stable.

========= ========= ========= ========= ========= ========= ========= =========
Timings for redis.StrictRedis
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get     88966      9705  45.061us  49.114us  77.009us 197.887us   4.171s
      set      9021         0  46.015us  50.068us  77.963us 179.052us 429.199ms
   delete      1012       104  44.823us  56.982us  77.009us 104.189us  47.746ms
    Total     98999                                                     4.648s
========= ========= ========= ========= ========= ========= ========= =========

Redis performance is roughly half that of Memcached. :doc:`DiskCache <index>`
performs better than Redis for get operations through the 99th percentile.

Concurrent Access
-----------------

The concurrent access workload starts eight worker processes each with
different and interleaved operations. None of these benchmarks saturated all
the processors.

Get
...

.. image:: _static/core-p8-get.png

Under heavy load, :doc:`DiskCache <index>` gets are very low latency. At the
90th percentile, they are less than half the latency of Memcached.

Set
...

.. image:: _static/core-p8-set.png

Stores are much slower under load and benefit greatly from sharding. Not
displayed are latencies in excess of five milliseconds. With one shard
allocated per worker, latency is within a magnitude of memory-backed server
solutions.

Delete
......

.. image:: _static/core-p8-delete.png

Again deletes require writes to disk. Only the :class:`FanoutCache
<diskcache.FanoutCache>` performs well with one shard allocated per worker.

Timing Data
...........

Not all data is easily displayed in the graphs above. Miss rate, maximum
latency and total latency is recorded below.

========= ========= ========= ========= ========= ========= ========= =========
Timings for diskcache.Cache
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     72929  16.928us  29.802us  45.061us 517.130us  13.617s
      set     71530         0 303.030us 360.966us  36.302ms   6.251s  269.090s
   delete      7916       773 265.837us 330.925us  35.141ms   1.339s   17.652s
    Total    791992                                                   300.358s
========= ========= ========= ========= ========= ========= ========= =========

Notice the unacceptably high maximum store and delete latency. Without
sharding, cache writers block each other. By default :class:`Cache
<diskcache.Cache>` objects raise a timeout error after sixty seconds.

========= ========= ========= ========= ========= ========= ========= =========
Timings for diskcache.FanoutCache(shards=4, timeout=1.0)
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     72975  17.166us  34.094us  73.195us   8.381ms  15.575s
      set     71530         0 228.882us   1.421ms  19.039ms 333.486ms  79.159s
   delete      7916       784 198.126us   1.385ms  19.165ms 107.130ms   8.838s
    Total    791992                                                   103.572s
========= ========= ========= ========= ========= ========= ========= =========

Here :class:`FanoutCache <diskcache.FanoutCache>` uses four shards to
distribute writes. That reduces the maximum latency by a factor of ten. Note
the miss rate is variable due to the interleaved operations of concurrent
workers.

========= ========= ========= ========= ========= ========= ========= =========
Timings for diskcache.FanoutCache(shards=8, timeout=0.025)
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     70780  23.127us  45.061us  86.069us   7.667ms  19.697s
      set     71530        31 257.015us   1.410ms   8.780ms  27.772ms  51.284s
   delete      7916       767 219.822us   1.366ms   8.804ms  26.998ms   5.474s
    Total    791992                                                    76.455s
========= ========= ========= ========= ========= ========= ========= =========

With one shard allocated per worker and a low timeout, the maximum latency is
more reasonable and corresponds to the specified 25 millisecond timeout. Some
set and delete operations were therefore canceled and recorded as cache
misses. The miss rate due to timeout is less than 0.05%.

========= ========= ========= ========= ========= ========= ========= =========
Timings for pylibmc.Client
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     72146  83.208us 105.143us 120.878us 520.945us  61.320s
      set     71530         0  85.115us 107.050us 123.024us 458.002us   6.285s
   delete      7916       792  82.016us 103.951us 119.925us 298.977us 673.505ms
    Total    791992                                                    68.279s
========= ========= ========= ========= ========= ========= ========= =========

Memcached performance is low latency and stable even under heavy load. Notice
that cache gets are half as fast in total as compared with :class:`FanoutCache
<diskcache.FanoutCache>`. The superior performance of get operations put the
overall performance of :doc:`DiskCache <index>` within ten percent of
Memcached.

========= ========= ========= ========= ========= ========= ========= =========
Timings for redis.StrictRedis
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     72652 141.144us 174.999us 210.047us 931.978us 103.515s
      set     71530         0 142.097us 174.999us 211.000us 623.941us  10.457s
   delete      7916       811 139.952us 172.138us 205.994us 288.963us   1.138s
    Total    791992                                                   115.110s
========= ========= ========= ========= ========= ========= ========= =========

Redis performance is roughly half that of Memcached. Beware the impact of
persistence settings on your Redis performance. Depending on your use of
logging and snapshotting, maximum latency may increase significantly.
