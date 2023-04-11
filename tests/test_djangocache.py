# Most of this file was copied from:
# https://raw.githubusercontent.com/django/django/stable/3.2.x/tests/cache/tests.py

# Unit tests for cache framework
# Uses whatever cache backend is set in the test settings file.
import os
import pickle
import shutil
import tempfile
import time
from unittest import mock

from django.conf import settings
from django.core.cache import CacheKeyWarning, cache, caches
from django.http import HttpResponse
from django.middleware.cache import (
    FetchFromCacheMiddleware,
    UpdateCacheMiddleware,
)
from django.test import RequestFactory, TestCase, override_settings
from django.test.signals import setting_changed

################################################################################
# Setup Django for models import.
################################################################################

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')

import django

django.setup()

from .models import Poll, expensive_calculation


# functions/classes for complex data type tests
def f():
    return 42


class C:
    def m(n):
        return 24


class Unpicklable:
    def __getstate__(self):
        raise pickle.PickleError()


def empty_response(request):
    return HttpResponse()


KEY_ERRORS_WITH_MEMCACHED_MSG = (
    'Cache key contains characters that will cause errors if used with '
    'memcached: %r'
)


class UnpicklableType(object):
    # Unpicklable using the default pickling protocol on Python 2.
    __slots__ = ('a',)


def custom_key_func(key, key_prefix, version):
    """A customized cache key function"""
    return 'CUSTOM-' + '-'.join([key_prefix, str(version), key])


_caches_setting_base = {
    'default': {},
    'prefix': {'KEY_PREFIX': 'cacheprefix{}'.format(os.getpid())},
    'v2': {'VERSION': 2},
    'custom_key': {'KEY_FUNCTION': custom_key_func},
    'custom_key2': {'KEY_FUNCTION': 'tests.test_djangocache.custom_key_func'},
    'cull': {'OPTIONS': {'MAX_ENTRIES': 30}},
    'zero_cull': {'OPTIONS': {'CULL_FREQUENCY': 0, 'MAX_ENTRIES': 30}},
}


def caches_setting_for_tests(base=None, exclude=None, **params):
    # `base` is used to pull in the memcached config from the original settings,
    # `exclude` is a set of cache names denoting which `_caches_setting_base` keys
    # should be omitted.
    # `params` are test specific overrides and `_caches_settings_base` is the
    # base config for the tests.
    # This results in the following search order:
    # params -> _caches_setting_base -> base
    base = base or {}
    exclude = exclude or set()
    setting = {
        k: base.copy() for k in _caches_setting_base if k not in exclude
    }
    for key, cache_params in setting.items():
        cache_params.update(_caches_setting_base[key])
        cache_params.update(params)
    return setting


class BaseCacheTests:
    # A common set of tests to apply to all cache backends
    factory = RequestFactory()

    # RemovedInDjango41Warning: python-memcached doesn't support .get() with
    # default.
    supports_get_with_default = True

    # Some clients raise custom exceptions when .incr() or .decr() are called
    # with a non-integer value.
    incr_decr_type_error = TypeError

    def tearDown(self):
        cache.clear()

    def test_simple(self):
        # Simple cache set/get works
        cache.set('key', 'value')
        self.assertEqual(cache.get('key'), 'value')

    def test_default_used_when_none_is_set(self):
        """If None is cached, get() returns it instead of the default."""
        cache.set('key_default_none', None)
        self.assertIsNone(cache.get('key_default_none', default='default'))

    def test_add(self):
        # A key can be added to a cache
        self.assertIs(cache.add('addkey1', 'value'), True)
        self.assertIs(cache.add('addkey1', 'newvalue'), False)
        self.assertEqual(cache.get('addkey1'), 'value')

    def test_prefix(self):
        # Test for same cache key conflicts between shared backend
        cache.set('somekey', 'value')

        # should not be set in the prefixed cache
        self.assertIs(caches['prefix'].has_key('somekey'), False)

        caches['prefix'].set('somekey', 'value2')

        self.assertEqual(cache.get('somekey'), 'value')
        self.assertEqual(caches['prefix'].get('somekey'), 'value2')

    def test_non_existent(self):
        """Nonexistent cache keys return as None/default."""
        self.assertIsNone(cache.get('does_not_exist'))
        self.assertEqual(cache.get('does_not_exist', 'bang!'), 'bang!')

    def test_get_many(self):
        # Multiple cache keys can be returned using get_many
        cache.set_many({'a': 'a', 'b': 'b', 'c': 'c', 'd': 'd'})
        self.assertEqual(
            cache.get_many(['a', 'c', 'd']), {'a': 'a', 'c': 'c', 'd': 'd'}
        )
        self.assertEqual(cache.get_many(['a', 'b', 'e']), {'a': 'a', 'b': 'b'})
        self.assertEqual(
            cache.get_many(iter(['a', 'b', 'e'])), {'a': 'a', 'b': 'b'}
        )
        cache.set_many({'x': None, 'y': 1})
        self.assertEqual(cache.get_many(['x', 'y']), {'x': None, 'y': 1})

    def test_delete(self):
        # Cache keys can be deleted
        cache.set_many({'key1': 'spam', 'key2': 'eggs'})
        self.assertEqual(cache.get('key1'), 'spam')
        self.assertIs(cache.delete('key1'), True)
        self.assertIsNone(cache.get('key1'))
        self.assertEqual(cache.get('key2'), 'eggs')

    def test_delete_nonexistent(self):
        self.assertIs(cache.delete('nonexistent_key'), False)

    def test_has_key(self):
        # The cache can be inspected for cache keys
        cache.set('hello1', 'goodbye1')
        self.assertIs(cache.has_key('hello1'), True)
        self.assertIs(cache.has_key('goodbye1'), False)
        cache.set('no_expiry', 'here', None)
        self.assertIs(cache.has_key('no_expiry'), True)
        cache.set('null', None)
        self.assertIs(
            cache.has_key('null'),
            True if self.supports_get_with_default else False,
        )

    def test_in(self):
        # The in operator can be used to inspect cache contents
        cache.set('hello2', 'goodbye2')
        self.assertIn('hello2', cache)
        self.assertNotIn('goodbye2', cache)
        cache.set('null', None)
        if self.supports_get_with_default:
            self.assertIn('null', cache)
        else:
            self.assertNotIn('null', cache)

    def test_incr(self):
        # Cache values can be incremented
        cache.set('answer', 41)
        self.assertEqual(cache.incr('answer'), 42)
        self.assertEqual(cache.get('answer'), 42)
        self.assertEqual(cache.incr('answer', 10), 52)
        self.assertEqual(cache.get('answer'), 52)
        self.assertEqual(cache.incr('answer', -10), 42)
        with self.assertRaises(ValueError):
            cache.incr('does_not_exist')
        cache.set('null', None)
        with self.assertRaises(self.incr_decr_type_error):
            cache.incr('null')

    def test_decr(self):
        # Cache values can be decremented
        cache.set('answer', 43)
        self.assertEqual(cache.decr('answer'), 42)
        self.assertEqual(cache.get('answer'), 42)
        self.assertEqual(cache.decr('answer', 10), 32)
        self.assertEqual(cache.get('answer'), 32)
        self.assertEqual(cache.decr('answer', -10), 42)
        with self.assertRaises(ValueError):
            cache.decr('does_not_exist')
        cache.set('null', None)
        with self.assertRaises(self.incr_decr_type_error):
            cache.decr('null')

    def test_close(self):
        self.assertTrue(hasattr(cache, 'close'))
        cache.close()

    def test_data_types(self):
        # Many different data types can be cached
        stuff = {
            'string': 'this is a string',
            'int': 42,
            'list': [1, 2, 3, 4],
            'tuple': (1, 2, 3, 4),
            'dict': {'A': 1, 'B': 2},
            'function': f,
            'class': C,
        }
        cache.set('stuff', stuff)
        self.assertEqual(cache.get('stuff'), stuff)

    def test_cache_read_for_model_instance(self):
        # Don't want fields with callable as default to be called on cache read
        expensive_calculation.num_runs = 0
        Poll.objects.all().delete()
        my_poll = Poll.objects.create(question='Well?')
        self.assertEqual(Poll.objects.count(), 1)
        pub_date = my_poll.pub_date
        cache.set('question', my_poll)
        cached_poll = cache.get('question')
        self.assertEqual(cached_poll.pub_date, pub_date)
        # We only want the default expensive calculation run once
        self.assertEqual(expensive_calculation.num_runs, 1)

    def test_cache_write_for_model_instance_with_deferred(self):
        # Don't want fields with callable as default to be called on cache write
        expensive_calculation.num_runs = 0
        Poll.objects.all().delete()
        Poll.objects.create(question='What?')
        self.assertEqual(expensive_calculation.num_runs, 1)
        defer_qs = Poll.objects.all().defer('question')
        self.assertEqual(defer_qs.count(), 1)
        self.assertEqual(expensive_calculation.num_runs, 1)
        cache.set('deferred_queryset', defer_qs)
        # cache set should not re-evaluate default functions
        self.assertEqual(expensive_calculation.num_runs, 1)

    def test_cache_read_for_model_instance_with_deferred(self):
        # Don't want fields with callable as default to be called on cache read
        expensive_calculation.num_runs = 0
        Poll.objects.all().delete()
        Poll.objects.create(question='What?')
        self.assertEqual(expensive_calculation.num_runs, 1)
        defer_qs = Poll.objects.all().defer('question')
        self.assertEqual(defer_qs.count(), 1)
        cache.set('deferred_queryset', defer_qs)
        self.assertEqual(expensive_calculation.num_runs, 1)
        runs_before_cache_read = expensive_calculation.num_runs
        cache.get('deferred_queryset')
        # We only want the default expensive calculation run on creation and set
        self.assertEqual(
            expensive_calculation.num_runs, runs_before_cache_read
        )

    def test_expiration(self):
        # Cache values can be set to expire
        cache.set('expire1', 'very quickly', 1)
        cache.set('expire2', 'very quickly', 1)
        cache.set('expire3', 'very quickly', 1)

        time.sleep(2)
        self.assertIsNone(cache.get('expire1'))

        self.assertIs(cache.add('expire2', 'newvalue'), True)
        self.assertEqual(cache.get('expire2'), 'newvalue')
        self.assertIs(cache.has_key('expire3'), False)

    def test_touch(self):
        # cache.touch() updates the timeout.
        cache.set('expire1', 'very quickly', timeout=1)
        self.assertIs(cache.touch('expire1', timeout=4), True)
        time.sleep(2)
        self.assertIs(cache.has_key('expire1'), True)
        time.sleep(3)
        self.assertIs(cache.has_key('expire1'), False)
        # cache.touch() works without the timeout argument.
        cache.set('expire1', 'very quickly', timeout=1)
        self.assertIs(cache.touch('expire1'), True)
        time.sleep(2)
        self.assertIs(cache.has_key('expire1'), True)

        self.assertIs(cache.touch('nonexistent'), False)

    def test_unicode(self):
        # Unicode values can be cached
        stuff = {
            'ascii': 'ascii_value',
            'unicode_ascii': 'Iñtërnâtiônàlizætiøn1',
            'Iñtërnâtiônàlizætiøn': 'Iñtërnâtiônàlizætiøn2',
            'ascii2': {'x': 1},
        }
        # Test `set`
        for (key, value) in stuff.items():
            with self.subTest(key=key):
                cache.set(key, value)
                self.assertEqual(cache.get(key), value)

        # Test `add`
        for (key, value) in stuff.items():
            with self.subTest(key=key):
                self.assertIs(cache.delete(key), True)
                self.assertIs(cache.add(key, value), True)
                self.assertEqual(cache.get(key), value)

        # Test `set_many`
        for (key, value) in stuff.items():
            self.assertIs(cache.delete(key), True)
        cache.set_many(stuff)
        for (key, value) in stuff.items():
            with self.subTest(key=key):
                self.assertEqual(cache.get(key), value)

    def test_binary_string(self):
        # Binary strings should be cacheable
        from zlib import compress, decompress

        value = 'value_to_be_compressed'
        compressed_value = compress(value.encode())

        # Test set
        cache.set('binary1', compressed_value)
        compressed_result = cache.get('binary1')
        self.assertEqual(compressed_value, compressed_result)
        self.assertEqual(value, decompress(compressed_result).decode())

        # Test add
        self.assertIs(cache.add('binary1-add', compressed_value), True)
        compressed_result = cache.get('binary1-add')
        self.assertEqual(compressed_value, compressed_result)
        self.assertEqual(value, decompress(compressed_result).decode())

        # Test set_many
        cache.set_many({'binary1-set_many': compressed_value})
        compressed_result = cache.get('binary1-set_many')
        self.assertEqual(compressed_value, compressed_result)
        self.assertEqual(value, decompress(compressed_result).decode())

    def test_set_many(self):
        # Multiple keys can be set using set_many
        cache.set_many({'key1': 'spam', 'key2': 'eggs'})
        self.assertEqual(cache.get('key1'), 'spam')
        self.assertEqual(cache.get('key2'), 'eggs')

    def test_set_many_returns_empty_list_on_success(self):
        """set_many() returns an empty list when all keys are inserted."""
        failing_keys = cache.set_many({'key1': 'spam', 'key2': 'eggs'})
        self.assertEqual(failing_keys, [])

    def test_set_many_expiration(self):
        # set_many takes a second ``timeout`` parameter
        cache.set_many({'key1': 'spam', 'key2': 'eggs'}, 1)
        time.sleep(2)
        self.assertIsNone(cache.get('key1'))
        self.assertIsNone(cache.get('key2'))

    def test_delete_many(self):
        # Multiple keys can be deleted using delete_many
        cache.set_many({'key1': 'spam', 'key2': 'eggs', 'key3': 'ham'})
        cache.delete_many(['key1', 'key2'])
        self.assertIsNone(cache.get('key1'))
        self.assertIsNone(cache.get('key2'))
        self.assertEqual(cache.get('key3'), 'ham')

    def test_clear(self):
        # The cache can be emptied using clear
        cache.set_many({'key1': 'spam', 'key2': 'eggs'})
        cache.clear()
        self.assertIsNone(cache.get('key1'))
        self.assertIsNone(cache.get('key2'))

    def test_long_timeout(self):
        """
        Follow memcached's convention where a timeout greater than 30 days is
        treated as an absolute expiration timestamp instead of a relative
        offset (#12399).
        """
        cache.set('key1', 'eggs', 60 * 60 * 24 * 30 + 1)  # 30 days + 1 second
        self.assertEqual(cache.get('key1'), 'eggs')

        self.assertIs(cache.add('key2', 'ham', 60 * 60 * 24 * 30 + 1), True)
        self.assertEqual(cache.get('key2'), 'ham')

        cache.set_many(
            {'key3': 'sausage', 'key4': 'lobster bisque'},
            60 * 60 * 24 * 30 + 1,
        )
        self.assertEqual(cache.get('key3'), 'sausage')
        self.assertEqual(cache.get('key4'), 'lobster bisque')

    def test_forever_timeout(self):
        """
        Passing in None into timeout results in a value that is cached forever
        """
        cache.set('key1', 'eggs', None)
        self.assertEqual(cache.get('key1'), 'eggs')

        self.assertIs(cache.add('key2', 'ham', None), True)
        self.assertEqual(cache.get('key2'), 'ham')
        self.assertIs(cache.add('key1', 'new eggs', None), False)
        self.assertEqual(cache.get('key1'), 'eggs')

        cache.set_many({'key3': 'sausage', 'key4': 'lobster bisque'}, None)
        self.assertEqual(cache.get('key3'), 'sausage')
        self.assertEqual(cache.get('key4'), 'lobster bisque')

        cache.set('key5', 'belgian fries', timeout=1)
        self.assertIs(cache.touch('key5', timeout=None), True)
        time.sleep(2)
        self.assertEqual(cache.get('key5'), 'belgian fries')

    def test_zero_timeout(self):
        """
        Passing in zero into timeout results in a value that is not cached
        """
        cache.set('key1', 'eggs', 0)
        self.assertIsNone(cache.get('key1'))

        self.assertIs(cache.add('key2', 'ham', 0), True)
        self.assertIsNone(cache.get('key2'))

        cache.set_many({'key3': 'sausage', 'key4': 'lobster bisque'}, 0)
        self.assertIsNone(cache.get('key3'))
        self.assertIsNone(cache.get('key4'))

        cache.set('key5', 'belgian fries', timeout=5)
        self.assertIs(cache.touch('key5', timeout=0), True)
        self.assertIsNone(cache.get('key5'))

    def test_float_timeout(self):
        # Make sure a timeout given as a float doesn't crash anything.
        cache.set('key1', 'spam', 100.2)
        self.assertEqual(cache.get('key1'), 'spam')

    def _perform_cull_test(self, cull_cache_name, initial_count, final_count):
        try:
            cull_cache = caches[cull_cache_name]
        except InvalidCacheBackendError:
            self.skipTest("Culling isn't implemented.")

        # Create initial cache key entries. This will overflow the cache,
        # causing a cull.
        for i in range(1, initial_count):
            cull_cache.set('cull%d' % i, 'value', 1000)
        count = 0
        # Count how many keys are left in the cache.
        for i in range(1, initial_count):
            if cull_cache.has_key('cull%d' % i):
                count += 1
        self.assertEqual(count, final_count)

    def test_cull(self):
        self._perform_cull_test('cull', 50, 29)

    def test_zero_cull(self):
        self._perform_cull_test('zero_cull', 50, 19)

    def test_cull_delete_when_store_empty(self):
        try:
            cull_cache = caches['cull']
        except InvalidCacheBackendError:
            self.skipTest("Culling isn't implemented.")
        old_max_entries = cull_cache._max_entries
        # Force _cull to delete on first cached record.
        cull_cache._max_entries = -1
        try:
            cull_cache.set('force_cull_delete', 'value', 1000)
            self.assertIs(cull_cache.has_key('force_cull_delete'), True)
        finally:
            cull_cache._max_entries = old_max_entries

    def _perform_invalid_key_test(self, key, expected_warning):
        """
        All the builtin backends should warn (except memcached that should
        error) on keys that would be refused by memcached. This encourages
        portable caching code without making it too difficult to use production
        backends with more liberal key rules. Refs #6447.
        """
        # mimic custom ``make_key`` method being defined since the default will
        # never show the below warnings
        def func(key, *args):
            return key

        old_func = cache.key_func
        cache.key_func = func

        tests = [
            ('add', [key, 1]),
            ('get', [key]),
            ('set', [key, 1]),
            ('incr', [key]),
            ('decr', [key]),
            ('touch', [key]),
            ('delete', [key]),
            ('get_many', [[key, 'b']]),
            ('set_many', [{key: 1, 'b': 2}]),
            ('delete_many', [{key: 1, 'b': 2}]),
        ]
        try:
            for operation, args in tests:
                with self.subTest(operation=operation):
                    with self.assertWarns(CacheKeyWarning) as cm:
                        getattr(cache, operation)(*args)
                    self.assertEqual(str(cm.warning), expected_warning)
        finally:
            cache.key_func = old_func

    def test_invalid_key_characters(self):
        # memcached doesn't allow whitespace or control characters in keys.
        key = 'key with spaces and 清'
        self._perform_invalid_key_test(
            key, KEY_ERRORS_WITH_MEMCACHED_MSG % key
        )

    def test_invalid_key_length(self):
        # memcached limits key length to 250.
        key = ('a' * 250) + '清'
        expected_warning = (
            'Cache key will cause errors if used with memcached: '
            '%r (longer than %s)' % (key, 250)
        )
        self._perform_invalid_key_test(key, expected_warning)

    def test_cache_versioning_get_set(self):
        # set, using default version = 1
        cache.set('answer1', 42)
        self.assertEqual(cache.get('answer1'), 42)
        self.assertEqual(cache.get('answer1', version=1), 42)
        self.assertIsNone(cache.get('answer1', version=2))

        self.assertIsNone(caches['v2'].get('answer1'))
        self.assertEqual(caches['v2'].get('answer1', version=1), 42)
        self.assertIsNone(caches['v2'].get('answer1', version=2))

        # set, default version = 1, but manually override version = 2
        cache.set('answer2', 42, version=2)
        self.assertIsNone(cache.get('answer2'))
        self.assertIsNone(cache.get('answer2', version=1))
        self.assertEqual(cache.get('answer2', version=2), 42)

        self.assertEqual(caches['v2'].get('answer2'), 42)
        self.assertIsNone(caches['v2'].get('answer2', version=1))
        self.assertEqual(caches['v2'].get('answer2', version=2), 42)

        # v2 set, using default version = 2
        caches['v2'].set('answer3', 42)
        self.assertIsNone(cache.get('answer3'))
        self.assertIsNone(cache.get('answer3', version=1))
        self.assertEqual(cache.get('answer3', version=2), 42)

        self.assertEqual(caches['v2'].get('answer3'), 42)
        self.assertIsNone(caches['v2'].get('answer3', version=1))
        self.assertEqual(caches['v2'].get('answer3', version=2), 42)

        # v2 set, default version = 2, but manually override version = 1
        caches['v2'].set('answer4', 42, version=1)
        self.assertEqual(cache.get('answer4'), 42)
        self.assertEqual(cache.get('answer4', version=1), 42)
        self.assertIsNone(cache.get('answer4', version=2))

        self.assertIsNone(caches['v2'].get('answer4'))
        self.assertEqual(caches['v2'].get('answer4', version=1), 42)
        self.assertIsNone(caches['v2'].get('answer4', version=2))

    def test_cache_versioning_add(self):

        # add, default version = 1, but manually override version = 2
        self.assertIs(cache.add('answer1', 42, version=2), True)
        self.assertIsNone(cache.get('answer1', version=1))
        self.assertEqual(cache.get('answer1', version=2), 42)

        self.assertIs(cache.add('answer1', 37, version=2), False)
        self.assertIsNone(cache.get('answer1', version=1))
        self.assertEqual(cache.get('answer1', version=2), 42)

        self.assertIs(cache.add('answer1', 37, version=1), True)
        self.assertEqual(cache.get('answer1', version=1), 37)
        self.assertEqual(cache.get('answer1', version=2), 42)

        # v2 add, using default version = 2
        self.assertIs(caches['v2'].add('answer2', 42), True)
        self.assertIsNone(cache.get('answer2', version=1))
        self.assertEqual(cache.get('answer2', version=2), 42)

        self.assertIs(caches['v2'].add('answer2', 37), False)
        self.assertIsNone(cache.get('answer2', version=1))
        self.assertEqual(cache.get('answer2', version=2), 42)

        self.assertIs(caches['v2'].add('answer2', 37, version=1), True)
        self.assertEqual(cache.get('answer2', version=1), 37)
        self.assertEqual(cache.get('answer2', version=2), 42)

        # v2 add, default version = 2, but manually override version = 1
        self.assertIs(caches['v2'].add('answer3', 42, version=1), True)
        self.assertEqual(cache.get('answer3', version=1), 42)
        self.assertIsNone(cache.get('answer3', version=2))

        self.assertIs(caches['v2'].add('answer3', 37, version=1), False)
        self.assertEqual(cache.get('answer3', version=1), 42)
        self.assertIsNone(cache.get('answer3', version=2))

        self.assertIs(caches['v2'].add('answer3', 37), True)
        self.assertEqual(cache.get('answer3', version=1), 42)
        self.assertEqual(cache.get('answer3', version=2), 37)

    def test_cache_versioning_has_key(self):
        cache.set('answer1', 42)

        # has_key
        self.assertIs(cache.has_key('answer1'), True)
        self.assertIs(cache.has_key('answer1', version=1), True)
        self.assertIs(cache.has_key('answer1', version=2), False)

        self.assertIs(caches['v2'].has_key('answer1'), False)
        self.assertIs(caches['v2'].has_key('answer1', version=1), True)
        self.assertIs(caches['v2'].has_key('answer1', version=2), False)

    def test_cache_versioning_delete(self):
        cache.set('answer1', 37, version=1)
        cache.set('answer1', 42, version=2)
        self.assertIs(cache.delete('answer1'), True)
        self.assertIsNone(cache.get('answer1', version=1))
        self.assertEqual(cache.get('answer1', version=2), 42)

        cache.set('answer2', 37, version=1)
        cache.set('answer2', 42, version=2)
        self.assertIs(cache.delete('answer2', version=2), True)
        self.assertEqual(cache.get('answer2', version=1), 37)
        self.assertIsNone(cache.get('answer2', version=2))

        cache.set('answer3', 37, version=1)
        cache.set('answer3', 42, version=2)
        self.assertIs(caches['v2'].delete('answer3'), True)
        self.assertEqual(cache.get('answer3', version=1), 37)
        self.assertIsNone(cache.get('answer3', version=2))

        cache.set('answer4', 37, version=1)
        cache.set('answer4', 42, version=2)
        self.assertIs(caches['v2'].delete('answer4', version=1), True)
        self.assertIsNone(cache.get('answer4', version=1))
        self.assertEqual(cache.get('answer4', version=2), 42)

    def test_cache_versioning_incr_decr(self):
        cache.set('answer1', 37, version=1)
        cache.set('answer1', 42, version=2)
        self.assertEqual(cache.incr('answer1'), 38)
        self.assertEqual(cache.get('answer1', version=1), 38)
        self.assertEqual(cache.get('answer1', version=2), 42)
        self.assertEqual(cache.decr('answer1'), 37)
        self.assertEqual(cache.get('answer1', version=1), 37)
        self.assertEqual(cache.get('answer1', version=2), 42)

        cache.set('answer2', 37, version=1)
        cache.set('answer2', 42, version=2)
        self.assertEqual(cache.incr('answer2', version=2), 43)
        self.assertEqual(cache.get('answer2', version=1), 37)
        self.assertEqual(cache.get('answer2', version=2), 43)
        self.assertEqual(cache.decr('answer2', version=2), 42)
        self.assertEqual(cache.get('answer2', version=1), 37)
        self.assertEqual(cache.get('answer2', version=2), 42)

        cache.set('answer3', 37, version=1)
        cache.set('answer3', 42, version=2)
        self.assertEqual(caches['v2'].incr('answer3'), 43)
        self.assertEqual(cache.get('answer3', version=1), 37)
        self.assertEqual(cache.get('answer3', version=2), 43)
        self.assertEqual(caches['v2'].decr('answer3'), 42)
        self.assertEqual(cache.get('answer3', version=1), 37)
        self.assertEqual(cache.get('answer3', version=2), 42)

        cache.set('answer4', 37, version=1)
        cache.set('answer4', 42, version=2)
        self.assertEqual(caches['v2'].incr('answer4', version=1), 38)
        self.assertEqual(cache.get('answer4', version=1), 38)
        self.assertEqual(cache.get('answer4', version=2), 42)
        self.assertEqual(caches['v2'].decr('answer4', version=1), 37)
        self.assertEqual(cache.get('answer4', version=1), 37)
        self.assertEqual(cache.get('answer4', version=2), 42)

    def test_cache_versioning_get_set_many(self):
        # set, using default version = 1
        cache.set_many({'ford1': 37, 'arthur1': 42})
        self.assertEqual(
            cache.get_many(['ford1', 'arthur1']), {'ford1': 37, 'arthur1': 42}
        )
        self.assertEqual(
            cache.get_many(['ford1', 'arthur1'], version=1),
            {'ford1': 37, 'arthur1': 42},
        )
        self.assertEqual(cache.get_many(['ford1', 'arthur1'], version=2), {})

        self.assertEqual(caches['v2'].get_many(['ford1', 'arthur1']), {})
        self.assertEqual(
            caches['v2'].get_many(['ford1', 'arthur1'], version=1),
            {'ford1': 37, 'arthur1': 42},
        )
        self.assertEqual(
            caches['v2'].get_many(['ford1', 'arthur1'], version=2), {}
        )

        # set, default version = 1, but manually override version = 2
        cache.set_many({'ford2': 37, 'arthur2': 42}, version=2)
        self.assertEqual(cache.get_many(['ford2', 'arthur2']), {})
        self.assertEqual(cache.get_many(['ford2', 'arthur2'], version=1), {})
        self.assertEqual(
            cache.get_many(['ford2', 'arthur2'], version=2),
            {'ford2': 37, 'arthur2': 42},
        )

        self.assertEqual(
            caches['v2'].get_many(['ford2', 'arthur2']),
            {'ford2': 37, 'arthur2': 42},
        )
        self.assertEqual(
            caches['v2'].get_many(['ford2', 'arthur2'], version=1), {}
        )
        self.assertEqual(
            caches['v2'].get_many(['ford2', 'arthur2'], version=2),
            {'ford2': 37, 'arthur2': 42},
        )

        # v2 set, using default version = 2
        caches['v2'].set_many({'ford3': 37, 'arthur3': 42})
        self.assertEqual(cache.get_many(['ford3', 'arthur3']), {})
        self.assertEqual(cache.get_many(['ford3', 'arthur3'], version=1), {})
        self.assertEqual(
            cache.get_many(['ford3', 'arthur3'], version=2),
            {'ford3': 37, 'arthur3': 42},
        )

        self.assertEqual(
            caches['v2'].get_many(['ford3', 'arthur3']),
            {'ford3': 37, 'arthur3': 42},
        )
        self.assertEqual(
            caches['v2'].get_many(['ford3', 'arthur3'], version=1), {}
        )
        self.assertEqual(
            caches['v2'].get_many(['ford3', 'arthur3'], version=2),
            {'ford3': 37, 'arthur3': 42},
        )

        # v2 set, default version = 2, but manually override version = 1
        caches['v2'].set_many({'ford4': 37, 'arthur4': 42}, version=1)
        self.assertEqual(
            cache.get_many(['ford4', 'arthur4']), {'ford4': 37, 'arthur4': 42}
        )
        self.assertEqual(
            cache.get_many(['ford4', 'arthur4'], version=1),
            {'ford4': 37, 'arthur4': 42},
        )
        self.assertEqual(cache.get_many(['ford4', 'arthur4'], version=2), {})

        self.assertEqual(caches['v2'].get_many(['ford4', 'arthur4']), {})
        self.assertEqual(
            caches['v2'].get_many(['ford4', 'arthur4'], version=1),
            {'ford4': 37, 'arthur4': 42},
        )
        self.assertEqual(
            caches['v2'].get_many(['ford4', 'arthur4'], version=2), {}
        )

    def test_incr_version(self):
        cache.set('answer', 42, version=2)
        self.assertIsNone(cache.get('answer'))
        self.assertIsNone(cache.get('answer', version=1))
        self.assertEqual(cache.get('answer', version=2), 42)
        self.assertIsNone(cache.get('answer', version=3))

        self.assertEqual(cache.incr_version('answer', version=2), 3)
        self.assertIsNone(cache.get('answer'))
        self.assertIsNone(cache.get('answer', version=1))
        self.assertIsNone(cache.get('answer', version=2))
        self.assertEqual(cache.get('answer', version=3), 42)

        caches['v2'].set('answer2', 42)
        self.assertEqual(caches['v2'].get('answer2'), 42)
        self.assertIsNone(caches['v2'].get('answer2', version=1))
        self.assertEqual(caches['v2'].get('answer2', version=2), 42)
        self.assertIsNone(caches['v2'].get('answer2', version=3))

        self.assertEqual(caches['v2'].incr_version('answer2'), 3)
        self.assertIsNone(caches['v2'].get('answer2'))
        self.assertIsNone(caches['v2'].get('answer2', version=1))
        self.assertIsNone(caches['v2'].get('answer2', version=2))
        self.assertEqual(caches['v2'].get('answer2', version=3), 42)

        with self.assertRaises(ValueError):
            cache.incr_version('does_not_exist')

        cache.set('null', None)
        if self.supports_get_with_default:
            self.assertEqual(cache.incr_version('null'), 2)
        else:
            with self.assertRaises(self.incr_decr_type_error):
                cache.incr_version('null')

    def test_decr_version(self):
        cache.set('answer', 42, version=2)
        self.assertIsNone(cache.get('answer'))
        self.assertIsNone(cache.get('answer', version=1))
        self.assertEqual(cache.get('answer', version=2), 42)

        self.assertEqual(cache.decr_version('answer', version=2), 1)
        self.assertEqual(cache.get('answer'), 42)
        self.assertEqual(cache.get('answer', version=1), 42)
        self.assertIsNone(cache.get('answer', version=2))

        caches['v2'].set('answer2', 42)
        self.assertEqual(caches['v2'].get('answer2'), 42)
        self.assertIsNone(caches['v2'].get('answer2', version=1))
        self.assertEqual(caches['v2'].get('answer2', version=2), 42)

        self.assertEqual(caches['v2'].decr_version('answer2'), 1)
        self.assertIsNone(caches['v2'].get('answer2'))
        self.assertEqual(caches['v2'].get('answer2', version=1), 42)
        self.assertIsNone(caches['v2'].get('answer2', version=2))

        with self.assertRaises(ValueError):
            cache.decr_version('does_not_exist', version=2)

        cache.set('null', None, version=2)
        if self.supports_get_with_default:
            self.assertEqual(cache.decr_version('null', version=2), 1)
        else:
            with self.assertRaises(self.incr_decr_type_error):
                cache.decr_version('null', version=2)

    def test_custom_key_func(self):
        # Two caches with different key functions aren't visible to each other
        cache.set('answer1', 42)
        self.assertEqual(cache.get('answer1'), 42)
        self.assertIsNone(caches['custom_key'].get('answer1'))
        self.assertIsNone(caches['custom_key2'].get('answer1'))

        caches['custom_key'].set('answer2', 42)
        self.assertIsNone(cache.get('answer2'))
        self.assertEqual(caches['custom_key'].get('answer2'), 42)
        self.assertEqual(caches['custom_key2'].get('answer2'), 42)

    def test_cache_write_unpicklable_object(self):
        fetch_middleware = FetchFromCacheMiddleware(empty_response)

        request = self.factory.get('/cache/test')
        request._cache_update_cache = True
        get_cache_data = FetchFromCacheMiddleware(
            empty_response
        ).process_request(request)
        self.assertIsNone(get_cache_data)

        content = 'Testing cookie serialization.'

        def get_response(req):
            response = HttpResponse(content)
            response.set_cookie('foo', 'bar')
            return response

        update_middleware = UpdateCacheMiddleware(get_response)
        response = update_middleware(request)

        get_cache_data = fetch_middleware.process_request(request)
        self.assertIsNotNone(get_cache_data)
        self.assertEqual(get_cache_data.content, content.encode())
        self.assertEqual(get_cache_data.cookies, response.cookies)

        UpdateCacheMiddleware(lambda req: get_cache_data)(request)
        get_cache_data = fetch_middleware.process_request(request)
        self.assertIsNotNone(get_cache_data)
        self.assertEqual(get_cache_data.content, content.encode())
        self.assertEqual(get_cache_data.cookies, response.cookies)

    def test_add_fail_on_pickleerror(self):
        # Shouldn't fail silently if trying to cache an unpicklable type.
        with self.assertRaises(pickle.PickleError):
            cache.add('unpicklable', Unpicklable())

    def test_set_fail_on_pickleerror(self):
        with self.assertRaises(pickle.PickleError):
            cache.set('unpicklable', Unpicklable())

    def test_get_or_set(self):
        self.assertIsNone(cache.get('projector'))
        self.assertEqual(cache.get_or_set('projector', 42), 42)
        self.assertEqual(cache.get('projector'), 42)
        self.assertIsNone(cache.get_or_set('null', None))
        if self.supports_get_with_default:
            # Previous get_or_set() stores None in the cache.
            self.assertIsNone(cache.get('null', 'default'))
        else:
            self.assertEqual(cache.get('null', 'default'), 'default')

    def test_get_or_set_callable(self):
        def my_callable():
            return 'value'

        self.assertEqual(cache.get_or_set('mykey', my_callable), 'value')
        self.assertEqual(cache.get_or_set('mykey', my_callable()), 'value')

        self.assertIsNone(cache.get_or_set('null', lambda: None))
        if self.supports_get_with_default:
            # Previous get_or_set() stores None in the cache.
            self.assertIsNone(cache.get('null', 'default'))
        else:
            self.assertEqual(cache.get('null', 'default'), 'default')

    def test_get_or_set_version(self):
        msg = "get_or_set() missing 1 required positional argument: 'default'"
        self.assertEqual(cache.get_or_set('brian', 1979, version=2), 1979)
        with self.assertRaisesMessage(TypeError, msg):
            cache.get_or_set('brian')
        with self.assertRaisesMessage(TypeError, msg):
            cache.get_or_set('brian', version=1)
        self.assertIsNone(cache.get('brian', version=1))
        self.assertEqual(cache.get_or_set('brian', 42, version=1), 42)
        self.assertEqual(cache.get_or_set('brian', 1979, version=2), 1979)
        self.assertIsNone(cache.get('brian', version=3))

    def test_get_or_set_racing(self):
        with mock.patch(
            '%s.%s' % (settings.CACHES['default']['BACKEND'], 'add')
        ) as cache_add:
            # Simulate cache.add() failing to add a value. In that case, the
            # default value should be returned.
            cache_add.return_value = False
            self.assertEqual(cache.get_or_set('key', 'default'), 'default')


class PicklingSideEffect:
    def __init__(self, cache):
        self.cache = cache
        self.locked = False

    def __getstate__(self):
        self.locked = self.cache._lock.locked()
        return {}


@override_settings(
    CACHES=caches_setting_for_tests(
        BACKEND='diskcache.DjangoCache',
    )
)
class DiskCacheTests(BaseCacheTests, TestCase):
    """Specific test cases for diskcache.DjangoCache."""

    def setUp(self):
        super().setUp()
        self.dirname = tempfile.mkdtemp()
        # Caches location cannot be modified through override_settings / modify_settings,
        # hence settings are manipulated directly here and the setting_changed signal
        # is triggered manually.
        for cache_params in settings.CACHES.values():
            cache_params.update({'LOCATION': self.dirname})
        setting_changed.send(self.__class__, setting='CACHES', enter=False)

    def tearDown(self):
        super().tearDown()
        cache.close()
        shutil.rmtree(self.dirname, ignore_errors=True)

    def test_ignores_non_cache_files(self):
        fname = os.path.join(self.dirname, 'not-a-cache-file')
        with open(fname, 'w'):
            os.utime(fname, None)
        cache.clear()
        self.assertTrue(
            os.path.exists(fname),
            'Expected cache.clear to ignore non cache files',
        )
        os.remove(fname)

    def test_creates_cache_dir_if_nonexistent(self):
        os.rmdir(self.dirname)
        cache.set('foo', 'bar')
        self.assertTrue(os.path.exists(self.dirname))

    def test_clear_does_not_remove_cache_dir(self):
        cache.clear()
        self.assertTrue(
            os.path.exists(self.dirname),
            'Expected cache.clear to keep the cache dir',
        )

    def test_cache_write_unpicklable_type(self):
        # This fails if not using the highest pickling protocol on Python 2.
        cache.set('unpicklable', UnpicklableType())

    def test_cull(self):
        cache.cull()

    def test_zero_cull(self):
        pass  # DiskCache has its own cull strategy.

    def test_invalid_key_characters(self):
        pass  # DiskCache supports any Pickle-able value as a cache key.

    def test_invalid_key_length(self):
        pass  # DiskCache supports any Pickle-able value as a cache key.

    def test_directory(self):
        self.assertTrue('tmp' in cache.directory)

    def test_read(self):
        value = b'abcd' * 2**20
        result = cache.set(b'test-key', value)

        self.assertTrue(result)

        with cache.read(b'test-key') as reader:
            self.assertEqual(reader.read(), value)

        try:
            with cache.read(b'dne') as reader:
                error = False
        except KeyError:
            error = True

        self.assertTrue(error)

    def test_expire(self):
        cache.clear()
        cache.set(b'expire-key', 0, timeout=0.05)
        time.sleep(0.1)
        self.assertEqual(cache.expire(), 1)
        self.assertEqual(cache.get(b'expire-key'), None)

    def test_evict(self):
        cache.clear()
        for num in range(100):
            cache.set(num, num, tag=(num % 4))
        self.assertEqual(cache.evict(1), 25)
        cache.create_tag_index()
        self.assertEqual(cache.evict(2), 25)
        cache.drop_tag_index()
        self.assertEqual(cache.evict(3), 25)
        for num in range(0, 100, 4):
            self.assertEqual(cache.get(num), num)

    def test_pop(self):
        cache.clear()
        for num in range(5):
            cache.set(num, num, timeout=None)
        self.assertEqual(cache.pop(0), 0)
        self.assertEqual(cache.pop(0), None)
        self.assertEqual(cache.pop(0, 1), 1)
        self.assertEqual(cache.pop(0, default=1), 1)
        self.assertEqual(cache.pop(1, expire_time=True), (1, None))
        self.assertEqual(cache.pop(2, tag=True), (2, None))
        self.assertEqual(
            cache.pop(3, expire_time=True, tag=True), (3, None, None)
        )
        self.assertEqual(cache.pop(4, retry=False), 4)

    def test_cache(self):
        subcache = cache.cache('test')
        directory = os.path.join(cache.directory, 'cache', 'test')
        self.assertEqual(subcache.directory, directory)

    def test_deque(self):
        deque = cache.deque('test')
        directory = os.path.join(cache.directory, 'deque', 'test')
        self.assertEqual(deque.directory, directory)

    def test_index(self):
        index = cache.index('test')
        directory = os.path.join(cache.directory, 'index', 'test')
        self.assertEqual(index.directory, directory)

    def test_memoize(self):
        with self.assertRaises(TypeError):

            @cache.memoize  # <-- Missing parens!
            def test():
                pass

        count = 1000

        def fibiter(num):
            alpha, beta = 0, 1

            for _ in range(num):
                alpha, beta = beta, alpha + beta

            return alpha

        @cache.memoize()
        def fibrec(num):
            if num == 0:
                return 0
            elif num == 1:
                return 1
            else:
                return fibrec(num - 1) + fibrec(num - 2)

        cache.stats(enable=True)

        for value in range(count):
            self.assertEqual(fibrec(value), fibiter(value))

        hits1, misses1 = cache.stats()

        for value in range(count):
            self.assertEqual(fibrec(value), fibiter(value))

        hits2, misses2 = cache.stats()

        self.assertEqual(hits2, hits1 + count)
        self.assertEqual(misses2, misses1)
