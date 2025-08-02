import asyncio
import json
import os
import base64
import zlib
from datetime import datetime, timezone

MAILBOX_DIR = "mailbox"
USERS_FILE = "users.json"
PORT = 8772
HOST = "0.0.0.0"

# Load users from JSON file
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "r") as f:
        USERS = json.load(f)
else:
    USERS = {}

os.makedirs(MAILBOX_DIR, exist_ok=True)

def decode_b2f(lines):
    headers = {}
    body_lines = []
    in_headers = True

    for line in lines:
        if in_headers:
            if line == "":
                in_headers = False
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()
        else:
            body_lines.append(line)

    ct = headers.get("CT", "").upper()
    encoding = headers.get("Encoding", "7bit").lower()
    print(f"[DECODE] CT={ct}, Encoding={encoding}, Line Count={len(body_lines)}")

    if ct == "B" and encoding == "base64":
        try:
            compressed_data = base64.b64decode("".join(body_lines))
            decompressed = zlib.decompress(compressed_data).decode("utf-8", errors="replace")
            body_lines = decompressed.split("\n")
        except Exception as e:
            body_lines = [f"[ERROR decompressing message: {e}]"]
            print(f"[DECODE] Error: {e}")
    else:
        print("[DECODE] No decompression performed")

    return headers, body_lines

def save_message(callsign, msg_lines, proposal):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    raw_filename = os.path.join(MAILBOX_DIR, f"{callsign}_{timestamp}.b2f")
    with open(raw_filename, "w", encoding="utf-8") as f:
        for line in msg_lines:
            f.write(line + "\r\n")

    headers, body = decode_b2f(msg_lines)
    
    # Optional validation: compare decoded line count to size2 (expected decoded size in bytes)
    decoded_bytes = sum(len(line.encode("utf-8")) + 1 for line in body)  # +1 for newline
    if proposal.get("size2") and decoded_bytes < proposal["size2"]:
        print(f"[{callsign}] Warning: decoded message size {decoded_bytes} bytes is less than size2={proposal['size2']}")
    decoded_filename = os.path.join(MAILBOX_DIR, f"{callsign}_{timestamp}.txt")
    with open(decoded_filename, "w", encoding="utf-8") as f:
        for line in body:
            f.write(line + "\n")

    print(f"[MAIL] Saved message for {callsign} to {raw_filename} and decoded to {decoded_filename}")
    print(f"[HEADERS] {json.dumps(headers, indent=2)}")

async def handle_client(reader, writer):
    addr = writer.get_extra_info("peername")
    print(f"[CONNECT] Client connected: {addr}")

    writer.write(b"Callsign :\r")
    await writer.drain()
    callsign = (await reader.readuntil(b"\r")).decode("utf-8", errors="ignore").strip().upper()
    print(f"[LOGIN] Callsign received: {callsign}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    writer.write(f";FW:{timestamp}\r".encode("utf-8"))
    await writer.drain()

    writer.write(b"Password :\r")
    await writer.drain()
    password = (await reader.readuntil(b"\r")).decode("utf-8", errors="ignore").strip()
    print(f"[LOGIN] Password received")

    stored_password = USERS.get(callsign)
    if stored_password is None or stored_password != password:
        writer.write(b";NAK\r\n")
        await writer.drain()
        print(f"[LOGIN] Invalid password for {callsign}")
        writer.close()
        return

    print(f"[LOGIN] Successful login for {callsign}")
    writer.write(b"WL-AREDN Bridge Rel 1.0\r")
    writer.write(b";PQ: 00000001\r")
    writer.write(b";IS:\r")
    writer.write(b";\r")
    writer.write(b"CMS>\r")
    await writer.drain()

    state = "COMMAND"
    proposal_queue = []
    expected_bytes = None

    while True:
        try:
            line = (await reader.readuntil(b"\r")).decode("utf-8", errors="ignore").strip()
            print(f"[{callsign}] Received: {line}")

            if line.startswith("FC"):
                if state not in ["COMMAND", "WAIT_FOR_PROPOSAL"]:
                    writer.write(b";NAK: Unexpected FC\r")
                    await writer.drain()
                    continue
                parts = line.split()
                if len(parts) >= 6:
                    _, msg_type, msg_id, size1, size2, status_flag = parts[:6]
                    proposal_queue.append({
                        "msg_type": msg_type,
                        "msg_id": msg_id,
                        "size1": int(size1),
                        "size2": int(size2),
                        "status_flag": status_flag
                    })
                    state = "WAIT_FOR_PROPOSAL"
                else:
                    writer.write(b";NAK: Malformed FC\r")
                    await writer.drain()

            elif line.startswith("F>"):
                if state != "WAIT_FOR_PROPOSAL" or not proposal_queue:
                    writer.write(b";NAK: Unexpected F>\r")
                    await writer.drain()
                    continue

                serial_number = line.split()[1] if len(line.split()) > 1 else None
                current_proposal = proposal_queue[0]  # Do NOT pop yet
                expected_bytes = current_proposal["size1"]

                print(f"[{callsign}] F> received, serial={serial_number}, expecting {expected_bytes} bytes")
                writer.write(b"FS Y\r")
                await writer.drain()

                msg_bytes = b""
                remaining = expected_bytes
                try:
                    while True:
                        try:
                            chunk = await asyncio.wait_for(reader.read(current_proposal["size1"] - len(msg_bytes)), timeout=1.0)
                            if not chunk:
                                print(f"[{callsign}] Warning: Client closed connection early.")
                                break
                            msg_bytes += chunk
                        except asyncio.TimeoutError:
                            print(f"[{callsign}] Error: Timeout while waiting for message bytes")
                            break
                except asyncio.TimeoutError:
                    print(f"[{callsign}] Error: Timeout while waiting for message bytes")

                actual_len = len(msg_bytes)
                print(f"[{callsign}] Received {actual_len} bytes of {current_proposal['size1']} expected")
                # Debug: show raw bytes as hex and ASCII
                hex_dump = ' '.join(f"{b:02X}" for b in msg_bytes)
                ascii_dump = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in msg_bytes)
                print(f"[{callsign}] HEX: {hex_dump}")
                print(f"[{callsign}] ASCII: {ascii_dump}")

                if actual_len < current_proposal["size1"]:
                    print(f"[{callsign}] Warning: message was truncated (got {actual_len} of {current_proposal['size1']}) — accepting anyway")

                msg_lines = msg_bytes.decode("utf-8", errors="ignore").split("\r\n")
                msg_lines = [line for line in msg_lines if line.strip()]

                if msg_lines:
                    save_message(callsign, msg_lines, current_proposal)
                    writer.write(b";OK: Message received\r")
                    await writer.drain()
                    proposal_queue.pop(0)  # Only now remove
                    state = "WAIT_FOR_PROPOSAL" if proposal_queue else "COMMAND"
                else:
                    writer.write(b";NAK: Empty message\r")
                    await writer.drain()

            elif line == "FF":
                print(f"[{callsign}] Received FF (end of message batch)")
                writer.write(b"FQ\r")
                await writer.drain()
                break

            elif line.upper() == "EXIT":
                print(f"[{callsign}] Session terminated by client")
                break

            elif line.startswith(";FW:"):
                print(f"[{callsign}] FW line accepted: {line}")
                continue
            elif line.startswith(";PR:"):
                print(f"[{callsign}] PR line received: {line}")
                continue
            elif line.startswith(";") and not line.startswith(";NAK"):
                print(f"[{callsign}] Info line: {line}")
                continue
            elif line.startswith("["):
                print(f"[{callsign}] Header comment line: {line}")
                continue
            else:
                print(f"[{callsign}] Unknown command: {line}")
                writer.write(f";NAK: Unknown command '{line}'\r".encode("utf-8"))
                await writer.drain()

        except (asyncio.IncompleteReadError, ConnectionResetError):
            print(f"[{callsign}] Connection closed")
            break

    writer.close()
    await writer.wait_closed()
    print(f"[DISCONNECT] Client disconnected: {addr}")

async def main():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    addr = server.sockets[0].getsockname()
    print(f"[START] Server listening on {addr}")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
