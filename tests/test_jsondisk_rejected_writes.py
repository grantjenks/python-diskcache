"""Rejected serializer input must not replace existing cached data."""

import json

import pytest

import diskcache as dc


@pytest.mark.parametrize('min_file_size', [0, 2**20])
@pytest.mark.parametrize('target', ['key', 'value'])
def test_jsondisk_rejected_write_preserves_data(
    tmp_path, min_file_size, target
):
    class RejectingJSONDisk(dc.JSONDisk):
        @staticmethod
        def json_dumps(value):
            if value == '__reject__':
                raise ValueError('serializer rejected input')
            return json.dumps(value)

    original = {'payload': 'original'}
    with dc.Cache(
        tmp_path, disk=RejectingJSONDisk, disk_min_file_size=min_file_size
    ) as cache:
        cache['kept'] = original
        before = {
            path.relative_to(tmp_path): path.read_bytes()
            for path in tmp_path.rglob('*.val')
        }
        assert bool(before) == (min_file_size == 0)

        with pytest.raises(ValueError, match='serializer rejected input'):
            if target == 'key':
                cache['__reject__'] = 'replacement'
            else:
                cache['kept'] = '__reject__'

        assert len(cache) == 1
        assert list(cache) == ['kept']
        assert cache['kept'] == original
        assert {
            path.relative_to(tmp_path): path.read_bytes()
            for path in tmp_path.rglob('*.val')
        } == before

    with dc.Cache(tmp_path, disk=RejectingJSONDisk) as reopened:
        assert len(reopened) == 1
        assert list(reopened) == ['kept']
        assert reopened['kept'] == original
