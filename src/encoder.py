"""Existing PSG/OPLL/SCC-I encoding and snapshot rules, one batch entry point."""
import json
from pathlib import Path
SAMPLE_RATE = RATE = 44100
def frame(t,a,d): return [0x20|t,a>>4,0x10|(a&15),d>>4,0x10|(d&15)]

def convert(row):
    chip, a, d = row["chip"], row["address"], row["data"]
    if chip == "PSG": return 0x17, a, (d & 0x3f) | 0x80 if a == 7 else d
    if chip == "YM2413": return 1, a, d
    if chip == "SCC":
        port, a = a >> 8, a & 255
        if port == 1: a += 0xa0
        elif port == 2: a += 0xaa
        elif port == 3: a = 0xaf
        elif port == 5: a += 0xe0
        elif port != 0: raise ValueError(f"unsupported SCC port {port}")
        return 4, a, d
    return None

def register_writes(writes):
    """Expand source SCC shared waveform writes for the SCC-I output mode."""
    for row in writes:
        item = convert(row)
        if item is None: continue
        yield row['sample'], item
        # VGM SCC port 0 addresses 60..7f are the shared ch4/ch5 waveform.
        # Type 4 selects SCC-I independent wave RAM: ch5 needs its own copy.
        # Apply on every update, including host-side seek state reconstruction.
        if row['chip'] == 'SCC' and 0x60 <= row['address'] <= 0x7f:
            yield row['sample'], (4, row['address'] + 0x20, row['data'])

def initial(writes):
    def audible(row):
        return ((row["chip"] == "PSG" and 8 <= row["address"] <= 10 and row["data"] != 0)
                or (row["chip"] == "YM2413" and 0x20 <= row["address"] <= 0x28 and row["data"] & 0x10)
                or (row["chip"] == "SCC" and row["address"] >> 8 == 2 and row["data"] != 0))
    first_audible = next((row["sample"] for row in writes if audible(row)), 0)
    frames, selected, last_type, last_address = [], False, -1, -1
    for sample, item in register_writes(writes):
        kind, address, data = item
        if kind == 4 and not selected:
            frames.append((sample, frame(3,1,0) + [0,0,0,0]))
            selected, last_type, last_address = True, 3, 1
        contiguous = kind in (1, 4) and kind == last_type and address == last_address + 1
        frames.append((sample, [0x20, data >> 4, 0x10 | (data & 15)] if contiguous else frame(kind, address, data)))
        last_type, last_address = kind, address
    prelude = [entry for entry in frames if entry[0] < first_audible]
    bins = {}
    for sample, values in (entry for entry in frames if entry[0] >= first_audible):
        bucket = bins.setdefault(sample, [sample, []])
        bucket[0] = min(bucket[0], sample); bucket[1].extend(values)
    rows = [{"kind":"metadata", "profile":"SCC-I automatic select", "sample_rate":SAMPLE_RATE, "prelude_before_sample":first_audible},
            {"bin":-1, "sample":0, "hex":bytes(sum((values for _, values in prelude), [])).hex()}]
    rows += [{"bin":bucket, "sample":data[0], "hex":bytes(data[1]).hex()} for bucket, data in sorted(bins.items())]
    return rows

def snapshot(writes,target):
    state = {0x17: {}, 1: {}, 4: {}}
    for sample, item in register_writes(writes):
        if sample >= target: break
        state[item[0]][item[1]] = item[2]
    # A snapshot writes only final register values.  Audible registers are last.
    pre, gate = [], []
    for a in range(14):
        if a not in (8, 9, 10) and a in state[0x17]: pre += frame(0x17, a, state[0x17][a])
    for a in (8, 9, 10):
        if a in state[0x17]: gate += frame(0x17, a, state[0x17][a])
    for a, d in state[1].items():
        # Rhythm enable can make the OPLL audible even while channel key-on
        # registers are withheld.  It belongs with the final gate.
        if not 0x20 <= a <= 0x28 and a != 0x0e: pre += frame(1, a, d)
    if 0x0e in state[1]: gate += frame(1, 0x0e, state[1][0x0e])
    for a in range(0x20, 0x29):
        if a in state[1]: gate += frame(1, a, state[1][a])
    if state[4]:
        pre += frame(3, 1, 0) + [0, 0, 0, 0]
        for a, d in state[4].items():
            if not 0xaa <= a <= 0xaf: pre += frame(4, a, d)
        for a in range(0xaa, 0xb0):
            if a in state[4]: gate += frame(4, a, state[4][a])
    bins = {}
    for sample, item in register_writes(writes):
        if sample < target: continue
        bucket = bins.setdefault(sample, [sample, []])
        bucket[0] = min(bucket[0], sample); bucket[1] += frame(*item)
    out = [{"kind":"metadata","mode":"seek","sample_rate":RATE,"target_sample":target},
           {"bin":-2,"sample":target,"hex":bytes(pre).hex()}, {"bin":-3,"sample":target,"hex":bytes(gate).hex()}]
    out += [{"bin":b,"sample":v[0],"hex":bytes(v[1]).hex()} for b,v in sorted(bins.items())]
    return out

def build(writes, destination, target_ms=0, total_samples=None):
    target = round(target_ms*RATE/1000)
    rows = initial(writes) if target == 0 else snapshot(writes,target)
    # Explicit end preserves trailing silence, including seeks near the end.
    end = max(target, total_samples if total_samples is not None else (writes[-1]['sample'] if writes else target))
    rows.append({'bin':2147483647,'sample':end,'hex':''})
    Path(destination).write_text('\n'.join(json.dumps(row,separators=(',',':')) for row in rows)+'\n',encoding='utf-8')
    return rows
