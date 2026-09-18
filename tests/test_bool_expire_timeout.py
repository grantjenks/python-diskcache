"""bool subclasses int; expire=True must not silently become 1s TTL."""
import shutil

import pytest

import diskcache as dc


@pytest.fixture
def dcache():
    with dc.Cache() as cache:
        yield cache
    shutil.rmtree(cache.directory, ignore_errors=True)


@pytest.mark.parametrize("value", [True, False])
def test_cache_timeout_rejects_bool(value, tmpdir):
    with pytest.raises(TypeError, match="timeout"):
        dc.Cache(str(tmpdir), timeout=value)


@pytest.mark.parametrize("value", [True, False])
def test_set_expire_rejects_bool(value, dcache):
    with pytest.raises(TypeError, match="expire"):
        dcache.set("k", "v", expire=value)


@pytest.mark.parametrize("value", [True, False])
def test_add_expire_rejects_bool(value, dcache):
    with pytest.raises(TypeError, match="expire"):
        dcache.add("k", "v", expire=value)


@pytest.mark.parametrize("value", [True, False])
def test_touch_expire_rejects_bool(value, dcache):
    dcache.set("k", "v")
    with pytest.raises(TypeError, match="expire"):
        dcache.touch("k", expire=value)


def test_expire_still_accepts_number(dcache):
    assert dcache.set("k", "v", expire=5) is True
    assert dcache.get("k") == "v"
    assert dcache.touch("k", expire=10) is True
