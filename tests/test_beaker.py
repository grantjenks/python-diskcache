from beaker.cache import Cache


def test_has_key():
    cache = Cache('test', data_dir='./cache', type='ext:diskcache')
    o = object()
    cache.set_value("test", o)
    assert cache.has_key("test")
    assert "test" in cache
    assert not cache.has_key("foo")
    assert "foo" not in cache
    cache.remove_value("test")
    assert not cache.has_key("test")


def test_has_key_multicache():
    cache = Cache('test', data_dir='./cache', type='ext:diskcache')
    o = object()
    cache.set_value("test", o)
    assert cache.has_key("test")
    assert "test" in cache
    cache = Cache('test', data_dir='./cache', type='ext:diskcache')
    assert cache.has_key("test")
    cache.remove_value('test')


def test_clear():
    cache = Cache('test', data_dir='./cache', type='ext:diskcache')
    o = object()
    cache.set_value("test", o)
    assert cache.has_key("test")
    cache.clear()
    assert not cache.has_key("test")


def test_unicode_keys():
    cache = Cache('test', data_dir='./cache', type='ext:diskcache')
    o = object()
    cache.set_value(u_('hiŏ'), o)
    assert u_('hiŏ') in cache
    assert u_('hŏa') not in cache
    cache.remove_value(u_('hiŏ'))
    assert u_('hiŏ') not in cache
