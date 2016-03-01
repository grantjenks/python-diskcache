"Benchmark glob.glob1 as used by django.core.cache.backends.filebased."

from __future__ import print_function

import os
import os.path as op
import shutil
import timeit

shutil.rmtree('tmp', ignore_errors=True)

os.mkdir('tmp')

for count in [10 ** exp for exp in range(6)]:
    for value in range(count):
        with open(op.join('tmp', '%s.tmp' % value), 'wb') as writer:
            pass
        
    delta = timeit.timeit(stmt="glob.glob1('tmp', '*.tmp')", setup='import glob', number=100)

    print('Count %6s Time %.3f' % (count, delta))

shutil.rmtree('tmp', ignore_errors=True)
