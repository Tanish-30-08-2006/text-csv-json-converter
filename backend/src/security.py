import os
import hmac
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# -------------------------------------------------------------------------
# SECURITY CONFIGURATION (OWASP Best Practices)
# -------------------------------------------------------------------------

# Load environment variables from a .env file so secrets are NEVER hardcoded in the source code.
# This ensures API keys, database credentials, and Flask secrets remain strictly on the server.
load_dotenv()

# Secure API Key Handling: Pulled securely from the environment, not hardcoded.
# If the environment variable isn't set, it defaults to None (which will block access).
SERVER_API_KEY = os.getenv("CONVERTER_API_KEY")

# Allowed file extensions to prevent malicious scripts (like .exe or .sh) from being uploaded
ALLOWED_EXTENSIONS = {'txt', 'csv', 'tsv', 'json'}

# Sensible default: 5MB maximum file size to prevent Denial of Service (DoS) attacks via massive uploads
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  

# -------------------------------------------------------------------------
# INPUT VALIDATION & SANITIZATION
# -------------------------------------------------------------------------

def is_allowed_extension(filename):
    """
    Checks if the uploaded file's extension is strictly within our whitelisted allowed extensions.
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_and_sanitize_file(filename, file_size=0):
    """
    Validates the file against size and extension schemas, then sanitizes the filename to prevent 
    directory traversal attacks (e.g., ../../../etc/passwd).
    
    Returns: (is_valid: bool, sanitized_name_or_error_msg: str)
    """
    if file_size > MAX_FILE_SIZE_BYTES:
        return False, f"File exceeds maximum allowed size of 5MB."

    if not is_allowed_extension(filename):
        return False, f"File type not allowed. Supported formats: {ALLOWED_EXTENSIONS}"

    # secure_filename() strips out any malicious path characters from the filename.
    # E.g. "../../../hack.sh" becomes "hack.sh"
    safe_name = secure_filename(filename)
    
    if not safe_name:
        return False, "Invalid filename provided."

    return True, safe_name

def require_api_key(provided_key):
    """
    Validates the provided API key against the server's secured environment key.
    Uses constant-time comparison (omitted here for simplicity, but logically sound) to prevent timing attacks.
    """
    if not SERVER_API_KEY:
        # Fail-closed security: If the server operator forgot to put a key in .env, deny everything.
        return False, "Server security configuration error. API key not initialized."
        
    if provided_key is None:
        return False, "Unauthorized. API key missing."
        
    if not hmac.compare_digest(str(provided_key), str(SERVER_API_KEY)):
        return False, "Unauthorized. Invalid API key."
        
    return True, "Authorized"

# -------------------------------------------------------------------------
# RATE LIMITING SETUP
# -------------------------------------------------------------------------
# Note: Since the web server isn't built yet, we define the blueprint here.
# When we build `app.py` in Phase 5, we will pass the Flask app object into this function.

def setup_rate_limiter(app):
    """
    Initialises Flask-Limiter for the web application.
    Rate limiting prevents Brute Force and DDoS attacks by capping how many times 
    a single IP address can hit our endpoints within a specific timeframe.
    """
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"], # Sensible base limits
        storage_uri="memory://" # Can be switched to Redis in full production
    )
    
    return limiter
