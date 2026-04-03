#!/usr/bin/env python3
"""
Submit an external signal to a live trading session via API.

Usage:
    python submit_signal.py --session-id <ID> --side buy [--quantity 100] [--price 0]
                            [--source skill:rsi] [--api-url http://localhost:8001]

Output:
    JSON response from the server.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error


def submit_signal(api_url: str, session_id: str, side: str,
                  quantity: float = 0, price: float = 0,
                  order_type: str = "market", source: str = "skill",
                  metadata: dict = None) -> dict:
    """Submit a signal to the session's ExecutionEngine."""
    url = f"{api_url}/api/v1/live/session/{session_id}/submit-signal"

    payload = {
        "side": side,
        "quantity": quantity,
        "price": price,
        "order_type": order_type,
        "source": source,
        "metadata": metadata or {},
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def main():
    parser = argparse.ArgumentParser(description="Submit signal to live session")
    parser.add_argument("--session-id", required=True, help="Live session ID")
    parser.add_argument("--side", required=True, choices=["buy", "sell", "short", "close_position"],
                        help="Signal side")
    parser.add_argument("--quantity", type=float, default=0, help="Order quantity (0 = auto)")
    parser.add_argument("--price", type=float, default=0, help="Price (0 = market)")
    parser.add_argument("--order-type", default="market", help="Order type")
    parser.add_argument("--source", default="skill", help="Signal source tag (must start with 'skill')")
    parser.add_argument("--metadata", type=str, default=None, help="JSON metadata string")
    parser.add_argument("--api-url", default="http://localhost:8001", help="Backend API URL")
    args = parser.parse_args()

    metadata = json.loads(args.metadata) if args.metadata else None

    try:
        result = submit_signal(
            api_url=args.api_url,
            session_id=args.session_id,
            side=args.side,
            quantity=args.quantity,
            price=args.price,
            order_type=args.order_type,
            source=args.source,
            metadata=metadata,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.readable() else ""
        print(json.dumps({"error": f"HTTP {e.code}: {e.reason}", "detail": body}, indent=2))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}), indent=2)
        sys.exit(1)


if __name__ == "__main__":
    main()
