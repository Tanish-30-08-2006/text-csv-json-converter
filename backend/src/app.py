import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Import our custom modules
from security import validate_and_sanitize_file, require_api_key, setup_rate_limiter, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_BYTES
from converter import convert_file_for_web, read_any_file, detect_delimiter

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

@app.route('/preview', methods=['POST'])
@limiter.limit("20 per minute")
def preview_file():
    """
    Endpoint 5 — File Preview
    """
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part in the request"}), 400
            
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        file_size = request.content_length or 0
        
        is_safe, sanitized_or_err = validate_and_sanitize_file(file.filename, file_size=file_size)
        if not is_safe:
            return jsonify({"error": sanitized_or_err}), 400

        saved_path = os.path.join(raw_data_path, sanitized_or_err)
        file.save(saved_path)
        
        with open(saved_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            
        converted_data = read_any_file(saved_path)
        
        first_line = all_lines[0] if all_lines else ""
        detected_delimiter = detect_delimiter(first_line)
        
        delimiter_names = {
            '|': 'Pipe',
            ',': 'Comma',
            '\t': 'Tab',
            ';': 'Semicolon'
        }
        delimiter_name = delimiter_names.get(detected_delimiter, 'Unknown')
        
        headers = converted_data[0] if converted_data else []
        preview_rows = converted_data[1:6] if len(converted_data) > 1 else []
        total_rows = len(converted_data) - 1 if len(converted_data) > 0 else 0
        
        return jsonify({
            "success": True,
            "filename": sanitized_or_err,
            "delimiter_detected": detected_delimiter,
            "delimiter_name": delimiter_name,
            "total_rows": total_rows,
            "headers": headers,
            "preview_rows": preview_rows
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/json-preview/<filename>', methods=['GET'])
def json_preview(filename):
    """
    Endpoint 6 — JSON Preview
    """
    try:
        safe_name = secure_filename(filename)
        if safe_name != filename:
            return jsonify({"error": "Invalid filename requested"}), 400
            
        file_path = os.path.join(processed_data_path, safe_name)
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
            
        if not safe_name.lower().endswith('.json'):
            return jsonify({"error": "Invalid file extension, must be .json"}), 400
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if isinstance(data, dict):
            preview_data = [data]
            total_records = 1
            preview_records = 1
        elif isinstance(data, list):
            total_records = len(data)
            preview_records = min(10, total_records)
            preview_data = data[:10]
        else:
            return jsonify({"error": "Invalid JSON format"}), 500
            
        return jsonify({
            "success": True,
            "filename": safe_name,
            "total_records": total_records,
            "preview_records": preview_records,
            "data": preview_data
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api-docs', methods=['GET'])
def api_docs():
    """
    Endpoint 7 — API Documentation
    """
    return jsonify({
      "api_name": "DataDrop API",
      "version": "1.0.0",
      "base_url": "https://text-csv-json-converter.onrender.com",
      "endpoints": [
        {
          "method": "POST",
          "path": "/upload",
          "description": "Upload a file and convert it to all formats simultaneously",
          "rate_limit": "10 per minute",
          "accepts": "multipart/form-data with field name 'file'",
          "supported_types": [".txt", ".csv", ".tsv"],
          "max_file_size": "5MB",
          "returns": {
            "success": True,
            "input_file": "filename.txt",
            "outputs": ["filename.csv", "filename.xlsx", "filename.json", "filename_nested.json"],
            "processing_time_ms": 45
          }
        },
        {
          "method": "POST",
          "path": "/preview",
          "description": "Preview file headers and first 5 rows before converting",
          "rate_limit": "20 per minute",
          "accepts": "multipart/form-data with field name 'file'",
          "supported_types": [".txt", ".csv", ".tsv"],
          "returns": {
            "success": True,
            "filename": "data.txt",
            "delimiter_detected": "|",
            "delimiter_name": "Pipe",
            "total_rows": 245,
            "headers": ["COL1", "COL2"],
            "preview_rows": [["val1", "val2"]]
          }
        },
        {
          "method": "GET",
          "path": "/download/<filename>",
          "description": "Download a converted file by filename",
          "rate_limit": "200 per day",
          "returns": "File attachment"
        },
        {
          "method": "GET",
          "path": "/json-preview/<filename>",
          "description": "Preview the contents of a converted JSON file inline",
          "rate_limit": "200 per day",
          "returns": {
            "success": True,
            "filename": "data.json",
            "total_records": 245,
            "preview_records": 10,
            "data": []
          }
        },
        {
          "method": "GET",
          "path": "/stats",
          "description": "Get live conversion statistics",
          "rate_limit": "200 per day",
          "returns": {
            "files_converted": 745,
            "formats_supported": ["TXT", "CSV", "TSV", "XLSX", "JSON", "Nested JSON"],
            "processing_speed_ms": 120
          }
        },
        {
          "method": "GET",
          "path": "/health",
          "description": "Health check — confirms server is running",
          "rate_limit": "none",
          "returns": {
            "status": "running",
            "watcher": "active"
          }
        }
      ],
      "curl_examples": [
        {
          "title": "Convert a file",
          "command": "curl -X POST https://web-production-4ddc1.up.railway.app/upload -F 'file=@yourfile.csv'"
        },
        {
          "title": "Preview a file before converting",
          "command": "curl -X POST https://web-production-4ddc1.up.railway.app/preview -F 'file=@yourfile.csv'"
        },
        {
          "title": "Download converted file",
          "command": "curl -O https://web-production-4ddc1.up.railway.app/download/yourfile.json"
        },
        {
          "title": "Check server health",
          "command": "curl https://web-production-4ddc1.up.railway.app/health"
        }
      ],
      "javascript_examples": [
        {
          "title": "Convert a file with fetch",
          "code": "const formData = new FormData();\nformData.append('file', fileInput.files[0]);\nconst response = await fetch('https://web-production-4ddc1.up.railway.app/upload', {\n  method: 'POST',\n  body: formData\n});\nconst result = await response.json();\nconsole.log(result.outputs);"
        },
        {
          "title": "Preview a file before converting",
          "code": "const formData = new FormData();\nformData.append('file', fileInput.files[0]);\nconst response = await fetch('https://web-production-4ddc1.up.railway.app/preview', {\n  method: 'POST',\n  body: formData\n});\nconst preview = await response.json();\nconsole.log(preview.headers, preview.preview_rows);"
        }
      ]
    }), 200

@app.route('/samples', methods=['GET'])
def list_samples():
    """
    Endpoint 8 — List Sample Files
    """
    try:
        samples_dir = os.path.join(base_dir, "..", "data", "samples")
        if not os.path.exists(samples_dir):
            return jsonify({"success": True, "count": 0, "samples": []}), 200
            
        samples = []
        for filename in os.listdir(samples_dir):
            file_path = os.path.join(samples_dir, filename)
            if os.path.isfile(file_path):
                size_bytes = os.path.getsize(file_path)
                extension = filename.split('.')[-1] if '.' in filename else ''
                samples.append({
                    "filename": filename,
                    "extension": extension.lower(),
                    "size_bytes": size_bytes,
                    "size_kb": round(size_bytes / 1024, 1)
                })
                
        return jsonify({
            "success": True,
            "count": len(samples),
            "samples": samples
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/samples/<filename>', methods=['GET'])
def get_sample(filename):
    """
    Endpoint 9 — Get Sample File
    """
    try:
        safe_name = secure_filename(filename)
        if safe_name != filename:
            return jsonify({"error": "Invalid filename requested"}), 400
            
        samples_dir = os.path.join(base_dir, "..", "data", "samples")
        file_path = os.path.join(samples_dir, safe_name)
        
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
            
        ext = safe_name.split('.')[-1].lower() if '.' in safe_name else ''
        if ext not in ['txt', 'csv', 'tsv']:
            return jsonify({"error": "Invalid file extension requested"}), 400
            
        return send_from_directory(samples_dir, safe_name, as_attachment=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------------------------------------------------------------
# RUN SERVER
# -------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
