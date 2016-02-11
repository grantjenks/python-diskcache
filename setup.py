from __future__ import print_function

from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand
import subprocess as sp
import sys

import diskcache

if sys.argv[-1] == 'release':
    def run(command):
        print('setup.py$', command)
        sp.check_call(command.split())

    version = b'v%s' % diskcache.__version__

    run('git checkout master')

    if version in sp.check_output(['git', 'tag']):
        print('Error: Version already tagged.')
        sys.exit(1)

    if sp.check_output(['git', 'status', '--porcelain']):
        print('Error: Commit files in working directory before release.')
        run('git status')
        sys.exit(1)

    run('git pull')
    run('pylint diskcache')
    run('tox')
    run('git tag -a %s -m %s' % (version, version))
    run('git push')
    run('git push --tags')
    run('python setup.py sdist upload')

    # Update docs
    # cd docs && make html
    # Upload docs/_build/html to gj server

    sys.exit()

class Tox(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True
    def run_tests(self):
        import tox
        errno = tox.cmdline(self.test_args)
        sys.exit(errno)

with open('README.rst') as reader:
    readme = reader.read()

with open('LICENSE') as reader:
    license = reader.read()

setup(
    name='diskcache',
    version=diskcache.__version__,
    description='Disk and file-based cache',
    long_description=readme,
    author='Grant Jenks',
    author_email='contact@grantjenks.com',
    url='http://www.grantjenks.com/docs/diskcache/',
    packages=find_packages(exclude=('tests', 'docs')),
    package_data={'': ['LICENSE', 'README.rst']},
    tests_require=['tox'],
    cmdclass={'test': Tox},
    license=license,
    classifiers=(
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ),
)
