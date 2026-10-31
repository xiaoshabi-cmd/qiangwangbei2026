#!/usr/bin/env python3
"""bitstream -> FASM using prjxray db (xc7a35t shares xc7a50t fabric)."""
import sys
sys.path.insert(0, '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work')
sys.path.insert(0, '/tmp/prjxray')
import fasm
import fasm.output
from prjxray import fasm_disassembler
from prjxray.db import Database
from bitparse import Part, frames_from_bit

DB_ROOT = '/tmp/prjxray-db/artix7'
PART = 'xc7a35tcpg236-1'


def make_bitdata(frames):
    bitdata = {}
    for far, ws in frames.items():
        words = set()
        bits = set()
        for widx, w in enumerate(ws):
            if w:
                words.add(widx)
                for b in range(32):
                    if (w >> b) & 1:
                        bits.add(widx * 32 + b)
        if bits:
            bitdata[far] = (words, bits)
    return bitdata


def main():
    bitfile = sys.argv[1]
    verbose = '--verbose' in sys.argv
    out = None
    for a in sys.argv[2:]:
        if not a.startswith('--'):
            out = a
    part = Part(DB_ROOT + '/xc7a35tcpg236-1/part.json')
    frames, order = frames_from_bit(bitfile, part)
    bitdata = make_bitdata(frames)
    db = Database(DB_ROOT, PART)
    grid = db.grid()
    dis = fasm_disassembler.FasmDisassembler(db)
    model = fasm.output.merge_and_sort(
        dis.find_features_in_bitstream(bitdata, verbose=verbose),
        zero_function=dis.is_zero_feature,
        sort_key=grid.tile_key,
    )
    txt = fasm.fasm_tuple_to_string(model, canonical=False)
    if out:
        open(out, 'w').write(txt)
        print('wrote', out, len(txt.splitlines()), 'lines')
    else:
        print(txt)


if __name__ == '__main__':
    main()
