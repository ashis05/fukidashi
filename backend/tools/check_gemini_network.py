"""Diagnose connectivity to the Gemini API host (DNS, TCP, HTTPS, proxies)."""
import os
import socket
import time
import urllib.request

HOST = "generativelanguage.googleapis.com"


def main() -> None:
    print(f"1. DNS for {HOST}")
    try:
        print("   ok:", socket.gethostbyname(HOST))
    except Exception as e:
        print("   FAILED:", e)
        return
    print("2. TCP 443")
    t = time.time()
    try:
        socket.create_connection((HOST, 443), timeout=10).close()
        print(f"   ok in {(time.time() - t) * 1000:.0f} ms")
    except Exception as e:
        print("   FAILED:", e)
        return
    print("3. HTTPS")
    try:
        with urllib.request.urlopen(f"https://{HOST}", timeout=10) as r:
            print("   ok: HTTP", r.getcode())
    except Exception as e:
        print("   response/error:", e)
    print("4. Proxies")
    for k in ("HTTP_PROXY", "HTTPS_PROXY"):
        print(f"   {k}: {'set' if os.environ.get(k) else 'not set'}")


if __name__ == "__main__":
    main()
