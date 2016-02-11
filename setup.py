from __future__ import print_function

import ftplib
import getpass
import os
import os.path as op
from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand
import shutil
import subprocess as sp
import sys

import diskcache

if sys.argv[-1] == 'release':
    def run(command):
        print('setup.py$', command)
        sp.check_call(command.split())

    version = b'v%s' % diskcache.__version__

    shutil.rmtree(op.join('docs', '_build'), ignore_errors=True)

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
    run('python setup.py sdist')
    run('twine upload dist/diskcache-%s.tar.gz' % diskcache.__version__)

    root = os.getcwd()
    os.chdir(op.join(root, 'docs'))

    print('setup.py$ building docs')

    run('make clean')
    run('make html')

    print('setup.py$ uploading docs')

    ftps = ftplib.FTP_TLS(
        'grantjenks.com',
        user='grant',
        passwd=getpass.getpass()
    )
    ftps.prot_p()

    base = '/domains/grantjenks.com/docs/diskcache'

    try:
        ftps.mkd(base)
    except ftplib.error_perm:
        pass

    os.chdir(op.join('_build', 'html'))

    for root, dirs, files in os.walk('.'):
        for directory in dirs:
            print('Creating directory', op.join(root, directory))
            try:
                ftps.mkd('/'.join([base, root, directory]))
            except ftplib.error_perm:
                pass

        for filename in files:
            print('Uploading file', op.join(root, filename))
            with open(op.join(root, filename), 'rb') as reader:
                command = 'STOR %s/%s/%s' % (base, root, filename)
                ftps.storbinary(command, reader)

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
    license='Apache 2.0',
    install_requires=[],
    classifiers=(
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
    ),
)
