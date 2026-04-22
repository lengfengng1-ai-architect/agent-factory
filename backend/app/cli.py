#!/usr/bin/env python3
import argparse
import os
import socket
import sys


def find_free_port(start: int = 18000, end: int = 18100) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"No free port found in range {start}-{end}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Factory Backend Server")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Server port (0 = auto-scan, default: 0)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Data directory path",
    )
    parser.add_argument(
        "--redis-url",
        type=str,
        default=None,
        help="Redis URL (e.g., redis://host:port/db)",
    )
    parser.add_argument(
        "--no-feishu",
        action="store_true",
        help="Skip Feishu WebSocket startup",
    )
    args = parser.parse_args()

    if args.data_dir is not None:
        os.environ["AGENT_FACTORY_DATA_DIR"] = args.data_dir

    if args.redis_url is not None:
        os.environ["REDIS_URL"] = args.redis_url

    if args.no_feishu:
        os.environ["AGENT_FACTORY_NO_FEISHU"] = "1"

    port = args.port
    if port == 0:
        port = find_free_port()

    import uvicorn
    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
