"""Tests for the CVE-2025-69872 / GHSA-w8v5-vhqr-4h9v mitigation.

These tests exercise the HMAC envelope wrapping every pickle blob written
by :class:`diskcache.Disk`.  They live in their own module so the rest of
the suite continues to run with the default
:class:`UnsafePickleWarning` filter, while these tests can opt to either
suppress or assert that the warning is emitted.
"""

import hashlib
import hmac
import io
import multiprocessing
import os
import os.path as op
import pickle
import secrets
import shutil
import sqlite3
import sys
import tempfile
import warnings
import errno

import pytest

import diskcache as dc
from diskcache.core import (
    PICKLE_HEADER_SIZE,
    PICKLE_KEY_ENV,
    PICKLE_KEY_FILENAME,
    PICKLE_MAGIC,
)


pytestmark = pytest.mark.filterwarnings(
    'ignore', category=dc.EmptyDirWarning
)


@pytest.fixture
def tmp_cache_dir():
    path = tempfile.mkdtemp(prefix='diskcache-sec-')
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def clear_env(monkeypatch):
    monkeypatch.delenv(PICKLE_KEY_ENV, raising=False)


# -- helpers ------------------------------------------------------------


class _Pwn:
    """Pickle payload that would execute code if naively unpickled."""

    def __reduce__(self):
        # Using ``print`` rather than ``os.system`` keeps the test
        # self-contained and side-effect free if the protection ever
        # regresses.
        return (print, ('PWNED!',))


def _force_evil_inline_pickle(directory, key):
    """Replace the inline pickle blob for ``key`` with a malicious payload."""
    con = sqlite3.connect(op.join(directory, 'cache.db'))
    try:
        con.execute(
            'UPDATE Cache SET value = ?, mode = 4 WHERE key = ?',
            (pickle.dumps(_Pwn()), key),
        )
        con.commit()
    finally:
        con.close()


def _val_files(directory):
    out = []
    for root, _, files in os.walk(directory):
        for name in files:
            if name.endswith('.val'):
                out.append(op.join(root, name))
    return out


# -- round-trip & default behaviour ------------------------------------


def test_default_roundtrip_emits_warning_and_creates_key_file(
    tmp_cache_dir, clear_env
):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.Cache(tmp_cache_dir) as cache:
            cache[('tup', 'le')] = {'nested': [1, 2, 3]}
            assert cache[('tup', 'le')] == {'nested': [1, 2, 3]}
            cache.check()

    msgs = [w for w in caught if isinstance(w.message, dc.UnsafePickleWarning)]
    assert msgs, 'expected UnsafePickleWarning for in-dir auto key'
    assert PICKLE_KEY_FILENAME in str(msgs[0].message)
    assert op.isfile(op.join(tmp_cache_dir, PICKLE_KEY_FILENAME))


def test_envelope_header_is_present_in_db(tmp_cache_dir, clear_env):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            cache['k'] = {'value': 'object'}

    con = sqlite3.connect(op.join(tmp_cache_dir, 'cache.db'))
    try:
        ((blob,),) = con.execute(
            'SELECT value FROM Cache WHERE key = ?', ('k',)
        ).fetchall()
    finally:
        con.close()

    raw = bytes(blob)
    assert raw.startswith(PICKLE_MAGIC)
    assert len(raw) > PICKLE_HEADER_SIZE


# -- explicit key ------------------------------------------------------


def test_explicit_key_no_keyfile_no_warning(tmp_cache_dir, clear_env):
    key = secrets.token_bytes(32)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['x'] = [1, 2, 3]
            assert cache['x'] == [1, 2, 3]

    assert not any(
        isinstance(w.message, dc.UnsafePickleWarning) for w in caught
    )
    assert not op.exists(op.join(tmp_cache_dir, PICKLE_KEY_FILENAME))


def test_explicit_key_hex_string(tmp_cache_dir, clear_env):
    key = secrets.token_bytes(32).hex()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['x'] = ['hex-keyed']
            assert cache['x'] == ['hex-keyed']


def test_explicit_key_too_short_raises(tmp_cache_dir, clear_env):
    with pytest.raises(ValueError, match='at least'):
        dc.Cache(tmp_cache_dir, disk_pickle_key=b'shortkey')


def test_explicit_key_wrong_type_raises(tmp_cache_dir, clear_env):
    with pytest.raises(TypeError):
        dc.Cache(tmp_cache_dir, disk_pickle_key=12345)


def test_explicit_key_not_persisted_in_settings(tmp_cache_dir, clear_env):
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['x'] = {'persist?': False}

    con = sqlite3.connect(op.join(tmp_cache_dir, 'cache.db'))
    try:
        rows = con.execute(
            'SELECT key, value FROM Settings WHERE key LIKE ?',
            ('%pickle_key%',),
        ).fetchall()
    finally:
        con.close()

    assert rows == [], (
        'disk_pickle_key must NOT be persisted in the Settings table'
    )


def test_mismatched_key_fails_to_decrypt(tmp_cache_dir, clear_env):
    key1 = secrets.token_bytes(32)
    key2 = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key1) as cache:
            cache['k'] = {'secret': True}
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key2) as cache:
            with pytest.raises(pickle.UnpicklingError):
                cache['k']


# -- env var -----------------------------------------------------------


def test_env_var_used_when_no_explicit_key(tmp_cache_dir, monkeypatch):
    monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.Cache(tmp_cache_dir) as cache:
            cache['k'] = {'env': True}
            assert cache['k'] == {'env': True}

    assert not any(
        isinstance(w.message, dc.UnsafePickleWarning) for w in caught
    )
    assert not op.exists(op.join(tmp_cache_dir, PICKLE_KEY_FILENAME))


def test_env_var_invalid_hex_raises(tmp_cache_dir, monkeypatch):
    monkeypatch.setenv(PICKLE_KEY_ENV, 'not-hex-at-all')
    with dc.Cache(tmp_cache_dir) as cache:
        with pytest.raises(ValueError, match='hex'):
            cache['k'] = {'x': 1}


# -- tamper detection --------------------------------------------------


def test_tampered_inline_value_raises(tmp_cache_dir, clear_env):
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['k'] = {'foo': 'bar'}

    _force_evil_inline_pickle(tmp_cache_dir, 'k')

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            with pytest.raises(pickle.UnpicklingError):
                cache['k']


def test_bitflip_inline_value_raises(tmp_cache_dir, clear_env):
    """Tampering that keeps the envelope header but corrupts the payload
    must fail HMAC verification (not just the missing-envelope check)."""
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['k'] = {'foo': 'bar'}

    con = sqlite3.connect(op.join(tmp_cache_dir, 'cache.db'))
    try:
        ((blob,),) = con.execute(
            'SELECT value FROM Cache WHERE key = ?', ('k',)
        ).fetchall()
        raw = bytearray(bytes(blob))
        # Flip a bit deep inside the payload (past the 36-byte header).
        raw[-1] ^= 0x01
        con.execute(
            'UPDATE Cache SET value = ? WHERE key = ?', (bytes(raw), 'k')
        )
        con.commit()
    finally:
        con.close()

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            with pytest.raises(pickle.UnpicklingError, match='HMAC'):
                cache['k']


def test_tampered_val_file_raises(tmp_cache_dir, clear_env):
    key = secrets.token_bytes(32)
    big_value = {'data': 'x' * (40 * 1024)}
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(
            tmp_cache_dir, disk_pickle_key=key, disk_min_file_size=1024
        ) as cache:
            cache['big'] = big_value

    files = _val_files(tmp_cache_dir)
    assert len(files) == 1, files
    with open(files[0], 'wb') as writer:
        writer.write(pickle.dumps(_Pwn()))

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            with pytest.raises(pickle.UnpicklingError):
                cache['big']


def test_tampered_pickled_key_via_iteration_raises(tmp_cache_dir, clear_env):
    """Complex (pickled) keys are loaded during iteration / peekitem, so
    tampering them must surface as UnpicklingError on those paths."""
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache[('complex', 'key')] = 'value'

    con = sqlite3.connect(op.join(tmp_cache_dir, 'cache.db'))
    try:
        rows = con.execute(
            'SELECT rowid, key FROM Cache WHERE raw = 0'
        ).fetchall()
        assert rows, 'expected at least one pickled key row'
        rowid, _ = rows[0]
        evil = pickle.dumps(_Pwn())
        con.execute(
            'UPDATE Cache SET key = ? WHERE rowid = ?',
            (sqlite3.Binary(evil), rowid),
        )
        con.commit()
    finally:
        con.close()

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            with pytest.raises(pickle.UnpicklingError):
                list(cache)


# -- legacy mode -------------------------------------------------------


def test_legacy_mode_emits_warning_and_works(tmp_cache_dir, clear_env):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.Cache(tmp_cache_dir, disk_pickle_key=False) as cache:
            cache['z'] = {'legacy': True}
            assert cache['z'] == {'legacy': True}

    msgs = [w for w in caught if isinstance(w.message, dc.UnsafePickleWarning)]
    assert msgs, 'pickle_key=False must emit UnsafePickleWarning'
    assert 'disabled' in str(msgs[0].message).lower()


def test_secure_mode_rejects_legacy_data(tmp_cache_dir, clear_env):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=False) as cache:
            cache['k'] = {'legacy': True}
        with dc.Cache(
            tmp_cache_dir, disk_pickle_key=secrets.token_bytes(32)
        ) as cache:
            with pytest.raises(pickle.UnpicklingError, match='envelope'):
                cache['k']


def test_legacy_mode_can_read_secure_data(tmp_cache_dir, clear_env):
    """Legacy mode strips the envelope so it can read forward as well."""
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['k'] = {'enveloped': True}
        with dc.Cache(tmp_cache_dir, disk_pickle_key=False) as cache:
            assert cache['k'] == {'enveloped': True}


# -- JSONDisk unaffected ------------------------------------------------


def test_jsondisk_does_not_create_keyfile(tmp_cache_dir, clear_env):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.Cache(tmp_cache_dir, disk=dc.JSONDisk) as cache:
            cache['a'] = [1, 2, 3]
            assert cache['a'] == [1, 2, 3]

    assert not any(
        isinstance(w.message, dc.UnsafePickleWarning) for w in caught
    )
    assert not op.exists(op.join(tmp_cache_dir, PICKLE_KEY_FILENAME))


# -- Cache.check whitelist ---------------------------------------------


def test_check_does_not_warn_about_keyfile(tmp_cache_dir, clear_env):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.Cache(tmp_cache_dir) as cache:
            cache['k'] = {'foo': 'bar'}
            warns = cache.check()
        assert op.isfile(op.join(tmp_cache_dir, PICKLE_KEY_FILENAME))

    unknown = [w for w in warns if isinstance(w.message, dc.UnknownFileWarning)]
    assert unknown == [], (
        'cache.check() must whitelist .diskcache_pickle_key, got %r' % unknown
    )

    unknown_top = [
        w for w in caught if isinstance(w.message, dc.UnknownFileWarning)
    ]
    assert unknown_top == []


# -- primitive keys/values bypass pickle entirely ----------------------


def test_primitive_only_does_not_create_keyfile(tmp_cache_dir, clear_env):
    """Lazy resolution means a cache used only with primitive keys and
    values never triggers HMAC key creation."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.Cache(tmp_cache_dir) as cache:
            cache['plain-str-key'] = 'plain-str-value'
            cache[42] = 3.14
            cache[b'bytes-key'] = b'bytes-value'
            assert cache['plain-str-key'] == 'plain-str-value'

    assert not any(
        isinstance(w.message, dc.UnsafePickleWarning) for w in caught
    )
    assert not op.exists(op.join(tmp_cache_dir, PICKLE_KEY_FILENAME))


# -- Review-pass-2: path traversal (C2) --------------------------------


def _put_evil_filename(directory, key, evil_filename, mode=2):
    """Replace the row's filename to point outside the cache dir."""
    con = sqlite3.connect(op.join(directory, 'cache.db'))
    try:
        con.execute(
            'UPDATE Cache SET filename = ?, mode = ?, value = NULL '
            'WHERE key = ?',
            (evil_filename, mode, key),
        )
        con.commit()
    finally:
        con.close()


def test_path_traversal_in_filename_raises(tmp_cache_dir, clear_env):
    """An attacker who tampers cache.db's ``filename`` column to point
    outside the cache directory must not be able to coerce DiskCache
    into reading arbitrary files (CVE-2025-69872 adjacent)."""
    secret_dir = tempfile.mkdtemp(prefix='diskcache-secret-')
    try:
        secret_path = op.join(secret_dir, 'secret.txt')
        with open(secret_path, 'wb') as fh:
            fh.write(b'TOP SECRET')

        key = secrets.token_bytes(32)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', dc.UnsafePickleWarning)
            with dc.Cache(
                tmp_cache_dir,
                disk_pickle_key=key,
                disk_min_file_size=1,
            ) as cache:
                cache['k'] = b'x' * 64

        rel = op.relpath(secret_path, tmp_cache_dir)
        _put_evil_filename(tmp_cache_dir, 'k', rel, mode=2)

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', dc.UnsafePickleWarning)
            with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
                with pytest.raises(ValueError, match='escapes cache'):
                    cache['k']
    finally:
        shutil.rmtree(secret_dir, ignore_errors=True)


def test_path_traversal_blocked_for_text_mode(tmp_cache_dir, clear_env):
    secret_dir = tempfile.mkdtemp(prefix='diskcache-secret-')
    try:
        secret_path = op.join(secret_dir, 'secret.txt')
        with open(secret_path, 'w', encoding='utf-8') as fh:
            fh.write('TOP SECRET')

        key = secrets.token_bytes(32)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', dc.UnsafePickleWarning)
            with dc.Cache(
                tmp_cache_dir,
                disk_pickle_key=key,
                disk_min_file_size=1,
            ) as cache:
                cache['k'] = 'x' * 64

        rel = op.relpath(secret_path, tmp_cache_dir)
        _put_evil_filename(tmp_cache_dir, 'k', rel, mode=3)

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', dc.UnsafePickleWarning)
            with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
                with pytest.raises(ValueError, match='escapes cache'):
                    cache['k']
    finally:
        shutil.rmtree(secret_dir, ignore_errors=True)


def test_remove_refuses_traversal(tmp_cache_dir, clear_env):
    """Disk.remove must refuse path-traversal filenames silently
    (eviction must be tolerant) but still emit an UnsafePickleWarning
    so operators see the tampering."""
    sentinel_dir = tempfile.mkdtemp(prefix='diskcache-sentinel-')
    try:
        sentinel = op.join(sentinel_dir, 'do-not-delete.txt')
        with open(sentinel, 'wb') as fh:
            fh.write(b'KEEP ME')

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', dc.UnsafePickleWarning)
            with dc.Cache(tmp_cache_dir) as cache:
                disk = cache._disk

        rel = op.relpath(sentinel, tmp_cache_dir)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            disk.remove(rel)

        assert op.exists(sentinel), 'sentinel file must not be deleted'
        assert any(
            isinstance(w.message, dc.UnsafePickleWarning)
            and 'refusing to remove' in str(w.message)
            for w in caught
        )
    finally:
        shutil.rmtree(sentinel_dir, ignore_errors=True)


# -- Review-pass-2: FanoutCache (C3) -----------------------------------


def test_fanoutcache_propagates_explicit_key(tmp_cache_dir, clear_env):
    key = secrets.token_bytes(32)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.FanoutCache(
            tmp_cache_dir, shards=4, disk_pickle_key=key
        ) as cache:
            cache[('complex', 'key')] = {'value': [1, 2, 3]}
            assert cache[('complex', 'key')] == {'value': [1, 2, 3]}

    assert not any(
        isinstance(w.message, dc.UnsafePickleWarning) for w in caught
    ), 'explicit key must not emit UnsafePickleWarning'

    # No per-shard key file: the explicit key was forwarded.
    for num in range(4):
        shard_dir = op.join(tmp_cache_dir, '%03d' % num)
        assert not op.exists(op.join(shard_dir, PICKLE_KEY_FILENAME))


def test_fanoutcache_default_emits_one_warning(tmp_cache_dir, clear_env):
    """With the default fallback, FanoutCache must emit ONE warning,
    not one-per-shard, and create a single key file at the FanoutCache
    root (not per-shard)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.FanoutCache(tmp_cache_dir, shards=4) as cache:
            cache[('a', 'b')] = {'val': 1}
            cache[('c', 'd')] = {'val': 2}
            cache[('e', 'f')] = {'val': 3}
            assert cache[('a', 'b')] == {'val': 1}
            assert cache[('c', 'd')] == {'val': 2}

    pkey_warnings = [
        w for w in caught if isinstance(w.message, dc.UnsafePickleWarning)
    ]
    assert len(pkey_warnings) == 1, (
        'expected exactly one UnsafePickleWarning per FanoutCache, got %d'
        % len(pkey_warnings)
    )

    # Root-level key file exists; CVE-2025-69872 (L1) shards now ALSO
    # mirror the same key file into their own directory so a process
    # that opens a shard directly as ``Cache(shard_dir)`` can recover
    # the same HMAC key via default resolution.  All copies must
    # equal the root key.
    root_key_path = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)
    assert op.exists(root_key_path)
    with open(root_key_path, 'rb') as fh:
        root_key = fh.read()
    for num in range(4):
        shard_dir = op.join(tmp_cache_dir, '%03d' % num)
        shard_key_path = op.join(shard_dir, PICKLE_KEY_FILENAME)
        assert op.exists(shard_key_path), (
            'L1: shard %d must mirror the root key file' % num
        )
        with open(shard_key_path, 'rb') as fh:
            assert fh.read() == root_key, (
                'L1: shard %d key file must equal root key' % num
            )


def test_fanoutcache_two_instances_share_default_key(
    tmp_cache_dir, clear_env
):
    """Two FanoutCache instances on the same directory must produce
    consistent sharding and read each other's writes."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(tmp_cache_dir, shards=4) as a:
            a[('shared', 'tuple', 'key')] = {'from': 'a'}
        with dc.FanoutCache(tmp_cache_dir, shards=4) as b:
            assert b[('shared', 'tuple', 'key')] == {'from': 'a'}


# -- Review-pass-2: Cache.check root-only whitelist (H1) ---------------


def test_check_does_not_whitelist_subdirectory_keyfile(
    tmp_cache_dir, clear_env
):
    """Attacker plants ``.diskcache_pickle_key`` in a subdirectory; the
    whitelist must not preserve it (basename-only would have).

    We assert the observable side effect: ``check(fix=True)`` deletes
    the subdirectory decoy.  (Pytest's warning capture interacts oddly
    with ``check()``'s own ``warnings.catch_warnings(record=True)``
    block, so we don't rely on the returned warning list.)
    """
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_min_file_size=0) as cache:
            cache['k'] = 'x' * 200  # forces .val file in subdirectory

            subdir = None
            for entry in os.listdir(tmp_cache_dir):
                full = op.join(tmp_cache_dir, entry)
                if op.isdir(full):
                    subdir = full
                    break
            assert subdir is not None, (
                'expected subdir; got %r' % os.listdir(tmp_cache_dir)
            )
            decoy = op.join(subdir, PICKLE_KEY_FILENAME)
            with open(decoy, 'wb') as fh:
                fh.write(b'attacker-controlled-bytes')

            assert op.exists(decoy)
            cache.check(fix=True)
            assert not op.exists(decoy), (
                'check(fix=True) must delete the subdirectory decoy '
                '(basename-only whitelist would have preserved it)'
            )

            # Sanity: legitimate root-level key file (not present here
            # since we used disk_min_file_size=0 and didn't pickle) is
            # not accidentally flagged either; create one and re-check.
            root_key = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)
            with open(root_key, 'wb') as fh:
                fh.write(b'X' * 32)
            cache.check(fix=True)
            assert op.exists(root_key), (
                'root-level key file must remain whitelisted'
            )


# -- Review-pass-2: Cache pickling (H2) --------------------------------


def test_cache_pickling_with_explicit_key_raises(tmp_cache_dir, clear_env):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        cache = dc.Cache(tmp_cache_dir, disk_pickle_key=secrets.token_bytes(32))
        try:
            with pytest.raises(TypeError, match='disk_pickle_key'):
                pickle.dumps(cache)
        finally:
            cache.close()


def test_cache_pickling_with_legacy_mode_raises(tmp_cache_dir, clear_env):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        cache = dc.Cache(tmp_cache_dir, disk_pickle_key=False)
        try:
            with pytest.raises(TypeError, match='disk_pickle_key'):
                pickle.dumps(cache)
        finally:
            cache.close()


def test_cache_pickling_with_default_succeeds(tmp_cache_dir, clear_env):
    """No explicit key + default fallback: pickling must work because
    the receiving process can re-resolve from env or file."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            cache['k'] = {'value': 1}
            blob = pickle.dumps(cache)
            other = pickle.loads(blob)
            try:
                assert other['k'] == {'value': 1}
            finally:
                other.close()


# -- Review-pass-2: defensive Settings pop (M3) ------------------------


def test_disk_pickle_key_in_settings_does_not_leak(tmp_cache_dir, clear_env):
    """A stale ``disk_pickle_key`` row in Settings (e.g. from an older
    patched build, manual edit, or attacker) must NOT influence the
    actual HMAC key used by the Disk on subsequent opens."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            cache['warm'] = 1

    # Manually inject a hostile row that, if naively trusted, would
    # become the HMAC key string.
    poisoned = 'attacker-supplied-key-' + 'A' * 16
    con = sqlite3.connect(op.join(tmp_cache_dir, 'cache.db'))
    try:
        con.execute(
            'INSERT OR REPLACE INTO Settings VALUES (?, ?)',
            ('disk_pickle_key', poisoned),
        )
        con.commit()
    finally:
        con.close()

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            cache['after'] = {'value': 1}
            assert cache['after'] == {'value': 1}
            disk = cache._disk

    # The Disk's pickle_key_arg must remain UNSET (defensive pop did
    # its job); the resolved key must not equal the poisoned bytes.
    from diskcache.core import _PICKLE_KEY_UNSET as UNSET
    assert disk._pickle_key_arg is UNSET, (
        'pickle_key_arg leaked from Settings: %r' % disk._pickle_key_arg
    )
    if disk._pickle_key_resolved not in (None, False):
        assert disk._pickle_key_resolved != poisoned.encode('utf-8'), (
            'resolved key matches poisoned Settings row'
        )


# -- Review-pass-2: edge-case envelope parsing (M9) --------------------


def test_short_envelope_header_raises(tmp_cache_dir, clear_env):
    """Bytes that start with ``DCv1`` but are shorter than the full
    36-byte header must NOT be treated as enveloped."""
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['k'] = 1

    con = sqlite3.connect(op.join(tmp_cache_dir, 'cache.db'))
    try:
        # Magic + only 20 bytes (truncated MAC).
        con.execute(
            'UPDATE Cache SET value = ?, mode = 4 WHERE key = ?',
            (PICKLE_MAGIC + b'\x00' * 20, 'k'),
        )
        con.commit()
    finally:
        con.close()

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            with pytest.raises(pickle.UnpicklingError):
                cache['k']


def test_zero_byte_value_raises(tmp_cache_dir, clear_env):
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['k'] = 1

    con = sqlite3.connect(op.join(tmp_cache_dir, 'cache.db'))
    try:
        con.execute(
            'UPDATE Cache SET value = ?, mode = 4 WHERE key = ?',
            (b'', 'k'),
        )
        con.commit()
    finally:
        con.close()

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            with pytest.raises(pickle.UnpicklingError, match='envelope'):
                cache['k']


def test_valid_hmac_invalid_pickle_raises(tmp_cache_dir, clear_env):
    """An attacker who somehow obtains the key (or a corrupted-but-
    HMAC-valid blob) and writes a non-pickle payload should still get a
    pickle error -- not silent garbage."""
    key = secrets.token_bytes(32)
    payload = b'\xff' * 50  # not valid pickle
    mac = hmac.new(key, payload, hashlib.sha256).digest()
    envelope = PICKLE_MAGIC + mac + payload

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['k'] = 1

    con = sqlite3.connect(op.join(tmp_cache_dir, 'cache.db'))
    try:
        con.execute(
            'UPDATE Cache SET value = ?, mode = 4 WHERE key = ?',
            (envelope, 'k'),
        )
        con.commit()
    finally:
        con.close()

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            # CVE-2025-69872 V22: tighten -- previous version accepted
            # KeyError, masking a regression where a corrupt HMAC-valid
            # entry could be treated as a cache miss.  pickle/EOFError
            # are the only legitimate outcomes here.
            with pytest.raises((pickle.UnpicklingError, EOFError)):
                cache['k']


def test_env_var_short_hex_raises(tmp_cache_dir, monkeypatch):
    monkeypatch.setenv(PICKLE_KEY_ENV, 'deadbeef')  # 4 bytes
    with dc.Cache(tmp_cache_dir) as cache:
        with pytest.raises(ValueError, match='at least'):
            cache['x'] = {'complex': 'value'}


def test_env_var_empty_raises(tmp_cache_dir, monkeypatch, clear_env):
    """Empty string env var must NOT be silently treated as 'unset'.

    monkeypatch the env var to '' explicitly; the resolution code uses
    ``if env_value:`` so empty falls through to the file fallback,
    which is the intended behavior.  Verify that path works (no crash).
    """
    monkeypatch.setenv(PICKLE_KEY_ENV, '')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            cache['k'] = {'val': 1}
            assert cache['k'] == {'val': 1}
    # File fallback created the key file because env was effectively unset.
    assert op.exists(op.join(tmp_cache_dir, PICKLE_KEY_FILENAME))


# -- Review-pass-2: multi-process race on key file (H3) ----------------


def _race_worker(directory, idx, queue):  # pragma: no cover - subprocess
    import warnings as _w
    import diskcache as _dc

    _w.simplefilter('ignore', _dc.UnsafePickleWarning)
    try:
        with _dc.Cache(directory) as cache:
            cache[('worker', idx)] = {'pid': os.getpid(), 'idx': idx}
            queue.put(('ok', idx, cache[('worker', idx)]))
    except Exception as exc:  # pylint: disable=broad-except
        queue.put(('err', idx, repr(exc)))


@pytest.mark.skipif(
    sys.platform == 'win32' and sys.version_info < (3, 8),
    reason='multiprocessing fork start method is unreliable on this combo',
)
def test_concurrent_key_file_creation_no_crash(tmp_cache_dir, clear_env):
    """Multiple processes creating the same fresh cache must all
    succeed -- the original code crashed losers with a false-positive
    'too short' error before the writer's os.write completed."""
    ctx = multiprocessing.get_context('spawn')
    queue = ctx.Queue()
    procs = [
        ctx.Process(target=_race_worker, args=(tmp_cache_dir, i, queue))
        for i in range(4)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0, (
            'worker exited %s; stdout/stderr should not contain '
            'RuntimeError("too short")' % p.exitcode
        )

    results = []
    while not queue.empty():
        results.append(queue.get_nowait())
    assert len(results) == 4
    for status, idx, payload in results:
        assert status == 'ok', 'worker %d failed: %r' % (idx, payload)


# -- Review-pass-2: sanity for trimmed TypeError (M4) ------------------


def test_typeerror_message_lists_only_real_types(tmp_cache_dir, clear_env):
    with pytest.raises(TypeError) as exc_info:
        dc.Cache(tmp_cache_dir, disk_pickle_key=12345)
    msg = str(exc_info.value)
    assert 'bytes' in msg and 'hex str' in msg
    assert 'False' not in msg and 'None' not in msg, (
        'TypeError must not advertise False/None: caller filters them. '
        'Got: %r' % msg
    )


# -- Pass-3 round of fixes ---------------------------------------------


def test_v3_keyboard_interrupt_during_write_cleans_up(
    tmp_cache_dir, clear_env, monkeypatch
):
    """V3: BaseException (KeyboardInterrupt / SystemExit) during the
    key-file write must not leave an empty file behind that
    permanently blocks every subsequent process."""
    from diskcache import core as dc_core

    keyfile = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)
    orig_write = os.write

    def kbd_int_write(fd, data):  # pragma: no cover - exercised below
        raise KeyboardInterrupt('simulated Ctrl+C')

    monkeypatch.setattr(os, 'write', kbd_int_write)
    with pytest.raises(KeyboardInterrupt):
        dc_core._read_or_create_pickle_key_file(keyfile)
    monkeypatch.setattr(os, 'write', orig_write)

    assert not op.exists(keyfile), (
        'Empty key file must be unlinked after KeyboardInterrupt; '
        'leaving it behind permanently blocks other processes with '
        'a "too short" RuntimeError.'
    )

    # And a fresh attempt now succeeds without manual cleanup:
    key, created = dc_core._read_or_create_pickle_key_file(keyfile)
    assert created and len(key) >= 16


def test_v3_oserror_during_write_cleans_up(
    tmp_cache_dir, clear_env, monkeypatch
):
    """V3: A regular OSError (disk full) during write must also remove
    the half-baked file."""
    from diskcache import core as dc_core

    keyfile = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)

    def disk_full_write(fd, data):
        raise OSError(28, 'No space left on device')

    monkeypatch.setattr(os, 'write', disk_full_write)
    with pytest.raises(OSError):
        dc_core._read_or_create_pickle_key_file(keyfile)
    assert not op.exists(keyfile)


def test_v9_unc_or_invalid_filename_raises_valueerror(
    tmp_cache_dir, clear_env
):
    """V9: ``_safe_filename_path`` must translate platform OSError
    (e.g. Windows UNC path resolution failure) into the documented
    ValueError so callers don't have to also catch OSError."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            disk = cache._disk
    if sys.platform == 'win32':
        with pytest.raises(ValueError):
            disk._safe_filename_path(
                '//nonexistent-server-xyz9876/share/file.txt'
            )
    else:
        # On POSIX, realpath of an absolute path that escapes the dir
        # also surfaces as ValueError (containment check rather than
        # OSError, but same exception class as documented).
        with pytest.raises(ValueError):
            disk._safe_filename_path('/etc/passwd')


def test_v6_realpath_cached_after_first_call(tmp_cache_dir, clear_env):
    """V6: After the first call, ``_directory_realpath`` is populated
    so subsequent fetches do not re-resolve the cache directory."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(
            tmp_cache_dir,
            disk_pickle_key=secrets.token_bytes(32),
            disk_min_file_size=1,
        ) as cache:
            assert cache._disk._directory_realpath is None
            cache['k'] = b'x' * 64        # forces a .val file
            _ = cache['k']                 # triggers _safe_filename_path
            cached = cache._disk._directory_realpath
            assert cached is not None
            assert cached == op.realpath(tmp_cache_dir)


def test_v13_filename_none_with_file_mode_raises_valueerror(
    tmp_cache_dir, clear_env
):
    """V13: a tampered row with mode=BINARY/TEXT/PICKLE and
    filename=NULL must raise a clear ValueError -- not the previous
    ``UnboundLocalError: local variable 'full_path' referenced before
    assignment``."""
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['k'] = b'x' * 16

    con = sqlite3.connect(op.join(tmp_cache_dir, 'cache.db'))
    try:
        con.execute(
            'UPDATE Cache SET filename = NULL, mode = 2, value = NULL '
            'WHERE key = ?', ('k',)
        )
        con.commit()
    finally:
        con.close()

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            with pytest.raises(ValueError, match='mode'):
                cache['k']


def test_v5_jsondisk_fanout_no_keyfile_no_warning(
    tmp_cache_dir, clear_env
):
    """V5: ``FanoutCache(disk=JSONDisk)`` must NOT auto-generate the
    pickle HMAC key file or emit ``UnsafePickleWarning``, since
    JSONDisk never exercises the pickle path."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.FanoutCache(
            tmp_cache_dir, shards=4, disk=dc.JSONDisk
        ) as cache:
            cache[('a', 'b')] = {'v': 1}
            assert cache[('a', 'b')] == {'v': 1}

    pkey_warnings = [
        w for w in caught if isinstance(w.message, dc.UnsafePickleWarning)
    ]
    assert pkey_warnings == [], (
        'JSONDisk under FanoutCache must not emit UnsafePickleWarning, '
        'got: %r' % [str(w.message) for w in pkey_warnings]
    )
    assert not op.exists(op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)), (
        'JSONDisk under FanoutCache must not auto-generate the pickle '
        'HMAC key file at the root.'
    )
    for num in range(4):
        shard_keyfile = op.join(
            tmp_cache_dir, '%03d' % num, PICKLE_KEY_FILENAME
        )
        assert not op.exists(shard_keyfile)


def test_v5_disk_uses_pickle_class_attr():
    """V5: the ``_uses_pickle`` capability flag is True for the base
    ``Disk`` and False for ``JSONDisk``."""
    assert dc.Disk._uses_pickle is True
    assert dc.JSONDisk._uses_pickle is False


def test_v1_fanoutcache_pickling_with_explicit_key_raises(
    tmp_cache_dir, clear_env
):
    """V1: FanoutCache.__getstate__ must mirror Cache.__getstate__'s
    refusal when an explicit pickle key was provided (else pickling
    silently strips the secret and corrupts reads in the receiving
    process)."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        fc = dc.FanoutCache(
            tmp_cache_dir,
            shards=2,
            disk_pickle_key=secrets.token_bytes(32),
        )
        try:
            with pytest.raises(TypeError, match='disk_pickle_key'):
                pickle.dumps(fc)
        finally:
            fc.close()


def test_v1_fanoutcache_pickling_with_legacy_mode_raises(
    tmp_cache_dir, clear_env
):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        fc = dc.FanoutCache(
            tmp_cache_dir, shards=2, disk_pickle_key=False
        )
        try:
            with pytest.raises(TypeError, match='disk_pickle_key'):
                pickle.dumps(fc)
        finally:
            fc.close()


def test_v1_fanoutcache_pickling_with_default_succeeds(
    tmp_cache_dir, clear_env
):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(tmp_cache_dir, shards=2) as fc:
            fc['k'] = {'v': 1}
            blob = pickle.dumps(fc)
            other = pickle.loads(blob)
            try:
                assert other['k'] == {'v': 1}
            finally:
                other.close()


def test_v2_deque_pickling_with_explicit_key_raises(
    tmp_cache_dir, clear_env
):
    """V2: Deque (built on Cache) must inherit the H2 protection."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        cache = dc.Cache(tmp_cache_dir, disk_pickle_key=secrets.token_bytes(32))
        try:
            deque = dc.Deque.fromcache(cache, [{'item': 1}])
            with pytest.raises(TypeError, match='disk_pickle_key'):
                pickle.dumps(deque)
        finally:
            cache.close()


def test_v2_index_pickling_with_explicit_key_raises(
    tmp_cache_dir, clear_env
):
    """V2: Index (built on Cache) must inherit the H2 protection."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        cache = dc.Cache(tmp_cache_dir, disk_pickle_key=secrets.token_bytes(32))
        try:
            idx = dc.Index.fromcache(cache, {'k': 'v'})
            with pytest.raises(TypeError, match='disk_pickle_key'):
                pickle.dumps(idx)
        finally:
            cache.close()


def test_v2_deque_pickling_with_default_succeeds(tmp_cache_dir, clear_env):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        cache = dc.Cache(tmp_cache_dir)
        try:
            deque = dc.Deque.fromcache(cache, [{'item': 1}])
            blob = pickle.dumps(deque)
            other = pickle.loads(blob)
            assert list(other) == [{'item': 1}]
        finally:
            cache.close()


def test_v11_copy_copy_preserves_explicit_key(tmp_cache_dir, clear_env):
    """V11: ``copy.copy(cache)`` does not cross a process boundary, so
    the explicit pickle_key should be preserved (not rejected by
    __getstate__) and a working independent Cache returned."""
    import copy

    secret = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=secret) as cache:
            cache['k'] = {'v': 1}
            shallow = copy.copy(cache)
            try:
                assert shallow.directory == cache.directory
                assert shallow._disk._pickle_key_arg == secret
                assert shallow['k'] == {'v': 1}
            finally:
                shallow.close()


def test_v11_copy_deepcopy_preserves_explicit_key(tmp_cache_dir, clear_env):
    import copy

    secret = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=secret) as cache:
            cache['k'] = {'v': 1}
            deep = copy.deepcopy(cache)
            try:
                assert deep['k'] == {'v': 1}
            finally:
                deep.close()


def test_v11_copy_copy_with_default_still_works(tmp_cache_dir, clear_env):
    import copy

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            cache['k'] = {'v': 1}
            shallow = copy.copy(cache)
            try:
                assert shallow['k'] == {'v': 1}
            finally:
                shallow.close()


def test_v10_warning_mentions_bootstrap_race(tmp_cache_dir, clear_env):
    """V10: the auto-generated-key warning must explicitly mention the
    bootstrap-race risk so operators understand the threat model
    (otherwise they may assume the file-mode 0o600 key is safe in any
    multi-tenant directory)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with dc.Cache(tmp_cache_dir) as cache:
            cache[('complex',)] = {'value': 1}

    msgs = [
        w for w in caught if isinstance(w.message, dc.UnsafePickleWarning)
    ]
    assert msgs
    assert 'bootstrap race' in str(msgs[0].message).lower(), (
        'Warning should mention bootstrap race; got: %r'
        % str(msgs[0].message)
    )


def test_v12_short_key_file_raises_clear_runtimeerror(
    tmp_cache_dir, clear_env
):
    """V12: coverage for the "after N retries" RuntimeError path in
    ``_read_or_create_pickle_key_file``."""
    from diskcache import core as dc_core

    keyfile = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)
    with open(keyfile, 'wb') as fh:
        fh.write(b'short')
    with pytest.raises(RuntimeError, match='too short.*after'):
        dc_core._read_or_create_pickle_key_file(keyfile)


def test_v12_safe_filename_path_rejects_non_string(
    tmp_cache_dir, clear_env
):
    """V12: coverage for the type guard in ``_safe_filename_path``."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            with pytest.raises(ValueError, match='must be str'):
                cache._disk._safe_filename_path(123)


def test_v12_bytearray_pickle_key_accepted(tmp_cache_dir, clear_env):
    """V12: bytearray is accepted by _coerce_pickle_key but was never
    exercised before."""
    key = bytearray(secrets.token_bytes(32))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=key) as cache:
            cache['k'] = {'v': 1}
            assert cache['k'] == {'v': 1}


# -- Pass-4 round of fixes ---------------------------------------------


def test_v14_short_os_write_does_not_silently_truncate(
    tmp_cache_dir, clear_env, monkeypatch
):
    """V14: ``os.write`` may legally return a short write (signal,
    quota, ENOSPC mid-write).  Ignoring the return value lets the
    writer hold a 32-byte key in memory while the on-disk file holds
    only a prefix; readers then see "too short" forever.

    With the loop-until-full fix, a short write should either complete
    (multiple iterations) or raise OSError that triggers cleanup.
    """
    from diskcache import core as dc_core

    keyfile = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)
    orig_write = os.write
    write_count = [0]

    def short_then_full_write(fd, data):
        write_count[0] += 1
        # First call writes 8 bytes; subsequent calls write the rest.
        return orig_write(fd, data[:8])

    monkeypatch.setattr(os, 'write', short_then_full_write)
    key, _ = dc_core._read_or_create_pickle_key_file(keyfile)
    monkeypatch.setattr(os, 'write', orig_write)

    # The writer loop must have called os.write multiple times until
    # all 32 bytes were durable.
    assert write_count[0] >= 4, (
        'expected the write loop to retry; got %d calls' % write_count[0]
    )
    on_disk_len = op.getsize(keyfile)
    assert on_disk_len == len(key) == 32, (
        'on-disk key (%d bytes) must match returned key (%d bytes)'
        % (on_disk_len, len(key))
    )


def test_v14_zero_return_from_os_write_triggers_cleanup(
    tmp_cache_dir, clear_env, monkeypatch
):
    """V14: a pathological 0-byte write loops forever in the naive
    implementation; the fix raises OSError after the first such call
    and the finally cleans up the file."""
    from diskcache import core as dc_core

    keyfile = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)

    def zero_write(fd, data):
        return 0

    monkeypatch.setattr(os, 'write', zero_write)
    with pytest.raises(OSError):
        dc_core._read_or_create_pickle_key_file(keyfile)
    assert not op.exists(keyfile)


def test_v17_keyboard_interrupt_during_fsync_keeps_durable_key(
    tmp_cache_dir, clear_env, monkeypatch
):
    """V17: once ``os.write`` has fully landed the key on disk,
    concurrent readers can already see it.  A KeyboardInterrupt
    during the subsequent fsync must NOT unlink the file -- doing so
    would strand readers using a key that no longer exists on disk."""
    from diskcache import core as dc_core

    keyfile = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)

    def kbd_during_fsync(fd):
        raise KeyboardInterrupt('simulated Ctrl+C during fsync')

    monkeypatch.setattr(os, 'fsync', kbd_during_fsync)
    with pytest.raises(KeyboardInterrupt):
        dc_core._read_or_create_pickle_key_file(keyfile)
    monkeypatch.undo()

    assert op.exists(keyfile), (
        'fsync interrupt after successful os.write must NOT unlink '
        'the key (the bytes are already visible to readers).'
    )
    assert op.getsize(keyfile) == 32


def test_v18_oserror_on_realpath_propagates_when_not_path_failure(
    tmp_cache_dir, clear_env, monkeypatch
):
    """V18: PermissionError / TimeoutError from realpath are real OS
    errors, not tampering signals.  They must propagate unchanged."""
    from diskcache import core as dc_core

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            disk = cache._disk

    def perm_error(*args, **kwargs):
        raise PermissionError(13, 'Permission denied (simulated)')

    monkeypatch.setattr(dc_core.op, 'realpath', perm_error)
    with pytest.raises(PermissionError):
        disk._safe_filename_path('ab/cd.val')


def test_v15_copy_preserves_resolved_key_across_env_change(
    tmp_cache_dir, clear_env, monkeypatch
):
    """V15: if the original Cache resolved its key from the env var
    or in-dir file, ``copy.copy`` must propagate the resolved bytes
    so an intervening env change does not produce a copy that uses a
    different key."""
    import copy

    monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            cache[('complex', 'key')] = {'v': 1}
            # Change the env var BEFORE copying
            monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
            shallow = copy.copy(cache)
            try:
                # The copy must read the same value that the original
                # wrote (resolved key was preserved).
                assert shallow[('complex', 'key')] == {'v': 1}
            finally:
                shallow.close()


def test_v16_fanout_child_cache_inherits_pickle_key(
    tmp_cache_dir, clear_env
):
    """V16: ``FanoutCache.cache(name)`` must forward
    ``disk_pickle_key`` to the child Cache.  Otherwise the child
    auto-generates a different key and its data is unreadable when
    the user re-opens with the parent's key."""
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(
            tmp_cache_dir, shards=2, disk_pickle_key=key
        ) as fc:
            child = fc.cache('child')
            assert child._disk._pickle_key_arg == key
            child[('complex',)] = {'v': 1}
            # No per-child key file should exist since the key was
            # inherited.
            child_dir = op.join(tmp_cache_dir, 'cache', 'child')
            assert not op.exists(op.join(child_dir, PICKLE_KEY_FILENAME))


def test_v16_fanout_child_deque_inherits_pickle_key(
    tmp_cache_dir, clear_env
):
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(
            tmp_cache_dir, shards=2, disk_pickle_key=key
        ) as fc:
            d = fc.deque('mydeque')
            assert d._cache._disk._pickle_key_arg == key
            d.append({'v': 1})
            assert d.pop() == {'v': 1}


def test_v16_fanout_child_index_inherits_pickle_key(
    tmp_cache_dir, clear_env
):
    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(
            tmp_cache_dir, shards=2, disk_pickle_key=key
        ) as fc:
            idx = fc.index('myindex')
            assert idx._cache._disk._pickle_key_arg == key
            idx['k'] = {'v': 1}
            assert idx['k'] == {'v': 1}


def test_v19_fanoutcache_copy_preserves_explicit_key(
    tmp_cache_dir, clear_env
):
    """V19: same-process ``copy.copy(fanout)`` must preserve an
    explicit key just like Cache does."""
    import copy

    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(
            tmp_cache_dir, shards=2, disk_pickle_key=key
        ) as fc:
            fc[('complex',)] = {'v': 1}
            shallow = copy.copy(fc)
            try:
                assert shallow[('complex',)] == {'v': 1}
            finally:
                shallow.close()


def test_v19_deque_copy_preserves_explicit_key(tmp_cache_dir, clear_env):
    import copy

    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        cache = dc.Cache(tmp_cache_dir, disk_pickle_key=key)
        try:
            deque = dc.Deque.fromcache(cache, [{'item': 1}, {'item': 2}])
            shallow = copy.copy(deque)
            try:
                assert list(shallow) == [{'item': 1}, {'item': 2}]
            finally:
                shallow._cache.close()
        finally:
            cache.close()


def test_v19_index_copy_preserves_explicit_key(tmp_cache_dir, clear_env):
    import copy

    key = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        cache = dc.Cache(tmp_cache_dir, disk_pickle_key=key)
        try:
            idx = dc.Index.fromcache(cache, {'k': {'v': 1}})
            shallow = copy.copy(idx)
            try:
                assert shallow['k'] == {'v': 1}
            finally:
                shallow._cache.close()
        finally:
            cache.close()


def test_v21_legacy_error_mentions_disk_pickle_key(
    tmp_cache_dir, clear_env
):
    """V21: the error must point users to ``disk_pickle_key=False``
    (the kwarg on Cache / FanoutCache / Django OPTIONS), not
    ``pickle_key=False`` (only valid on the Disk constructor)."""
    # Write raw legacy pickle directly
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir, disk_pickle_key=False) as cache:
            cache['k'] = {'legacy': True}

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(
            tmp_cache_dir, disk_pickle_key=secrets.token_bytes(32)
        ) as cache:
            with pytest.raises(pickle.UnpicklingError) as exc_info:
                cache['k']
    msg = str(exc_info.value)
    assert 'disk_pickle_key' in msg, (
        'Error must reference the public kwarg name disk_pickle_key '
        '(not the Disk-only pickle_key); got: %r' % msg
    )


# -- Pass-5: O1 default-mode copies survive env changes ----------------


def test_o1_default_mode_cache_copy_survives_env_change(
    tmp_cache_dir, monkeypatch
):
    """O1 (Cache): copy.copy(cache) in default mode must keep using the
    original key even if DISKCACHE_PICKLE_KEY is replaced before the
    copy is constructed."""
    import copy

    monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            cache['k'] = {'v': 1}
            assert cache['k'] == {'v': 1}  # force lazy resolution
            monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
            shallow = copy.copy(cache)
            try:
                assert shallow['k'] == {'v': 1}
            finally:
                shallow.close()


def test_o1_default_mode_fanout_copy_survives_env_change(
    tmp_cache_dir, monkeypatch
):
    """O1 (FanoutCache): copy.copy(fc) must keep using the original key
    even if DISKCACHE_PICKLE_KEY is replaced before the copy is made.
    Without the inherited-key propagation the copy would re-resolve
    from the (now different) env var and silently fail HMAC."""
    import copy

    monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(tmp_cache_dir, shards=4) as fc:
            fc['k'] = {'v': 1}
            assert fc['k'] == {'v': 1}
            monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
            shallow = copy.copy(fc)
            try:
                assert shallow['k'] == {'v': 1}
            finally:
                shallow.close()


def test_o1_default_mode_deque_copy_survives_env_change(
    tmp_cache_dir, monkeypatch
):
    """O1 (Deque): copy.copy(deque) must keep the original key."""
    import copy

    monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        deque = dc.Deque(directory=tmp_cache_dir)
        try:
            deque.append({'v': 1})
            assert list(deque) == [{'v': 1}]
            monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
            shallow = copy.copy(deque)
            try:
                assert list(shallow) == [{'v': 1}]
            finally:
                shallow._cache.close()
        finally:
            deque._cache.close()


def test_o1_default_mode_index_copy_survives_env_change(
    tmp_cache_dir, monkeypatch
):
    """O1 (Index): copy.copy(index) must keep the original key."""
    import copy

    monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        idx = dc.Index(tmp_cache_dir)
        try:
            idx['k'] = {'v': 1}
            assert idx['k'] == {'v': 1}
            monkeypatch.setenv(PICKLE_KEY_ENV, secrets.token_bytes(32).hex())
            shallow = copy.copy(idx)
            try:
                assert shallow['k'] == {'v': 1}
            finally:
                shallow._cache.close()
        finally:
            idx._cache.close()


# -- Pass-5: O2 FanoutCache children get-or-create lock ----------------


def test_o2_fanout_concurrent_cache_no_duplicate(
    tmp_cache_dir, clear_env, monkeypatch
):
    """O2: two threads calling fc.cache('foo') simultaneously must get
    the SAME instance.  Without the lock, both can miss the dict, both
    construct, the second store overwrites the first, and the first
    caller is left with an orphan Cache (open SQLite handle, no
    references in fc._caches).

    This version is deterministic: we monkey-patch ``Cache.__init__``
    with a wrapper that sleeps before returning, so both threads enter
    the get-or-create critical section while the first construction
    is still in flight.  Without the lock the second thread observes
    an empty ``self._caches`` and constructs a duplicate.
    """
    import threading
    import time

    real_init = dc.Cache.__init__
    construct_count = {'n': 0}
    construct_lock = threading.Lock()

    def slow_init(self, *args, **kwargs):
        with construct_lock:
            construct_count['n'] += 1
            n = construct_count['n']
        real_init(self, *args, **kwargs)
        # Only slow down child cache construction (under the
        # FanoutCache 'cache' subdirectory), not the FanoutCache's
        # own shards.  Sleep races the second caller into the
        # critical section.
        if n > 0 and 'cache' in str(self.directory).split(os.sep):
            time.sleep(0.2)

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(tmp_cache_dir, shards=2) as fc:
            # Patch only after FanoutCache is fully constructed so
            # shard inits aren't slowed.
            monkeypatch.setattr(dc.Cache, '__init__', slow_init)

            results = []
            results_lock = threading.Lock()

            def grab():
                child = fc.cache('shared')
                with results_lock:
                    results.append(child)

            threads = [threading.Thread(target=grab) for _ in range(8)]
            t0 = time.time()
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            elapsed = time.time() - t0

            first = results[0]
            assert all(r is first for r in results), (
                'All threads must see the same cached child instance'
            )
            assert len(fc._caches) == 1
            # If the lock works, all threads serialize on the first
            # construction (~0.2s); a duplicate construction would
            # double the time.  Allow generous slack.
            assert elapsed < 1.0, (
                'O2: child construction appears to have run more '
                'than once concurrently (elapsed=%.2fs)' % elapsed
            )


# -- Pass-5: O3 close() closes cached children -------------------------


def test_o3_fanout_close_closes_children(tmp_cache_dir, clear_env):
    """O3: ``fc.close()`` must close cached child Cache/Deque/Index
    instances.  Otherwise long-lived references leak SQLite handles.

    Behavioral check: after ``fc.close()`` we must be able to open a
    fresh sqlite3 connection to each child's database file in
    exclusive locking mode.  If close() failed to release the
    underlying handle (e.g. on Windows where the file is held by the
    OS while the connection is open), this will fail.  We also assert
    the parent's child dicts are cleared so the FanoutCache cannot
    silently keep handing out post-close children.
    """
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        fc = dc.FanoutCache(tmp_cache_dir, shards=2)
        child_cache = fc.cache('child_cache')
        child_deque = fc.deque('child_deque')
        child_index = fc.index('child_index')
        # Force connection creation in this thread.
        child_cache['k'] = 1
        child_deque.append('x')
        child_index['a'] = 1

        child_cache_db = op.join(child_cache.directory, 'cache.db')
        child_deque_db = op.join(child_deque._cache.directory, 'cache.db')
        child_index_db = op.join(child_index._cache.directory, 'cache.db')
        assert op.isfile(child_cache_db)
        assert op.isfile(child_deque_db)
        assert op.isfile(child_index_db)

        fc.close()

        # Behavioral verification: each child's db must be openable
        # by a fresh exclusive-locking sqlite connection.  If the
        # original connection is still held, the BEGIN EXCLUSIVE will
        # raise OperationalError (database is locked).
        for db_path in (child_cache_db, child_deque_db, child_index_db):
            con = sqlite3.connect(db_path, timeout=0.5)
            try:
                con.execute('BEGIN EXCLUSIVE')
                con.execute('COMMIT')
            finally:
                con.close()

        # The dicts must be cleared so the parent can be safely
        # reopened later without leaking the old children.
        assert fc._caches == {}
        assert fc._deques == {}
        assert fc._indexes == {}


# -- Pass-5: O4 child Cache pickling depends on key source -------------


def test_o4_default_mode_child_cache_pickleable(tmp_cache_dir, clear_env):
    """O4: in default mode the FanoutCache and its child Cache must
    be pickleable -- the inherited key isn't a user-supplied secret."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(tmp_cache_dir, shards=2) as fc:
            child = fc.cache('foo')
            # The child must NOT have an explicit _pickle_key_arg.
            from diskcache.core import _PICKLE_KEY_UNSET
            assert child._disk._pickle_key_arg is _PICKLE_KEY_UNSET
            # And it must be pickleable.
            blob = pickle.dumps(child)
            restored = pickle.loads(blob)
            try:
                assert restored.directory == child.directory
            finally:
                restored.close()


def test_o4_explicit_mode_child_cache_unpickleable(
    tmp_cache_dir, clear_env
):
    """O4: when the user passes an explicit ``disk_pickle_key`` to
    FanoutCache, the child Cache inherits that explicit key and
    pickling must be refused (mirrors the parent's posture)."""
    secret = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(
            tmp_cache_dir, shards=2, disk_pickle_key=secret
        ) as fc:
            child = fc.cache('foo')
            with pytest.raises(TypeError, match='disk_pickle_key'):
                pickle.dumps(child)


# -- Pass-5: Y1 KeyboardInterrupt after full write preserves key file --


def test_y1_keyboard_interrupt_after_full_write_preserves_file(
    tmp_cache_dir, clear_env, monkeypatch
):
    """Y1: if KeyboardInterrupt fires AFTER os.write has deposited the
    full key in the kernel but BEFORE ``write_succeeded = True`` runs,
    the finally block must NOT unlink the file -- concurrent readers
    can already see that key bytes."""
    from diskcache import core as dc_core

    real_write = os.write

    def evil_write(fd, data):
        n = real_write(fd, data)
        # Simulate an async exception firing right after os.write
        # returned the full count -- before the assignment below.
        raise KeyboardInterrupt('simulated SIGINT')

    monkeypatch.setattr(dc_core.os, 'write', evil_write)
    keyfile = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)
    with pytest.raises(KeyboardInterrupt):
        dc_core._read_or_create_pickle_key_file(keyfile)
    # Restore real os.write for the assertion phase.
    monkeypatch.setattr(dc_core.os, 'write', real_write)

    # File must still exist with a valid key (>= MIN_LEN bytes).
    assert op.exists(keyfile), (
        'Y1: file was unlinked even though os.write completed -- '
        'concurrent readers may already hold this key.'
    )
    with open(keyfile, 'rb') as fh:
        on_disk = fh.read()
    assert len(on_disk) >= dc_core.PICKLE_KEY_MIN_LEN


# -- Pass-5: Y2 ELOOP translates to ValueError -------------------------


@pytest.mark.skipif(
    os.name == 'nt', reason='symlink loops require admin on Windows'
)
def test_y2_eloop_translates_to_value_error(tmp_cache_dir, clear_env):
    """Y2: a symlink loop inside the cache directory (errno ELOOP)
    must surface as ValueError from _safe_filename_path, signalling
    a tampered cache.db row -- not as an opaque OSError."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            disk = cache._disk
            # Create a symlink loop a -> b -> a inside the cache dir.
            a = op.join(tmp_cache_dir, 'loop_a')
            b = op.join(tmp_cache_dir, 'loop_b')
            try:
                os.symlink(b, a)
                os.symlink(a, b)
            except (OSError, NotImplementedError) as exc:
                pytest.skip('cannot create symlink loop: %s' % exc)
            with pytest.raises(ValueError, match='cache.db may be tampered'):
                disk._safe_filename_path('loop_a')


# -- Pass-5: Y3 error wording uses the public kwarg name --------------


def test_y3_error_message_uses_disk_pickle_key_kwarg_name(
    tmp_cache_dir, clear_env
):
    """Y3: ``Cache(td, disk_pickle_key='not-hex')`` must raise with
    the public kwarg name (``disk_pickle_key``) in the error so users
    aren't confused by the underlying ``Disk(pickle_key=...)`` kwarg
    they never typed."""
    with pytest.raises(ValueError) as exc_info:
        dc.Cache(tmp_cache_dir, disk_pickle_key='not-hex')
    msg = str(exc_info.value)
    assert 'disk_pickle_key' in msg, (
        'error must mention the public kwarg disk_pickle_key, got: %r'
        % msg
    )

    # FanoutCache should also use the public name.
    with pytest.raises(ValueError) as exc_info2:
        dc.FanoutCache(tmp_cache_dir, disk_pickle_key='not-hex')
    msg2 = str(exc_info2.value)
    assert 'disk_pickle_key' in msg2, (
        'FanoutCache error must mention disk_pickle_key, got: %r' % msg2
    )



# -- Pass-6: L1 child cache key recoverability after pickle ------------


def test_l1_pickled_child_cache_recovers_data_in_receiver(
    tmp_cache_dir, clear_env
):
    """L1: pickling a child Cache obtained from FanoutCache.cache(name)
    must round-trip -- the receiver must be able to recover the HMAC
    key from the child's directory and read the data."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(tmp_cache_dir, shards=2) as fc:
            child = fc.cache('mychild')
            child[('complex', 'key')] = {'value': 42}
            blob = pickle.dumps(child)
            child_dir = child.directory
        # Simulate "receiving process": brand-new Cache instance from
        # the same directory, no env var.
        with dc.Cache(child_dir) as rcv:
            assert rcv[('complex', 'key')] == {'value': 42}
        # Also test pickle round-trip.
        rcv2 = pickle.loads(blob)
        try:
            assert rcv2[('complex', 'key')] == {'value': 42}
        finally:
            rcv2.close()


def test_l1_inherited_key_file_written_atomically_in_child_dir(
    tmp_cache_dir, clear_env
):
    """L1: the inherited key must be persisted into the child
    directory's ``.diskcache_pickle_key`` so default resolution in a
    receiving process recovers the same key."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(tmp_cache_dir, shards=2) as fc:
            child = fc.cache('mychild')
            child_key_path = op.join(child.directory, PICKLE_KEY_FILENAME)
            assert op.isfile(child_key_path)
            with open(child_key_path, 'rb') as fh:
                child_key = fh.read()
            parent_key_path = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)
            with open(parent_key_path, 'rb') as fh:
                parent_key = fh.read()
            assert child_key == parent_key


def test_l1_explicit_key_does_NOT_write_keyfile_into_child_dir(
    tmp_cache_dir, clear_env
):
    """L1 negative: when the user passes an explicit
    ``disk_pickle_key`` the secret must NOT be persisted to disk in
    any child directory.  Only the implicit (inherited from default
    resolution) path triggers the L1 keyfile-write."""
    secret = secrets.token_bytes(32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(
            tmp_cache_dir, shards=2, disk_pickle_key=secret
        ) as fc:
            child = fc.cache('mychild')
            assert not op.isfile(
                op.join(child.directory, PICKLE_KEY_FILENAME)
            )
            # Parent dir also should not have one.
            assert not op.isfile(
                op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)
            )


def test_l1_legacy_mode_does_NOT_write_keyfile_into_child_dir(
    tmp_cache_dir, clear_env
):
    """L1 negative: legacy mode (disk_pickle_key=False) must not
    create a keyfile anywhere -- there is no key to persist."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.FanoutCache(
            tmp_cache_dir, shards=2, disk_pickle_key=False
        ) as fc:
            child = fc.cache('mychild')
            assert not op.isfile(
                op.join(child.directory, PICKLE_KEY_FILENAME)
            )


# -- Pass-6: C1 FanoutCache.close() fences subsequent use --------------


def test_c1_fanoutcache_use_after_close_raises(tmp_cache_dir, clear_env):
    """C1: after fc.close(), creating new children via cache()/
    deque()/index() must raise RuntimeError."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        fc = dc.FanoutCache(tmp_cache_dir, shards=2)
        fc.cache('existing')  # populate to exercise close() pathways
        fc.close()
        with pytest.raises(RuntimeError, match='closed'):
            fc.cache('new')
        with pytest.raises(RuntimeError, match='closed'):
            fc.deque('new')
        with pytest.raises(RuntimeError, match='closed'):
            fc.index('new')


def test_c1_fanoutcache_close_idempotent(tmp_cache_dir, clear_env):
    """C1: calling close() twice must not raise."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        fc = dc.FanoutCache(tmp_cache_dir, shards=2)
        fc.close()
        fc.close()  # second close should not raise


# -- Pass-6: L2 size-based finally cleanup -----------------------------


def test_y1_finally_size_based_cleanup_partial(
    tmp_cache_dir, clear_env, monkeypatch
):
    """L2: if os.write only delivers a short prefix of the key and
    then raises OSError, the finally block must unlink the partial
    file (file_size < len(new_key))."""
    from diskcache import core as dc_core

    real_write = os.write

    def short_then_fail(fd, data):
        # Write only 8 bytes and report failure thereafter.
        real_write(fd, data[:8])
        raise OSError(28, 'simulated short write + failure')

    monkeypatch.setattr(dc_core.os, 'write', short_then_fail)
    keyfile = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)
    with pytest.raises(OSError):
        dc_core._read_or_create_pickle_key_file(keyfile)
    # Restore for cleanup safety.
    monkeypatch.setattr(dc_core.os, 'write', real_write)
    assert not op.exists(keyfile), (
        'L2: partial file (8 bytes < 32) must be unlinked'
    )


def test_y1_finally_size_based_cleanup_complete(
    tmp_cache_dir, clear_env, monkeypatch
):
    """L2: if os.write delivers the full key but an exception fires
    before write_succeeded=True, the finally block must preserve the
    file (file_size == len(new_key) and content matches)."""
    from diskcache import core as dc_core

    real_write = os.write

    def full_then_fail(fd, data):
        n = real_write(fd, data)
        # Simulate KeyboardInterrupt firing AFTER full bytes deposited
        # but BEFORE the write_succeeded=True assignment runs.
        raise KeyboardInterrupt('simulated SIGINT post-write')

    monkeypatch.setattr(dc_core.os, 'write', full_then_fail)
    keyfile = op.join(tmp_cache_dir, PICKLE_KEY_FILENAME)
    with pytest.raises(KeyboardInterrupt):
        dc_core._read_or_create_pickle_key_file(keyfile)
    monkeypatch.setattr(dc_core.os, 'write', real_write)
    assert op.exists(keyfile), (
        'L2: complete file (32 bytes, content matches) must be preserved'
    )
    with open(keyfile, 'rb') as fh:
        assert len(fh.read()) >= dc_core.PICKLE_KEY_MIN_LEN


# -- Pass-6: Y2 cross-platform ELOOP via monkeypatch -------------------


def test_y2_eloop_translates_to_value_error_via_monkeypatch(
    tmp_cache_dir, clear_env, monkeypatch
):
    """Y2 (cross-platform): monkey-patch op.realpath to raise
    OSError(ELOOP) so the translation to ValueError is verified
    without needing real symlinks (which require admin on Windows)."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', dc.UnsafePickleWarning)
        with dc.Cache(tmp_cache_dir) as cache:
            disk = cache._disk
            from diskcache import core as dc_core

            real_realpath = dc_core.op.realpath

            def loop_realpath(path, *args, **kwargs):
                # Only fake the loop for our specific filename so the
                # cache directory's own realpath caching still works.
                if 'loop_target' in str(path):
                    raise OSError(
                        errno.ELOOP, 'Too many symbolic links'
                    )
                return real_realpath(path, *args, **kwargs)

            monkeypatch.setattr(
                dc_core.op, 'realpath', loop_realpath
            )
            with pytest.raises(
                ValueError, match='cache.db may be tampered'
            ):
                disk._safe_filename_path('loop_target')
