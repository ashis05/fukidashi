import socket
import time
import sys
import os

print("--- 🕵️ NETWORK DIAGNOSTIC TOOL ---")

def test_dns(hostname):
    print(f"\n1. Testing DNS Resolution for {hostname}...")
    try:
        ip = socket.gethostbyname(hostname)
        print(f"   ✅ Success! Resolved to: {ip}")
        return ip
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return None

def test_connection(hostname, port):
    print(f"\n2. Testing TCP Connection to {hostname}:{port}...")
    start = time.time()
    try:
        sock = socket.create_connection((hostname, port), timeout=10)
        sock.close()
        duration = (time.time() - start) * 1000
        print(f"   ✅ Success! Connected in {duration:.2f} ms")
        return True
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False

def test_https_request(url):
    print(f"\n3. Testing HTTPS Request to {url}...")
    # We use raw socket to avoid library issues
    import urllib.request
    try:
        start = time.time()
        with urllib.request.urlopen(url, timeout=10) as response:
            code = response.getcode()
            duration = (time.time() - start) * 1000
            print(f"   ✅ Success! HTTP {code} in {duration:.2f} ms")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")

# --- MAIN EXECUTION ---
target_host = "generativelanguage.googleapis.com"
target_url = f"https://{target_host}"

ip = test_dns(target_host)
if ip:
    test_connection(target_host, 443)
    test_https_request(target_url)

print("\n--- 4. Checking Environment ---")
print(f"   HTTP_PROXY: {os.environ.get('HTTP_PROXY', 'Not Set')}")
print(f"   HTTPS_PROXY: {os.environ.get('HTTPS_PROXY', 'Not Set')}")
print("-------------------------------")