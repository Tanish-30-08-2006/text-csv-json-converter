import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Import our custom modules
from security import validate_and_sanitize_file, require_api_key, setup_rate_limiter, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_BYTES
from converter import convert_file_for_web

# -------------------------------------------------------------------------
# SETUP & CONFIGURATION
# -------------------------------------------------------------------------
app = Flask(__name__)

# Apply CORS to the entire app to allow frontend connections
CORS(app)

# Apply Rate Limiting Blueprint
limiter = setup_rate_limiter(app)

base_dir = os.path.dirname(os.path.abspath(__file__))
raw_data_path = os.path.join(base_dir, "..", "data", "raw")
processed_data_path = os.path.join(base_dir, "..", "data", "processed")
stats_file_path = os.path.join(base_dir, "..", "data", "stats.json")

# Ensure critical directories exist
os.makedirs(raw_data_path, exist_ok=True)
os.makedirs(processed_data_path, exist_ok=True)


# -------------------------------------------------------------------------
# GLOBAL SECURITY HEADERS
# -------------------------------------------------------------------------
@app.after_request
def add_security_headers(response):
    """Adds critical OWASP security headers to every single response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


# -------------------------------------------------------------------------
# HELPER: STATS TRACKER
# -------------------------------------------------------------------------
def update_stats(processing_time_ms):
    """
    Reads data/stats.json, increments the counter, calculates the rolling average speed,
    and saves it back to the file atomically.
    """
    stats = {
        "files_converted": 0,
        "formats_supported": ["TXT", "CSV", "TSV", "XLSX", "JSON", "Nested JSON"],
        "processing_speed_ms": 0
    }
    
    # Read existing stats if present
    if os.path.exists(stats_file_path):
        try:
            with open(stats_file_path, "r", encoding="utf-8") as f:
                loaded_stats = json.load(f)
                stats.update(loaded_stats)
        except json.JSONDecodeError:
            pass # Use defaults if corrupted

    current_count = stats.get("files_converted", 0)
    current_avg = stats.get("processing_speed_ms", 0)
    
    new_count = current_count + 1
    # Rolling average formula
    new_avg = ((current_avg * current_count) + processing_time_ms) // new_count
    
    stats["files_converted"] = new_count
    stats["processing_speed_ms"] = new_avg
    stats["formats_supported"] = ["TXT", "CSV", "TSV", "XLSX", "JSON", "Nested JSON"]
    
    # Write updated stats
    with open(stats_file_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4)


# -------------------------------------------------------------------------
# ENDPOINTS
# -------------------------------------------------------------------------

@app.route('/upload', methods=['POST'])
@limiter.limit("10 per minute")
def upload_file():
    """
    Endpoint 1 — File Upload & Conversion
    Expects a multipart/form-data request with a 'file' payload.
    """
    # Check that a file was actually included
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
        
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Get file size from the stream headers
    file_size = request.content_length or 0
    
    # Security Validation
    is_safe, sanitized_or_err = validate_and_sanitize_file(file.filename, file_size=file_size)
    if not is_safe:
        status_code = 413 if "size" in sanitized_or_err.lower() else 400
        return jsonify({"error": sanitized_or_err}), status_code

    # Save to Raw
    saved_path = os.path.join(raw_data_path, sanitized_or_err)
    file.save(saved_path)
    
    # Run conversion
    result = convert_file_for_web(saved_path, processed_data_path)
    
    if result.get("success"):
        update_stats(result.get("processing_time_ms", 0))
        return jsonify(result), 200
    else:
        return jsonify(result), 500


@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """
    Endpoint 2 — Secure File Download
    Sanitizes the requested filename and forces an attachment download.
    """
    safe_name = secure_filename(filename)
    
    # If sanitization changes the name, the user requested something hacky (like ../file)
    if safe_name != filename:
        return jsonify({"error": "Invalid filename requested"}), 400
        
    file_path = os.path.join(processed_data_path, safe_name)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
        
    return send_from_directory(processed_data_path, safe_name, as_attachment=True)


@app.route('/stats', methods=['GET'])
def get_stats():
    """
    Endpoint 3 — Public Statistics
    Returns the basic server statistics from stats.json.
    """
    stats = {
        "files_converted": 0,
        "formats_supported": ["TXT", "CSV", "TSV", "XLSX", "JSON", "Nested JSON"],
        "processing_speed_ms": 0
    }
    
    if os.path.exists(stats_file_path):
        try:
            with open(stats_file_path, "r", encoding="utf-8") as f:
                loaded_stats = json.load(f)
                stats.update(loaded_stats)
        except json.JSONDecodeError:
            pass
            
    return jsonify(stats), 200


@app.route('/health', methods=['GET'])
def health_check():
    """
    Endpoint 4 — Health Check
    No rate limit on this basic ping.
    """
    return jsonify({"status": "running", "watcher": "active"}), 200


# -------------------------------------------------------------------------
# RUN SERVER
# -------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
