"""Test Script for Issue #85

$ export PYTHONPATH=`pwd`
$ python tests/issue_85.py

"""

import collections
import os
import random
import shutil
import sqlite3
import threading
import time

import django


def remove_cache_dir():
    print('REMOVING CACHE DIRECTORY')
    shutil.rmtree('.cache', ignore_errors=True)


def init_django():
    global shard
    print('INITIALIZING DJANGO')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
    django.setup()
    from django.core.cache import cache

    shard = cache._cache._shards[0]


def multi_threading_init_test():
    print('RUNNING MULTI-THREADING INIT TEST')
    from django.core.cache import cache

    def run():
        cache.get('key')

    threads = [threading.Thread(target=run) for _ in range(50)]
    _ = [thread.start() for thread in threads]
    _ = [thread.join() for thread in threads]


def show_sqlite_compile_options():
    print('SQLITE COMPILE OPTIONS')
    options = shard._sql('pragma compile_options').fetchall()
    print('\n'.join(val for val, in options))


def create_data_table():
    print('CREATING DATA TABLE')
    shard._con.execute('create table data (x)')
    nums = [(num,) for num in range(1000)]
    shard._con.executemany('insert into data values (?)', nums)


commands = {
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


values = collections.deque()


def run(statements):
    ident = threading.get_ident()
    try:
        for index, statement in enumerate(statements):
            if index == (len(statements) - 1):
                values.append(('COMMIT', ident))
            time.sleep(random.random() / 10.0)
            shard._sql(statement)
            if index == 0:
                values.append(('BEGIN', ident))
    except sqlite3.OperationalError:
        values.append(('ERROR', ident))


def test_transaction_errors():
    for key, statements in commands.items():
        print(f'RUNNING {key}')
        values.clear()
        threads = []
        for _ in range(100):
            thread = threading.Thread(target=run, args=(statements,))
            threads.append(thread)
        _ = [thread.start() for thread in threads]
        _ = [thread.join() for thread in threads]
        errors = [pair for pair in values if pair[0] == 'ERROR']
        begins = [pair for pair in values if pair[0] == 'BEGIN']
        commits = [pair for pair in values if pair[0] == 'COMMIT']
        print('Error count:', len(errors))
        print('Begin count:', len(begins))
        print('Commit count:', len(commits))
        begin_idents = [ident for _, ident in begins]
        commit_idents = [ident for _, ident in commits]
        print('Serialized:', begin_idents == commit_idents)


if __name__ == '__main__':
    remove_cache_dir()
    init_django()
    multi_threading_init_test()
    show_sqlite_compile_options()
    create_data_table()
    test_transaction_errors()
