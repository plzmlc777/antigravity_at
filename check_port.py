
import socket
import sys

def check_server(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(('127.0.0.1', port))
        print(f"Port {port}: OPEN")
        return True
    except Exception as e:
        print(f"Port {port}: CLOSED ({e})")
        return False
    finally:
        s.close()

if __name__ == "__main__":
    check_server(8001)
