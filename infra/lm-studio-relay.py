#!/usr/bin/env python3
"""
LM Studio relay for Docker on WSL2.

LM Studio binds to 127.0.0.1:1234 by default, which Docker containers cannot
reach. This script listens on 0.0.0.0:1235 and forwards all TCP traffic to
127.0.0.1:1234, making LM Studio reachable from Docker containers via
host.docker.internal:1235 or the WSL2 eth0 IP on port 1235.

Usage:
    python3 infra/lm-studio-relay.py &

Then set in infra/.env:
    OLLAMA_BASE_URL=http://host.docker.internal:1235/v1
"""

import socket
import threading
import sys
import signal

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 1235
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 1234


def forward(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            src.close()
        except OSError:
            pass
        try:
            dst.close()
        except OSError:
            pass


def handle(client: socket.socket) -> None:
    try:
        server = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=10)
        server.settimeout(None)
    except OSError as e:
        print(f"[relay] Cannot connect to LM Studio at {TARGET_HOST}:{TARGET_PORT}: {e}", flush=True)
        client.close()
        return

    t1 = threading.Thread(target=forward, args=(client, server), daemon=True)
    t2 = threading.Thread(target=forward, args=(server, client), daemon=True)
    t1.start()
    t2.start()


def main() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((LISTEN_HOST, LISTEN_PORT))
    except OSError as e:
        print(f"[relay] Failed to bind {LISTEN_HOST}:{LISTEN_PORT}: {e}", file=sys.stderr)
        sys.exit(1)

    srv.listen(50)
    print(
        f"[relay] Listening on {LISTEN_HOST}:{LISTEN_PORT} "
        f"-> {TARGET_HOST}:{TARGET_PORT}",
        flush=True,
    )

    def shutdown(signum, frame):
        print("\n[relay] Shutting down.", flush=True)
        srv.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        try:
            client, addr = srv.accept()
        except OSError:
            break
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
