"""Test JSONDisk serialization hooks."""

import io
import json
import pickle
import zlib
from decimal import Decimal
from functools import partial

import pytest

import diskcache as dc


class DecimalEncoder(json.JSONEncoder):
    def default(self, value):
        if isinstance(value, Decimal):
            return {'decimal': str(value)}
        return super().default(value)


def decimal_hook(value):
    if set(value) == {'decimal'}:
        return Decimal(value['decimal'])
    return value


class DecimalJSONDisk(dc.JSONDisk):
    json_dumps = staticmethod(partial(json.dumps, cls=DecimalEncoder))
    json_loads = staticmethod(
        partial(json.loads, object_hook=decimal_hook, parse_float=Decimal)
    )


@pytest.mark.parametrize('min_file_size', [0, 2**20])
def test_jsondisk_custom_hooks(tmp_path, min_file_size):
    with dc.Cache(
        tmp_path, disk=DecimalJSONDisk, disk_min_file_size=min_file_size
    ) as cache:
        cache[Decimal('1.25')] = {'custom': Decimal('2.5'), 'float': 3.5}
        expected = {'custom': Decimal('2.5'), 'float': Decimal('3.5')}
        assert cache[Decimal('1.25')] == expected
        assert list(cache) == [Decimal('1.25')]

        # Both key decoding and value decoding use the custom loader.
        cache[4.5] = 5.5
        assert list(cache)[-1] == Decimal('4.5')
        assert cache[4.5] == Decimal('5.5')

        with pickle.loads(pickle.dumps(cache)) as restored:
            assert restored[Decimal('1.25')] == expected
            assert restored[4.5] == Decimal('5.5')

    with dc.Cache(tmp_path, disk=DecimalJSONDisk) as reopened:
        assert reopened[Decimal('1.25')] == expected
        assert reopened[4.5] == Decimal('5.5')


def test_jsondisk_instance_hooks(tmp_path):
    disk = dc.JSONDisk(str(tmp_path))
    disk.json_dumps = partial(json.dumps, default=str)
    disk.json_loads = partial(json.loads, parse_float=Decimal)
    assert disk.get(*disk.put(Decimal('1.25'))) == '1.25'
    assert disk.get(*disk.put(1.25)) == Decimal('1.25')


@pytest.mark.parametrize('compress_level', [0, 1, 9])
@pytest.mark.parametrize('min_file_size', [0, 2**20])
def test_jsondisk_default_bytes(tmp_path, compress_level, min_file_size):
    disk = dc.JSONDisk(
        str(tmp_path),
        compress_level=compress_level,
        min_file_size=min_file_size,
    )
    value = {'unicode': '\u00e9', 'values': [None, True, 1, 2.5]}
    expected = zlib.compress(json.dumps(value).encode('utf-8'), compress_level)
    key, raw = disk.put(value)
    assert bytes(key) == expected
    assert raw
    assert disk.get(key, raw) == value

    _, mode, filename, stored = disk.store(value, False)
    assert (filename is None) == bool(min_file_size)
    assert dc.Disk.fetch(disk, mode, filename, stored, False) == expected
    assert disk.fetch(mode, filename, stored, False) == value


def test_jsondisk_read_bypasses_hooks(tmp_path):
    def unexpected(value):
        pytest.fail('stream data must not use JSON serialization hooks')

    disk = dc.JSONDisk(str(tmp_path))
    disk.json_dumps = unexpected
    disk.json_loads = unexpected
    data = b'\x00\xffnot JSON'
    _, mode, filename, value = disk.store(io.BytesIO(data), True)
    with disk.fetch(mode, filename, value, True) as reader:
        assert reader.read() == data
