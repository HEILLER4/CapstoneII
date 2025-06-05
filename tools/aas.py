from cryptography.fernet import Fernet

# Generate and save a key (run once, keep this key safe!)
def generate_key():
    key = Fernet.generate_key()
    with open("../secret.key", "wb") as f:
        f.write(key)
    print("[INFO] Key generated and saved to 'secret.key'")

# Encrypt an API key using the saved key
def encrypt_api_key(api_key):
    with open("../secret.key", "rb") as f:
        key = f.read()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(api_key.encode())
    with open("../encrypted_api.key", "wb") as f:
        f.write(encrypted)
    print("[INFO] Encrypted API key saved to 'encrypted_api.key'")

if __name__ == "__main__":
    generate_key()
    api_key = input("Enter your API key: ")
    encrypt_api_key(api_key)
