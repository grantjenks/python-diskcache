"""Benchmark for Issue #109

"""

import time

import diskcache as dc


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--cache-dir', default='/tmp/test')
    parser.add_argument('--iterations', type=int, default=100)
    parser.add_argument('--sleep', type=float, default=0.1)
    parser.add_argument('--size', type=int, default=25)
    args = parser.parse_args()

    data = dc.FanoutCache(args.cache_dir)
    delays = []
    values = {str(num): num for num in range(args.size)}
    iterations = args.iterations

    for i in range(args.iterations):
        print(f'Iteration {i + 1}/{iterations}', end='\r')
        time.sleep(args.sleep)
        for key, value in values.items():
            start = time.monotonic()
            data[key] = value
            stop = time.monotonic()
            diff = stop - start
            delays.append(diff)

    # Discard warmup delays, first two iterations.
    del delays[: (len(values) * 2)]

    # Convert seconds to microseconds.
    delays = sorted(delay * 1e6 for delay in delays)

    # Display performance.
    print()
    print(f'Total #:  {len(delays)}')
    print(f'Min delay (us): {delays[0]:>8.3f}')
    print(f'50th %ile (us): {delays[int(len(delays) * 0.50)]:>8.3f}')
    print(f'90th %ile (us): {delays[int(len(delays) * 0.90)]:>8.3f}')
    print(f'99th %ile (us): {delays[int(len(delays) * 0.99)]:>8.3f}')
    print(f'Max delay (us): {delays[-1]:>8.3f}')


if __name__ == '__main__':
    main()
