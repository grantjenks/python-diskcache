"Plot benchmark docs."

import argparse
import collections as co
import matplotlib.pyplot as plt
import re
import sys

blocks = re.compile(' '.join(['=' * 9] * 8))
dashes = re.compile('^-{79}$')
title = re.compile('^Timings for (.*)$')
row = re.compile(' '.join(['(.{9})'] * 7) + ' (.{8,9})')

parser = argparse.ArgumentParser()

parser.add_argument(
    'docfile',
    type=argparse.FileType('r'),
    default=sys.stdin,
)
parser.add_argument('-l', '--limit', type=float, default=0.005)

args = parser.parse_args()


def parse(timing):
    "Parse timing."
    if timing.endswith('ms'):
        value = float(timing[:-2]) * 1e-3
    elif timing.endswith('us'):
        value = float(timing[:-2]) * 1e-6
    else:
        assert timing.endswith('s')
        value = float(timing[:-1])
    return 0.0 if value > args.limit else value


lines = args.docfile.readlines()

data = co.OrderedDict()
index = 0

while index < len(lines):
    line = lines[index]

    if blocks.match(line):
        try:
            name = title.match(lines[index + 1]).group(1)
        except:
            index += 1
            continue
        data[name] = {}
        assert dashes.match(lines[index + 2])
        cols = [val.strip() for val in row.match(lines[index + 3]).groups()]
        assert blocks.match(lines[index + 4])
        get_row = [val.strip() for val in row.match(lines[index + 5]).groups()]
        assert get_row[0] == 'get'
        set_row = [val.strip() for val in row.match(lines[index + 6]).groups()]
        assert set_row[0] == 'set'
        delete_row = [val.strip() for val in row.match(lines[index + 7]).groups()]
        assert delete_row[0] == 'delete'
        assert blocks.match(lines[index + 9])
        data[name]['get'] = dict(zip(cols, get_row))
        data[name]['set'] = dict(zip(cols, set_row))
        data[name]['delete'] = dict(zip(cols, delete_row))
        index += 10
    else:
        index += 1

for action in ['get', 'set', 'delete']:
    fig, ax = plt.subplots()
    colors = ['#ff7f00', '#377eb8', '#4daf4a', '#984ea3', '#e41a1c']
    width = 0.15

    ticks = ('Median', 'P90', 'P99')
    index = (0, 1, 2)
    names = list(data)
    bars = []

    for pos, (name, color) in enumerate(zip(names, colors)):
        bars.append(ax.bar(
            [val + pos * width for val in index],
            [parse(data[name][action][tick]) for tick in ticks],
            width,
            color=color,
        ))

    ax.set_ylabel('Time (s)')
    ax.set_title('Percentile vs Time for "%s"' % action)
    ax.set_xticks([val + width * (len(data) / 2) for val in index])
    ax.set_xticklabels(ticks)
    ax.legend([bar[0] for bar in bars], names, loc='best')

    plt.show()
