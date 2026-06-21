"""
Decrypt TWAK wallet.json mnemonic.
TWAK uses: PBKDF2-SHA256 (600,000 iter) + AES-256-GCM
"""
import json
import hashlib
import binascii
import subprocess
import os
import sys

try:
    from Crypto.Cipher import AES
except ImportError:
    os.system("pip install pycryptodome -q")
    from Crypto.Cipher import AES

wallet_path = os.path.expanduser("~/.twak/wallet.json")
with open(wallet_path) as f:
    data = json.load(f)

salt       = binascii.unhexlify(data["salt"])
iv         = binascii.unhexlify(data["iv"])
auth_tag   = binascii.unhexlify(data["authTag"])
ciphertext = binascii.unhexlify(data["encryptedMnemonic"])

print(f"Wallet loaded: ciphertext={len(ciphertext)} bytes, salt={len(salt)} bytes")

# Read password from keychain directly (no manual input error)
def get_keychain_password():
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "twak", "-a", "wallet", "-w"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        print(f"Keychain read failed: {e}")
    return None

def try_decrypt(password_bytes, label):
    key = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, 600000, dklen=32)
    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        decrypted = cipher.decrypt_and_verify(ciphertext, auth_tag)
        print(f"\n*** DECRYPTED ({label}) ***")
        print(decrypted.decode("utf-8"))
        return True
    except Exception:
        return False

# 1. Try keychain password directly
kc_password = get_keychain_password()
if kc_password:
    print(f"Keychain password found (length={len(kc_password)})")
    if try_decrypt(kc_password.encode("utf-8"), "keychain utf-8"):
        sys.exit(0)
    # Try without strip (in case trailing newline matters — unlikely)
    result = subprocess.run(
        ["security", "find-generic-password", "-s", "twak", "-a", "wallet", "-w"],
        capture_output=True
    )
    raw_pw = result.stdout.rstrip(b"\n")
    if try_decrypt(raw_pw, "keychain raw bytes"):
        sys.exit(0)
else:
    print("No keychain password found for service=twak account=wallet")
    # Try without account filter
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "twak", "-w"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            kc_password = result.stdout.strip()
            print(f"Keychain password (no account filter, length={len(kc_password)})")
            if try_decrypt(kc_password.encode("utf-8"), "keychain no-account utf-8"):
                sys.exit(0)
    except Exception as e:
        print(f"Keychain fallback failed: {e}")

# 2. Manual input as fallback
import getpass
manual = getpass.getpass("\nEnter TWAK wallet password manually: ")
if try_decrypt(manual.encode("utf-8"), "manual input"):
    sys.exit(0)

print("\nDecryption failed. Trying iteration variants with manual password...")
for iterations in [100000, 210000, 10000, 50000, 1000, 32000]:
    key = hashlib.pbkdf2_hmac("sha256", manual.encode(), salt, iterations, dklen=32)
    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        decrypted = cipher.decrypt_and_verify(ciphertext, auth_tag)
        print(f"\n*** DECRYPTED (PBKDF2 {iterations} iters) ***")
        print(decrypted.decode("utf-8"))
        sys.exit(0)
    except Exception:
        pass

print("\nAll attempts failed.")
print("Keychain password (hex):", kc_password.encode().hex() if kc_password else "N/A")
