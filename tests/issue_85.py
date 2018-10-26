"""Test Script for Issue #85

$ export PYTHONPATH=`pwd`
$ python tests/issue_85.py

"""

print('REMOVING CACHE DIRECTORY')
import shutil
shutil.rmtree('.cache', ignore_errors=True)

print('INITIALIZING DJANGO')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')

import django
django.setup()

print('RUNNING MULTI-THREADING INIT TEST')
from django.core.cache import cache
def run():
    cache.get('key')

import threading
threads = [threading.Thread(target=run) for _ in range(50)]
_ = [thread.start() for thread in threads]
_ = [thread.join() for thread in threads]

print('SQLITE COMPILE OPTIONS')
c = cache._cache._shards[0]
options = c._sql('pragma compile_options').fetchall()
print('\n'.join(val for val, in options))

print('CREATING DATA TABLE')
c._con.execute('create table data (x)')
nums = [(num,) for num in range(1000)]
c._con.executemany('insert into data values (?)', nums)
c._timeout = 60

commands = {
    'read/write': [
        'SELECT MAX(x) FROM data',
        'UPDATE data SET x = x + 1',
    ],
    'write/read': [
        'UPDATE data SET x = x + 1',
        'SELECT MAX(x) FROM data',
    ],
    'begin/read/write': [
        'BEGIN',
        'SELECT MAX(x) FROM data',
        'UPDATE data SET x = x + 1',
        'COMMIT',
    ],
    'begin/write/read': [
        'BEGIN',
        'UPDATE data SET x = x + 1',
        'SELECT MAX(x) FROM data',
        'COMMIT',
    ],
    'begin immediate/read/write': [
        'BEGIN IMMEDIATE',
        'SELECT MAX(x) FROM data',
        'UPDATE data SET x = x + 1',
        'COMMIT',
    ],
    'begin immediate/write/read': [
        'BEGIN IMMEDIATE',
        'UPDATE data SET x = x + 1',
        'SELECT MAX(x) FROM data',
        'COMMIT',
    ],
    'begin exclusive/read/write': [
        'BEGIN EXCLUSIVE',
        'SELECT MAX(x) FROM data',
        'UPDATE data SET x = x + 1',
        'COMMIT',
    ],
    'begin exclusive/write/read': [
        'BEGIN EXCLUSIVE',
        'UPDATE data SET x = x + 1',
        'SELECT MAX(x) FROM data',
        'COMMIT',
    ],
}

import collections
errors = collections.deque()

import sqlite3

def run():
    try:
        for statement in statements:
            c._sql(statement)
    except sqlite3.OperationalError:
        errors.append(True)

for key, statements in commands.items():
    print(f'RUNNING {key}')
    errors.clear()
    threads = [threading.Thread(target=run) for _ in range(100)]
    _ = [thread.start() for thread in threads]
    _ = [thread.join() for thread in threads]
    print('Error count:', len(errors))
