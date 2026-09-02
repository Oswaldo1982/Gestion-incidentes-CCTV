import hmac
import hashlib
import base64
import json
import bcrypt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def generate_license_key(payload: dict, secret_key: str) -> str:
    """
    Generates a signed license key from a payload.
    Used for creating licenses.
    """
    json_str = json.dumps(payload, sort_keys=True)
    payload_b64 = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
    
    # Sign using HMAC-SHA256
    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    return f"{payload_b64}.{signature}"

def verify_license_key(license_key: str, secret_key: str) -> dict | None:
    """
    Verifies a license key signature. Returns the payload dict if valid, else None.
    """
    try:
        if "." not in license_key:
            return None
        
        payload_b64, signature = license_key.split(".", 1)
        
        # Verify HMAC signature
        expected_signature = hmac.new(
            secret_key.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_signature, signature):
            return None
        
        # Decode payload
        json_str = base64.b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(json_str)
        return payload
    except Exception:
        return None
