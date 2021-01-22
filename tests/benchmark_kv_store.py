"""Benchmarking Key-Value Stores

$ python -m IPython tests/benchmark_kv_store.py

"""

from IPython import get_ipython

import diskcache

ipython = get_ipython()
assert ipython is not None, 'No IPython! Run with $ ipython ...'

value = 'value'

print('diskcache set')
dc = diskcache.FanoutCache('/tmp/diskcache')
ipython.magic("timeit -n 100 -r 7 dc['key'] = value")
print('diskcache get')
ipython.magic("timeit -n 100 -r 7 dc['key']")
print('diskcache set/delete')
ipython.magic("timeit -n 100 -r 7 dc['key'] = value; del dc['key']")

try:
    import dbm.gnu  # Only trust GNU DBM
except ImportError:
    print('Error: Cannot import dbm.gnu')
    print('Error: Skipping import shelve')
else:
    print('dbm set')
    d = dbm.gnu.open('/tmp/dbm', 'c')
    ipython.magic("timeit -n 100 -r 7 d['key'] = value; d.sync()")
    print('dbm get')
    ipython.magic("timeit -n 100 -r 7 d['key']")
    print('dbm set/delete')
    ipython.magic(
        "timeit -n 100 -r 7 d['key'] = value; d.sync(); del d['key']; d.sync()"
    )

    import shelve

    print('shelve set')
    s = shelve.open('/tmp/shelve')
    ipython.magic("timeit -n 100 -r 7 s['key'] = value; s.sync()")
    print('shelve get')
    ipython.magic("timeit -n 100 -r 7 s['key']")
    print('shelve set/delete')
    ipython.magic(
        "timeit -n 100 -r 7 s['key'] = value; s.sync(); del s['key']; s.sync()"
    )

try:
    import sqlitedict
except ImportError:
    print('Error: Cannot import sqlitedict')
else:
    print('sqlitedict set')
    sd = sqlitedict.SqliteDict('/tmp/sqlitedict', autocommit=True)
    ipython.magic("timeit -n 100 -r 7 sd['key'] = value")
    print('sqlitedict get')
    ipython.magic("timeit -n 100 -r 7 sd['key']")
    print('sqlitedict set/delete')
    ipython.magic("timeit -n 100 -r 7 sd['key'] = value; del sd['key']")

try:
    import pickledb
except ImportError:
    print('Error: Cannot import pickledb')
else:
    print('pickledb set')
    p = pickledb.load('/tmp/pickledb', True)
    ipython.magic("timeit -n 100 -r 7 p['key'] = value")
    print('pickledb get')
    ipython.magic(
        "timeit -n 100 -r 7 p = pickledb.load('/tmp/pickledb', True); p['key']"
    )
    print('pickledb set/delete')
    ipython.magic("timeit -n 100 -r 7 p['key'] = value; del p['key']")
