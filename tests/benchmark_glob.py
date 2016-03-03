"Benchmark glob.glob1 as used by django.core.cache.backends.filebased."

from __future__ import print_function

import os
import os.path as op
import shutil
import timeit

from utils import secs

shutil.rmtree('tmp', ignore_errors=True)

os.mkdir('tmp')

size = 12
cols = ('Count', 'Time')
template = ' '.join(['%' + str(size) + 's'] * len(cols))

print()
print(' '.join(['=' * size] * len(cols)))
print('Timings for glob.glob1')
print('-'.join(['-' * size] * len(cols)))
print(template % ('Count', 'Time'))
print(' '.join(['=' * size] * len(cols)))

for count in [10 ** exp for exp in range(6)]:
    for value in range(count):
        with open(op.join('tmp', '%s.tmp' % value), 'wb') as writer:
            pass
        
    delta = timeit.timeit(
        stmt="glob.glob1('tmp', '*.tmp')",
        setup='import glob',
        number=100
    )

    print(template % (count, secs(delta)))

print(' '.join(['=' * size] * len(cols)))

shutil.rmtree('tmp', ignore_errors=True)
