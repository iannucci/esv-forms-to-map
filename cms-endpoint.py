import asyncio
import json
import os
import zlib
from datetime import datetime, timezone

MAILBOX_DIR = "mailboxes"
USERS_FILE = "users.json"

# Base91 decode table for B2F decompression
B91_TABLE = [None] * 256
B91_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    "!#$%&()*+,./:;<=>?@[]^_`{|}~\""
)
for i, c in enumerate(B91_ALPHABET):
    B91_TABLE[ord(c)] = i

def base91_decode(data: str) -> bytes:
    v = -1
    b = 0
    n = 0
    out = bytearray()
    for ch in data:
        c = B91_TABLE[ord(ch)]
        if c is None:
            continue
        if v < 0:
            v = c
        else:
            v += c * 91
            b |= v << n
            n += 13 if (v & 8191) > 88 else 14
            while n > 7:
                out.append(b & 255)
                b >>= 8
                n -= 8
            v = -1
    if v >= 0:
        out.append((b | v << n) & 255)
    return bytes(out)

def decode_b2f_block(encoded: str) -> str:
    try:
        compressed_data = base91_decode(encoded)
        decompressed = zlib.decompress(compressed_data)
        return decompressed.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[ERROR] B2F decode failed: {e}")
        return ""

def decode_if_compressed(lines: list[str]) -> str:
    is_compressed = False
    encoded_blob = ""
    for line in lines:
        if line.startswith("Content-Encoding: x-b2-compression"):
            is_compressed = True
        elif is_compressed and line.strip() and not line.startswith("Content-"):
            encoded_blob += line.strip()
    if is_compressed and encoded_blob:
        return decode_b2f_block(encoded_blob)
    else:
        return "\n".join(lines)

def extract_b2_headers(b2f_message: str) -> dict:
    headers = {}
    for line in b2f_message.splitlines():
        if line.startswith("SF "):
            parts = line.strip().split()
            if len(parts) >= 3:
                headers["From"] = parts[2]
                headers["To"] = parts[1]
        elif line.startswith("SU "):
            headers["Subject"] = line[3:].strip()
        elif line.startswith("MID "):
            headers["MID"] = line[4:].strip()
        elif line.strip() == "/EX":
            break
    return headers

def load_users(filename=USERS_FILE) -> dict:
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Could not load user file: {e}")
        return {}

USERS = load_users()

if not os.path.exists(MAILBOX_DIR):
    os.makedirs(MAILBOX_DIR)

MAILBOX = {}

def load_mailbox(callsign: str) -> list:
    mailbox_path = os.path.join(MAILBOX_DIR, f"{callsign}.mbox")
    if os.path.isfile(mailbox_path):
        with open(mailbox_path, "r", encoding="utf-8") as f:
            content = f.read()
            return content.split("\n\n") if content.strip() else []
    return []

def save_message(callsign: str, message: str):
    mailbox_path = os.path.join(MAILBOX_DIR, f"{callsign}.mbox")
    with open(mailbox_path, "a", encoding="utf-8") as f:
        f.write(message.strip() + "\n\n")

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info('peername')
    print(f"[+] Connection from {addr}")

    # === CMS Plaintext Password Login Flow ===

    writer.write(b"Callsign :\r")
    await writer.drain()
    try:
        callsign = (await reader.readuntil(b"\r")).decode("utf-8", errors="ignore").strip().upper()
    except asyncio.IncompleteReadError:
        print("[LOGIN] Connection closed prematurely")
        writer.close()
        return

    print(f"[LOGIN] Callsign received: {callsign}")

    # <-- This is your requested line -->
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    writer.write(f";FW:{timestamp}\r".encode("utf-8"))
    await writer.drain()

    writer.write(b"Password :\r")
    await writer.drain()
    try:
        password = (await reader.readuntil(b"\r")).decode("utf-8", errors="ignore").strip()
    except asyncio.IncompleteReadError:
        print("[LOGIN] Connection closed during password input")
        writer.close()
        return

    print(f"[LOGIN] Password received")

    stored_password = USERS.get(callsign)
    if stored_password is None or stored_password != password:
        writer.write(b";NAK\r")
        await writer.drain()
        print(f"[LOGIN] Invalid password for {callsign}")
        writer.close()
        return

    print(f"[LOGIN] Successful login for {callsign}")

    # Load mailbox for this callsign
    if callsign not in MAILBOX:
        MAILBOX[callsign] = load_mailbox(callsign)

    writer.write(b"WL-AREDN Bridge Rel 1.0\r")
    writer.write(b";PQ: 00000001\r")
    writer.write(b"CMS>\r")
    await writer.drain()

    incoming_lines = []
    receiving_message = False

    while True:
        try:
            line = (await reader.readuntil(b"\r")).decode("utf-8", errors="ignore").strip()
        except asyncio.IncompleteReadError:
            print(f"[-] Connection lost: {callsign}")
            break

        print(f"[{callsign}] Received: {line}")

        # Start message reception on ;PR:
        if line.startswith(";PR:"):
            receiving_message = True
            incoming_lines.clear()
            incoming_lines.append(line)
            writer.write(b";OK: Ready to receive message\r")
            await writer.drain()
            continue

        # End of message is line containing FF (ASCII 0xFF)
        if line == "\xFF":
            decoded = decode_if_compressed(incoming_lines)
            full_msg = decoded if decoded else "\n".join(incoming_lines)
            to_call = None

            for l in full_msg.splitlines():
                if l.startswith("SF "):
                    parts = l.split()
                    if len(parts) >= 3:
                        to_call = parts[1].upper()
                    break

            if not to_call:
                to_call = callsign

            if to_call not in MAILBOX:
                MAILBOX[to_call] = load_mailbox(to_call)
            MAILBOX[to_call].append(full_msg)
            save_message(to_call, full_msg)

            headers = extract_b2_headers(full_msg)
            print(f"[MAIL] Stored message for {to_call}")
            print(f"       From   : {headers.get('From', '?')}")
            print(f"       Subject: {headers.get('Subject', '?')}")
            print(f"       MID    : {headers.get('MID', '?')}")

            writer.write(b";OK: Message received\r")
            await writer.drain()

            incoming_lines.clear()
            receiving_message = False
            continue

        if receiving_message:
            incoming_lines.append(line)
            continue

    writer.close()
    await writer.wait_closed()
    print(f"[-] Connection closed: {callsign}")

async def main():
    server = await asyncio.start_server(handle_client, "0.0.0.0", 8772)
    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    print(f"Serving on {addrs}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
