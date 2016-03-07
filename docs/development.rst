DiskCache Development
=====================

:doc:`DiskCache <index>` development is lead by Grant Jenks
<contact@grantjenks.com>.

Collaborators Welcome
---------------------

#. Search issues or open a new issue to start a discussion around a bug.
#. Fork the `GitHub repository`_ and make your changes in a new branch.
#. Write a test which shows the bug was fixed.
#. Send a pull request and message the development lead until its merged and
   published.

.. _`GitHub repository`: https://github.com/grantjenks/python-diskcache

Requests for Contributions
--------------------------

#. Command-line interface. Operations to support: get, set, store, delete,
   expire, evict, clear, path, check, stats.
#. Atomic increment and decrement methods.
#. Django admin interface for cache stats and interaction.
#. Cache stampede barrier (source prototype in repo).
#. API Compatibility

   #. `lru_cache-like decorator <https://docs.python.org/3/library/functools.html#functools.lru_cache>`_
   #. `Shelf interface <https://docs.python.org/2/library/shelve.html>`_
   #. `DBM interface <https://docs.python.org/2/library/anydbm.html>`_

#. Backend Compatibility

   #. `Flask-Cache <https://pythonhosted.org/Flask-Cache/>`_
   #. `Beaker <http://beaker.readthedocs.org/en/latest/>`_
   #. `dogpile.cache <http://dogpilecache.readthedocs.org/en/latest/>`_

Get the Code
------------

:doc:`DiskCache <index>` is actively developed in a `GitHub repository`_.

You can either clone the public repository::

    $ git clone git://github.com/grantjenks/python-diskcache.git

Download the `tarball <https://github.com/grantjenks/python-diskcache/tarball/master>`_::

    $ curl -OL https://github.com/grantjenks/python-diskcache/tarball/master

Or, download the `zipball <https://github.com/grantjenks/python-diskcache/zipball/master>`_::

    $ curl -OL https://github.com/grantjenks/python-diskcache/zipball/master

Installing Dependencies
-----------------------

Install development dependencies with `pip <http://www.pip-installer.org/>`_::

    $ pip install -r requirements.txt

All packages for running tests will be installed.

Additional packages like ``pylibmc`` and ``redis`` along with their server
counterparts are necessary for some benchmarks.

Testing
-------

:doc:`DiskCache <index>` currently tests against four versions of Python:

* CPython 2.7
* CPython 3.4
* CPython 3.5
* PyPy2

Testing uses `tox <https://pypi.python.org/pypi/tox>`_. If you don't want to
install all the development requirements, then, after downloading, you can
simply run::

    $ python setup.py test

The test argument to setup.py will download a minimal testing infrastructure
and run the tests.

::

   $ tox
   GLOB sdist-make: python-diskcache/setup.py
   py27 inst-nodeps: python-diskcache/.tox/dist/diskcache-0.9.0.zip
   py27 runtests: PYTHONHASHSEED='3527394681'
   py27 runtests: commands[0] | nosetests
   .........................................................................
   ----------------------------------------------------------------------
   Ran 98 tests in 29.404s

   OK
   py34 inst-nodeps: python-diskcache/.tox/dist/diskcache-0.9.0.zip
   py34 runtests: PYTHONHASHSEED='3527394681'
   py34 runtests: commands[0] | nosetests
   .........................................................................
   ----------------------------------------------------------------------
   Ran 98 tests in 22.841s

   OK
   py35 inst-nodeps: python-diskcache/.tox/dist/diskcache-0.9.0.zip
   py35 runtests: PYTHONHASHSEED='3527394681'
   py35 runtests: commands[0] | nosetests
   .........................................................................
   ----------------------------------------------------------------------
   Ran 98 tests in 23.803s

   OK
   ____________________ summary ____________________
     py27: commands succeeded
     py34: commands succeeded
     py35: commands succeeded
     congratulations :)

Coverage testing uses `nose <https://nose.readthedocs.org>`_:

::

   $ nosetests --cover-erase --with-coverage --cover-package diskcache
   .........................................................................
   Name                       Stmts   Miss  Cover   Missing
   --------------------------------------------------------
   diskcache.py                  13      2    85%   9-11
   diskcache/core.py            442      4    99%   22-25
   diskcache/djangocache.py      43      0   100%
   diskcache/fanout.py           66      0   100%
   --------------------------------------------------------
   TOTAL                        564      6    99%
   ----------------------------------------------------------------------
   Ran 98 tests in 28.766s

   OK

It's normal not to see 100% coverage. Some code is specific to the Python
runtime.

Stress testing is also based on nose but can be run independently as a
module. Stress tests are kept in the tests directory and prefixed with
``stress_test_``. Stress tests accept many arguments. Read the help for
details.

::

   $ python -m tests.stress_test_core --help
   usage: stress_test_core.py [-h] [-n OPERATIONS] [-g GET_AVERAGE]
                              [-k KEY_COUNT] [-d DEL_CHANCE] [-w WARMUP]
                              [-e EXPIRE] [-t THREADS] [-p PROCESSES] [-s SEED]
                              [--no-create] [--no-delete] [-v EVICTION_POLICY]

   optional arguments:
     -h, --help            show this help message and exit
     -n OPERATIONS, --operations OPERATIONS
                           Number of operations to perform (default: 10000)
     -g GET_AVERAGE, --get-average GET_AVERAGE
                           Expected value of exponential variate used for GET
                           count (default: 100)
     -k KEY_COUNT, --key-count KEY_COUNT
                           Number of unique keys (default: 10)
     -d DEL_CHANCE, --del-chance DEL_CHANCE
                           Likelihood of a key deletion (default: 0.1)
     -w WARMUP, --warmup WARMUP
                           Number of warmup operations before timings (default:
                           10)
     -e EXPIRE, --expire EXPIRE
                           Number of seconds before key expires (default: None)
     -t THREADS, --threads THREADS
                           Number of threads to start in each process (default:
                           1)
     -p PROCESSES, --processes PROCESSES
                           Number of processes to start (default: 1)
     -s SEED, --seed SEED  Random seed (default: 0)
     --no-create           Do not create operations data (default: True)
     --no-delete           Do not delete operations data (default: True)
     -v EVICTION_POLICY, --eviction-policy EVICTION_POLICY

If stress exits normally then it worked successfully. Some stress is run by tox
and nose but the iteration count is limited. More rigorous testing requires
increasing the iteration count to millions. At that level, it's best to just
let it run overnight. Stress testing will stop at the first failure.

Running Benchmarks
------------------

Running and plotting benchmarks is a two step process. Each is a Python script
in the tests directory. Benchmark scripts are prefixed with ``benchmark_``. For
example:

::

    $ python tests/benchmark_core.py --help
    usage: benchmark_core.py [-h] [-p PROCESSES] [-n OPERATIONS] [-r RANGE]
                             [-w WARMUP]

    optional arguments:
      -h, --help            show this help message and exit
      -p PROCESSES, --processes PROCESSES
                            Number of processes to start (default: 8)
      -n OPERATIONS, --operations OPERATIONS
                            Number of operations to perform (default: 100000)
      -r RANGE, --range RANGE
                            Range of keys (default: 100)
      -w WARMUP, --warmup WARMUP
                            Number of warmup operations before timings (default:
                            1000)

Benchmark output is stored in text files prefixed with ``timings_`` in the
`tests` directory. Plotting the benchmarks is done by passing the timings file
as an argument to ``plot.py``.
