"""Independent VSIF wire decoder, including auto-increment frames."""
def decode_batches(rows, stride=1):
    kind = address = None
    result = []
    for row in rows:
        data = bytes.fromhex(row.get('hex', ''))[::stride]
        writes = []
        i = 0
        while i < len(data):
            command = data[i]
            if command == 0:
                i += 1
                continue
            if command == 0x20:
                assert kind is not None
                address += 1
                value = (data[i+1] << 4) | (data[i+2] & 15)
                i += 3
            else:
                assert command & 0xe0 == 0x20
                kind = command & 31
                address = (data[i+1] << 4) | (data[i+2] & 15)
                value = (data[i+3] << 4) | (data[i+4] & 15)
                i += 5
            writes.append((kind, address, value))
        result.append(writes)
    return result
