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

    if headers.get("CT") == "B":
        encoding = headers.get("Encoding", "7bit").lower()
        if encoding == "base64":
            try:
                compressed_data = base64.b64decode("".join(body_lines))
                decompressed = zlib.decompress(compressed_data).decode("utf-8", errors="replace")
                body_lines = decompressed.split("\n")
            except Exception as e:
                body_lines = [f"[ERROR decompressing message: {e}]"]
    return headers, body_lines

def save_message(callsign, msg_lines):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    filename = os.path.join(MAILBOX_DIR, f"{callsign}_{timestamp}.b2f")
    with open(filename, "w", encoding="utf-8") as f:
        for line in msg_lines:
            f.write(line + "\r\n")

    headers, body = decode_b2f(msg_lines)
    print(f"[MAIL] Saved message for {callsign} to {filename}")
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
    writer.write(b"CMS>\r")
    await writer.drain()

    while True:
        try:
            line = (await reader.readuntil(b"\r")).decode("utf-8", errors="ignore").strip()
            print(f"[{callsign}] Received: {line}")

            if line.startswith(";PR:"):
                writer.write(b";OK: Ready to receive message\r")
                await writer.drain()

                msg_lines = []
                while True:
                    raw = await reader.readuntil(b"\r")
                    if raw == b"\xFF\r":
                        break
                    line = raw.decode("utf-8", errors="ignore").strip()
                    msg_lines.append(line)

                save_message(callsign, msg_lines)
                writer.write(b";OK: Message received\r")
                writer.write(b"CMS>\r")
                await writer.drain()

            elif line == "FF":
                print(f"[{callsign}] Received unexpected FF")
                continue

            elif line == "F>":
                print(f"[{callsign}] Ignored client prompt F>")
                continue

            elif line.upper() == "EXIT":
                print(f"[{callsign}] Session terminated by client")
                break

            else:
                writer.write(b";NAK: Unknown command\r")
                writer.write(b"CMS>\r")
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
