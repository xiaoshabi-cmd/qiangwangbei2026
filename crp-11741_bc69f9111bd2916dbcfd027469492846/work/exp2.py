#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work')
import exp1
from exp1 import tick, state, vals

KEY = 0x0123456789abcdef
def key_bits(key, n=64, msb=True):
    return [(key >> (n-1-i if msb else i)) & 1 for i in range(n)]
def frame_bits(fr, n=22, msb=True):
    return [(fr >> (n-1-i if msb else i)) & 1 for i in range(n)]

def run(bits_in, total, label):
    state.clear()
    outs = []
    for k in range(total):
        din = bits_in[k] if k < len(bits_in) else 1
        outs.append(tick(din))
    tx = ''.join(str(o) for o in outs)
    print(label, 'tx[0:160]:', tx[:160])
    print(label, 'zeros:', tx.count('0'), 'first0@', tx.find('0'))
    return tx

N = 4000
run(key_bits(KEY) + frame_bits(0), N, 'A(msb)')
run(key_bits(KEY, msb=False) + frame_bits(0, msb=False), N, 'B(lsb)')
run([1]*100 + key_bits(KEY) + frame_bits(0), N, 'C(idle+msb)')
