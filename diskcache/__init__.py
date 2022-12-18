"""
DiskCache API Reference
=======================

The :doc:`tutorial` provides a helpful walkthrough of most methods.
"""

import importlib
import sys

_objects_modules = {
    'DEFAULT_SETTINGS': 'core',
    'ENOVAL': 'core',
    'EVICTION_POLICY': 'core',
    'UNKNOWN': 'core',
    'Cache': 'core',
    'Disk': 'core',
    'EmptyDirWarning': 'core',
    'JSONDisk': 'core',
    'Timeout': 'core',
    'UnknownFileWarning': 'core',
    'FanoutCache': 'fanout',
    'Deque': 'persistent',
    'Index': 'persistent',
    'Averager': 'recipes',
    'BoundedSemaphore': 'recipes',
    'Lock': 'recipes',
    'RLock': 'recipes',
    'barrier': 'recipes',
    'memoize_stampede': 'recipes',
    'throttle': 'recipes',
    'DjangoCache': 'djangocache',
}

# Implement PEP 562 on Python > 3.6 to avoid uneeded imports
if sys.version_info < (3, 7):
    del _objects_modules['DjangoCache']
    __all__ = list(_objects_modules.keys())

    _loaded_modules = {}

    for _object_name, _modname in _objects_modules.items():
        if _modname not in _loaded_modules:
            _loaded_modules[_modname] = importlib.import_module(
                f'diskcache.{_modname}'
            )
        globals()[_object_name] = getattr(
            _loaded_modules[_modname],
            _object_name,
        )

    try:
        from .djangocache import DjangoCache  # noqa

        __all__.append('DjangoCache')
    except ImportError as err:  # pragma: no cover
        if err.name != "django":
            raise
        # Django not installed or not setup so ignore.
else:

    def _all__():
        __all__ = list(_objects_modules.keys())
        try:
            from .djangocache import DjangoCache  # noqa

            __all__.append('DjangoCache')
        except ImportError as err:  # pragma: no cover
            if err.name != "django":
                raise
            # Django not installed or not setup so ignore.
        return __all__

    def __dir__():
        __all__ = _all__()
        del globals()['_all__']
        return __all__ + list(globals())

    def __getattr__(name):
        if name == '__all__':
            return _all__()
        elif name.startswith('__'):
            # Internal dunder name like __path__
            return globals()[name]

        try:
            modname = _objects_modules[name]
        except KeyError:
            raise ImportError(
                f"cannot import name '{name}' from diskcache",
                name=name,
            ) from None

        try:
            _module = importlib.import_module(f'diskcache.{modname}')
        except ImportError as err:
            # Manage django import error of DjangoCache in the same way
            # as non existing in __all__
            if name == 'DjangoCache' and err.name == "django":
                raise ImportError(
                    f"cannot import name 'DjangoCache' from diskcache",
                    name=name,
                ) from None
            raise
        else:
            return getattr(_module, name)


__title__ = 'diskcache'
__version__ = '5.4.0'
__build__ = 0x050400
__author__ = 'Grant Jenks'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright 2016-2022 Grant Jenks'
