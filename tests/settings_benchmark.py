from .settings import *  # noqa

CACHES = {
    'default': {
        'BACKEND': 'diskcache.DjangoCache',
        'LOCATION': CACHE_DIR,  # noqa
    },
    'memcached': {
        'BACKEND': 'django.core.cache.backends.memcached.PyLibMCCache',
        'LOCATION': '127.0.0.1:11211',
    },
    'redis': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    },
    'filebased': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': '/tmp/django_cache',
        'OPTIONS': {
            'CULL_FREQUENCY': 10,
            'MAX_ENTRIES': 1000,
        },
    },
    'locmem': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'diskcache',
        'OPTIONS': {
            'CULL_FREQUENCY': 10,
            'MAX_ENTRIES': 1000,
        },
    },
    'diskcache': {
        'BACKEND': 'diskcache.DjangoCache',
        'LOCATION': 'tmp',
    },
}
