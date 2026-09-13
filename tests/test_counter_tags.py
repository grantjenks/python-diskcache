"""Test atomic initialization of tagged counters."""

from concurrent.futures import ThreadPoolExecutor

import pytest

import diskcache as dc


@pytest.fixture(params=[dc.Cache, dc.FanoutCache])
def cache(request, tmp_path):
    with request.param(str(tmp_path)) as cache:
        yield cache


@pytest.mark.parametrize('method,delta', [('incr', 3), ('decr', -3)])
@pytest.mark.parametrize('tag', [None, '', 'counter'])
@pytest.mark.parametrize('expired', [False, True])
def test_counter_tag_creation(cache, method, delta, tag, expired):
    if expired:
        cache.set('count', 100, expire=-1, tag='old')

    assert (
        getattr(cache, method)('count', 3, default=10, tag=tag) == 10 + delta
    )
    assert cache.get('count', expire_time=True, tag=True) == (
        10 + delta,
        None,
        tag,
    )
    if tag is not None:
        assert cache.evict(tag) == 1
        assert 'count' not in cache


@pytest.mark.parametrize('method,delta', [('incr', 3), ('decr', -3)])
@pytest.mark.parametrize('tag', [None, '', 'replacement'])
def test_counter_tag_preserves_live_metadata(cache, method, delta, tag):
    cache.set('count', 10, expire=60, tag='original')
    _, expiry, _ = cache.get('count', expire_time=True, tag=True)

    assert getattr(cache, method)('count', 3, tag=tag) == 10 + delta
    assert cache.get('count', expire_time=True, tag=True) == (
        10 + delta,
        expiry,
        'original',
    )


@pytest.mark.parametrize('method', ['incr', 'decr'])
@pytest.mark.parametrize('expired', [False, True])
def test_counter_tag_missing_default_none(cache, method, expired):
    if expired:
        cache.set('count', 100, expire=-1, tag='old')

    with pytest.raises(KeyError):
        getattr(cache, method)('count', default=None, tag='counter')
    assert 'count' not in cache


@pytest.mark.parametrize('method,delta', [('incr', 3), ('decr', -3)])
def test_counter_original_positional_arguments(cache, method, delta):
    assert getattr(cache, method)('count', 3, 10, True) == 10 + delta
    assert cache.get('count', tag=True) == (10 + delta, None)


def test_counter_tag_concurrent_initialization(cache):
    def increment():
        try:
            return [
                cache.incr('count', retry=True, tag='counter')
                for _ in range(20)
            ]
        finally:
            cache.close()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(increment) for _ in range(4)]
        results = [value for future in futures for value in future.result(30)]

    assert sorted(results) == list(range(1, 81))
    assert cache.get('count', tag=True) == (80, 'counter')
    assert cache.evict('counter') == 1
