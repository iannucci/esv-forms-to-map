def lzw_decompress(compressed: bytes, max_bits=12) -> bytes:
    """
    Decompress LZW-compressed data (assuming 12-bit codes).
    
    Parameters:
        compressed (bytes): LZW compressed data.
        max_bits (int): Maximum bit length of codes (default 12).

    Returns:
        bytes: Decompressed data.
    """
    from io import BytesIO

    # Initialize the dictionary with single-byte entries
    dict_size = 256
    dictionary = {i: bytes([i]) for i in range(dict_size)}
    
    # Setup bit-reading
    data = int.from_bytes(compressed, byteorder='big')
    total_bits = len(compressed) * 8
    code_size = max_bits
    bit_mask = (1 << code_size) - 1

    codes = []
    for i in range(0, total_bits, code_size):
        shift = total_bits - code_size - i
        if shift < 0:
            break
        code = (data >> shift) & bit_mask
        codes.append(code)

    # Decompression loop
    result = BytesIO()
    prev_code = codes.pop(0)
    result.write(dictionary[prev_code])

    for code in codes:
        if code in dictionary:
            entry = dictionary[code]
        elif code == dict_size:
            # Special LZW case: code not in dictionary yet
            entry = dictionary[prev_code] + dictionary[prev_code][:1]
        else:
            raise ValueError(f"Invalid LZW code: {code}")
        
        result.write(entry)
        dictionary[dict_size] = dictionary[prev_code] + entry[:1]
        dict_size += 1
        prev_code = code

    return result.getvalue()
