import dbm
import diskcache
import pickledb
import shelve
import sqlitedict
import timeit

value = 'value'

print('diskcache set')
dc = diskcache.FanoutCache('/tmp/diskcache')
%timeit -n 100 -r 7 dc['key'] = value
print('diskcache get')
%timeit -n 100 -r 7 dc['key']
print('diskcache set/delete')
%timeit -n 100 -r 7 dc['key'] = value; del dc['key']

print('dbm set')
d = dbm.open('/tmp/dbm', 'c')
%timeit -n 100 -r 7 d['key'] = value; d.sync()
print('dbm get')
%timeit -n 100 -r 7 d['key']
print('dbm set/delete')
%timeit -n 100 -r 7 d['key'] = value; del d['key']; d.sync()

print('shelve set')
s = shelve.open('/tmp/shelve')
%timeit -n 100 -r 7 s['key'] = value; s.sync()
print('shelve get')
%timeit -n 100 -r 7 s['key']
print('shelve set/delete')
%timeit -n 100 -r 7 s['key'] = value; del s['key']; s.sync()

print('sqlitedict set')
sd = sqlitedict.SqliteDict('/tmp/sqlitedict', autocommit=True)
%timeit -n 100 -r 7 sd['key'] = value
print('sqlitedict get')
%timeit -n 100 -r 7 sd['key']
print('sqlitedict set/delete')
%timeit -n 100 -r 7 sd['key'] = value; del sd['key']

print('pickledb set')
p = pickledb.load('/tmp/pickledb', True)
%timeit -n 100 -r 7 p['key'] = value
print('pickledb get')
%timeit -n 100 -r 7 p = pickledb.load('/tmp/pickledb', True); p['key']
print('pickledb set/delete')
%timeit -n 100 -r 7 p['key'] = value; del p['key']
