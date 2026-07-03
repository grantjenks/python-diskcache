"""Test diskcache safe pickle deserialization (CVE-2025-69872 fix)."""

import inspect
import io
import os
import pickle
import shutil
import subprocess
import tempfile
from collections import OrderedDict, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

import pytest

import diskcache as dc
from diskcache.core import MODE_PICKLE, UnpicklingError, safe_pickle_load


@pytest.fixture
def cache():
    with dc.Cache() as cache:
        yield cache
    shutil.rmtree(cache.directory, ignore_errors=True)


# --- SafeUnpickler Tests ---


class TestSafeUnpickler:
    """Test the SafeUnpickler restricts deserialization correctly."""

    def test_allows_basic_types(self):
        """Safe types should deserialize without error."""
        safe_values = [
            42,
            3.14,
            'hello',
            b'bytes',
            True,
            False,
            None,
            [1, 2, 3],
            {'key': 'value'},
            (1, 2, 3),
            {1, 2, 3},
            frozenset([1, 2, 3]),
        ]
        for value in safe_values:
            data = pickle.dumps(value)
            result = safe_pickle_load(io.BytesIO(data))
            assert result == value

    def test_allows_collections(self):
        """Standard collection types should deserialize."""
        values = [
            OrderedDict([('a', 1), ('b', 2)]),
            deque([1, 2, 3]),
        ]
        for value in values:
            data = pickle.dumps(value)
            result = safe_pickle_load(io.BytesIO(data))
            assert result == value

    def test_allows_datetime(self):
        """Datetime types should deserialize."""
        values = [
            datetime(2025, 1, 1, 12, 0, 0),
            timedelta(days=1, hours=2),
            timezone.utc,
        ]
        for value in values:
            data = pickle.dumps(value)
            result = safe_pickle_load(io.BytesIO(data))
            assert result == value

    def test_allows_decimal(self):
        """Decimal should deserialize."""
        value = Decimal('3.14159')
        data = pickle.dumps(value)
        result = safe_pickle_load(io.BytesIO(data))
        assert result == value

    def test_allows_fraction(self):
        """Fraction should deserialize."""
        value = Fraction(1, 3)
        data = pickle.dumps(value)
        result = safe_pickle_load(io.BytesIO(data))
        assert result == value

    def test_allows_uuid(self):
        """UUID should deserialize."""
        value = UUID('12345678-1234-5678-1234-567812345678')
        data = pickle.dumps(value)
        result = safe_pickle_load(io.BytesIO(data))
        assert result == value

    def test_blocks_os_system(self):
        """os.system should be blocked - classic RCE vector."""
        data = pickle.dumps(os.system)
        with pytest.raises(UnpicklingError, match='not allowed'):
            safe_pickle_load(io.BytesIO(data))

    def test_blocks_eval(self):
        """eval should be blocked."""
        data = pickle.dumps(eval)
        with pytest.raises(UnpicklingError, match='not allowed'):
            safe_pickle_load(io.BytesIO(data))

    def test_blocks_exec(self):
        """exec should be blocked."""
        data = pickle.dumps(exec)
        with pytest.raises(UnpicklingError, match='not allowed'):
            safe_pickle_load(io.BytesIO(data))

    def test_blocks_subprocess(self):
        """subprocess.Popen should be blocked."""
        data = pickle.dumps(subprocess.Popen)
        with pytest.raises(UnpicklingError, match='not allowed'):
            safe_pickle_load(io.BytesIO(data))

    def test_blocks_pickle_reduce_exploit(self):
        """Crafted __reduce__ payloads should be blocked."""

        class Exploit:
            def __reduce__(self):
                return (os.system, ('echo pwned',))

        data = pickle.dumps(Exploit())
        with pytest.raises(UnpicklingError, match='not allowed'):
            safe_pickle_load(io.BytesIO(data))

    def test_blocks_arbitrary_class(self):
        """Custom classes should be blocked."""
        data = pickle.dumps(tempfile.NamedTemporaryFile)
        with pytest.raises(UnpicklingError, match='not allowed'):
            safe_pickle_load(io.BytesIO(data))

    def test_error_message_includes_class_info(self):
        """Error message should indicate what was blocked."""
        data = pickle.dumps(os.system)
        with pytest.raises(UnpicklingError) as exc_info:
            safe_pickle_load(io.BytesIO(data))
        assert 'JSONDisk' in str(exc_info.value)

    def test_nested_safe_types(self):
        """Nested structures of safe types should work."""
        value = {
            'list': [1, 2.0, 'three'],
            'tuple': (4, 5, 6),
            'nested': {'a': [True, False, None]},
            'ordered': OrderedDict([('x', datetime(2025, 1, 1))]),
        }
        data = pickle.dumps(value)
        result = safe_pickle_load(io.BytesIO(data))
        assert result == value


# --- Cache Integration Tests ---


class TestCacheDefaultSafe:
    """Test that Cache uses safe deserialization unconditionally."""

    def test_safe_values_work(self, cache):
        """Standard safe types should round-trip through cache."""
        test_data = {
            'int': 42,
            'float': 3.14,
            'str': 'hello world',
            'bytes': b'binary data',
            'list': [1, 2, 3],
            'dict': {'nested': True},
            'tuple': (1, 'two', 3.0),
            'none': None,
            'bool': True,
        }
        for key, value in test_data.items():
            cache[key] = value

        for key, value in test_data.items():
            assert cache[key] == value

    def test_safe_complex_types(self, cache):
        """Allowed complex types should work."""
        cache['decimal'] = Decimal('3.14')
        cache['uuid'] = UUID('12345678-1234-5678-1234-567812345678')
        cache['datetime'] = datetime(2025, 6, 15, 10, 30)
        cache['ordered'] = OrderedDict([('a', 1), ('b', 2)])

        assert cache['decimal'] == Decimal('3.14')
        assert cache['uuid'] == UUID('12345678-1234-5678-1234-567812345678')
        assert cache['datetime'] == datetime(2025, 6, 15, 10, 30)
        assert cache['ordered'] == OrderedDict([('a', 1), ('b', 2)])

    def test_blocks_malicious_payload(self, cache):
        """Injecting a malicious pickle into cache should fail on read."""

        class Exploit:
            def __reduce__(self):
                return (os.system, ('echo pwned',))

        malicious_data = pickle.dumps(Exploit())

        # Manually insert malicious data as if attacker had write access
        sql = cache._sql
        sql(
            'INSERT INTO Cache (key, raw, store_time, expire_time,'
            ' access_time, access_count, tag, mode, filename, value)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                'malicious',
                True,
                0,
                None,
                0,
                0,
                None,
                MODE_PICKLE,
                None,
                malicious_data,
            ),
        )

        with pytest.raises(UnpicklingError):
            cache['malicious']


class TestNoEscapeHatch:
    """Confirm there is no way to bypass safe deserialization."""

    def test_no_allow_pickle_parameter(self):
        """Disk.__init__ should not accept allow_pickle."""
        sig = inspect.signature(dc.Disk.__init__)
        assert 'allow_pickle' not in sig.parameters

    def test_no_disk_allow_pickle_setting(self):
        """DEFAULT_SETTINGS should not contain disk_allow_pickle."""
        assert 'disk_allow_pickle' not in dc.DEFAULT_SETTINGS

    def test_unknown_disk_setting_rejected(self):
        """Passing disk_allow_pickle to Cache should raise TypeError."""
        with pytest.raises(TypeError):
            dc.Cache(disk_allow_pickle=True)

    def test_safe_unpickling_always_active(self, cache):
        """Even after explicit attempts, deserialization stays restricted."""
        # Try to bypass by setting attribute directly on disk
        cache.disk.allow_pickle = True  # This attribute doesn't exist/matter

        class Exploit:
            def __reduce__(self):
                return (os.system, ('echo pwned',))

        malicious_data = pickle.dumps(Exploit())

        sql = cache._sql
        sql(
            'INSERT INTO Cache (key, raw, store_time, expire_time,'
            ' access_time, access_count, tag, mode, filename, value)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                'bypass_attempt',
                True,
                0,
                None,
                0,
                0,
                None,
                MODE_PICKLE,
                None,
                malicious_data,
            ),
        )

        with pytest.raises(UnpicklingError):
            cache['bypass_attempt']


# --- FanoutCache Integration ---


class TestFanoutCacheSafe:
    """Test FanoutCache uses safe deserialization."""

    def test_default_safe(self):
        """FanoutCache should use safe mode."""
        with dc.FanoutCache() as cache:
            cache['key'] = [1, 2, 3]
            assert cache['key'] == [1, 2, 3]
        shutil.rmtree(cache.directory, ignore_errors=True)


# --- Deque and Index Integration ---


class TestPersistentSafe:
    """Test Deque and Index use safe deserialization."""

    def test_deque_safe(self):
        """Deque should work with safe types."""
        deq = dc.Deque([1, 2, 3])
        assert list(deq) == [1, 2, 3]
        shutil.rmtree(deq.directory, ignore_errors=True)

    def test_index_safe(self):
        """Index should work with safe types."""
        index = dc.Index({'a': 1, 'b': 2})
        assert index['a'] == 1
        shutil.rmtree(index.directory, ignore_errors=True)


# --- Key Serialization Tests ---


class TestKeySerialization:
    """Test that non-raw keys (tuple keys) are deserialized safely."""

    def test_tuple_key_safe(self, cache):
        """Tuple keys use pickle serialization and should work safely."""
        key = (1, 'two', 3.0)
        cache[key] = 'value'
        assert cache[key] == 'value'

    def test_complex_key_safe(self, cache):
        """Complex safe keys should work."""
        key = (None, 0, 'abc')
        cache[key] = 'value'
        assert cache[key] == 'value'
