"Plot benchmark docs."

import argparse
import collections as co
import matplotlib.pyplot as plt
import re
import sys


def parse_timing(timing, limit):
    "Parse timing."
    if timing.endswith('ms'):
        value = float(timing[:-2]) * 1e-3
    elif timing.endswith('us'):
        value = float(timing[:-2]) * 1e-6
    else:
        assert timing.endswith('s')
        value = float(timing[:-1])
    return 0.0 if value > limit else value


def parse_row(row, line):
    "Parse row."
    return [val.strip() for val in row.match(line).groups()]


def parse_data(infile):
    "Parse data from `infile`."
    blocks = re.compile(' '.join(['=' * 9] * 8))
    dashes = re.compile('^-{79}$')
    title = re.compile('^Timings for (.*)$')
    row = re.compile(' '.join(['(.{9})'] * 7) + ' (.{8,9})')

    lines = infile.readlines()

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

            cols = parse_row(row, lines[index + 3])

            assert blocks.match(lines[index + 4])

            get_row = parse_row(row, lines[index + 5])
            assert get_row[0] == 'get'

            set_row = parse_row(row, lines[index + 6])
            assert set_row[0] == 'set'

            delete_row = parse_row(row, lines[index + 7])
            assert delete_row[0] == 'delete'

            assert blocks.match(lines[index + 9])

            data[name]['get'] = dict(zip(cols, get_row))
            data[name]['set'] = dict(zip(cols, set_row))
            data[name]['delete'] = dict(zip(cols, delete_row))

            index += 10
        else:
            index += 1

    return data


def make_plot(data, action, save=False, show=False, limit=0.005):
    "Make plot."
    fig, ax = plt.subplots(figsize=(8, 10))
    colors = ['#ff7f00', '#377eb8', '#4daf4a', '#984ea3', '#e41a1c']
    width = 0.15

    ticks = ('Median', 'P90', 'P99')
    index = (0, 1, 2)
    names = list(data)
    bars = []

    for pos, (name, color) in enumerate(zip(names, colors)):
        bars.append(ax.bar(
            [val + pos * width for val in index],
            [parse_timing(data[name][action][tick], limit) for tick in ticks],
            width,
            color=color,
        ))

    ax.set_ylabel('Time (s)')
    ax.set_title('"%s" Time vs Percentile' % action)
    ax.set_xticks([val + width * (len(data) / 2) for val in index])
    ax.set_xticklabels(ticks)

    box = ax.get_position()
    ax.set_position([box.x0, box.y0 + box.height * 0.2, box.width, box.height * 0.8])
    ax.legend(
        [bar[0] for bar in bars],
        names,
        loc='lower center',
        bbox_to_anchor=(0.5, -0.3)
    )

    if show:
        plt.show()

    if save:
        plt.savefig('%s-%s.png' % (save, action), dpi=80, bbox_inches='tight')

    plt.close()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        'infile',
        type=argparse.FileType('r'),
        default=sys.stdin,
    )
    parser.add_argument('-l', '--limit', type=float, default=0.005)
    parser.add_argument('-s', '--save')
    parser.add_argument('--show', action='store_true')

    args = parser.parse_args()

    data = parse_data(args.infile)

    for action in ['get', 'set', 'delete']:
        make_plot(data, action, args.save, args.show, args.limit)


if __name__ == '__main__':
    main()
