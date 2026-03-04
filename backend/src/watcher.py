import os
import sys
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import the main logic from our converter script
# This allows the watcher to directly pass the file to converter.py without opening a new terminal
from converter import read_any_file, check_header_row, convert_to_csv, convert_to_excel, convert_to_json_flat, convert_to_json_nested
from security import validate_and_sanitize_file

# Setup paths based on where this script lives
base_dir = os.path.dirname(__file__)
raw_data_path = os.path.join(base_dir, "..", "data", "raw")
processed_data_path = os.path.join(base_dir, "..", "data", "processed")
logs_dir = os.path.join(base_dir, "..", "logs")

# Ensure the folders exist before we try to watch or write to them
os.makedirs(raw_data_path, exist_ok=True)
os.makedirs(processed_data_path, exist_ok=True)
os.makedirs(logs_dir, exist_ok=True)

# -------------------------------------------------------------------------#
# LOGGER SETUP (Fix 7)
# -------------------------------------------------------------------------#
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(logs_dir, "watcher.log")),
        logging.StreamHandler()
    ]
)

# -------------------------------------------------------------------------#
# LAYER 4: THE TRIGGER SEQUENCE 
# -------------------------------------------------------------------------#
# 1. OS Detects File: You drag "sales.csv" into the data/raw/ folder. Windows OS notices this.
# 2. OS Notifies Watchdog: Windows sends an internal signal to the Python `Observer` running below.
# 3. Observer Checks Instructions: The Observer looks at the `ConvertOnDrop` class below.
# 4. Trigger Fired: Because a file was created, watchdog automatically calls `on_created(event)`.
# 5. Conversion: Inside `on_created`, we get the file path (`event.src_path`), check if it's 
#    finished copying, and instantly pass it to our converter functions.
# -------------------------------------------------------------------------#

class ConvertOnDrop(FileSystemEventHandler):
    """
    The 'Instruction Manual' for the Observer. 
    Defines exactly what happens when a file is created, modified, or deleted in the folder.
    """

    def __init__(self):
        super().__init__()
        # Track when files were last processed to ignore multiple rapid triggers from a single save.
        self.last_processed = {}
        self.DEBOUNCE_SECONDS = 2.0

    def should_process(self, file_path):
        current_time = time.time()
        
        # --- FIX 6: Memory Leak Prevention ---
        # Remove entries from the tracking dict that are older than 60 seconds
        keys_to_delete = [path for path, timestamp in self.last_processed.items() if current_time - timestamp > 60]
        for key in keys_to_delete:
            del self.last_processed[key]
            
        # If triggered recently, ignore to prevent "machine gun" duplicate conversions
        if file_path in self.last_processed:
            if current_time - self.last_processed[file_path] < self.DEBOUNCE_SECONDS:
                return False
        
        self.last_processed[file_path] = current_time
        return True

    def on_created(self, event):
        # Stop if the user created a new folder instead of a file
        if event.is_directory:
            return
            
        if not self.should_process(event.src_path):
            return
            
        logging.info(f"[WATCHER] 🚨 TRIGGER FIRED: New file detected -> {event.src_path}")
        self.process_file(event.src_path)

    def on_modified(self, event):
        # Handle file edits
        if event.is_directory:
            return
            
        if not self.should_process(event.src_path):
            return
            
        logging.info(f"[WATCHER] 🚨 TRIGGER FIRED: File modified -> {event.src_path}")
        self.process_file(event.src_path)

    def process_file(self, input_file):
        
        # --- FIX 5: Add security validation before processing ---
        filename_only = os.path.basename(input_file)
        
        try:
            file_sz = os.path.getsize(input_file)
        except OSError:
            file_sz = 0
            
        is_safe, err_msg = validate_and_sanitize_file(filename_only, file_size=file_sz)
        if not is_safe:
            logging.warning(f"[WATCHER] ❌ SECURITY BLOCKED: {err_msg}")
            return
            
        # --- EDGE CASE 1 & BUG 1 FIX: Large File Copying / Cancelled Drop ---
        # If the user drops a 1GB file, Windows fires instantly.
        # If the user cancels the copy, the file vanishes. We catch OSError to prevent a fatal crash.
        previous_size = -1
        try:
            while True:
                current_size = os.path.getsize(input_file)
                if current_size == previous_size:
                    break # Size stopped changing, copy is complete!
                previous_size = current_size
                time.sleep(0.5) # Wait half a second and check again
        except OSError:
            logging.warning("[WATCHER] ❌ File vanished before reading (Copy cancelled). Ignoring.")
            return # Safely exit the event, keep watcher alive

        logging.info("[WATCHER] ✅ File ready. Beginning conversion...")

        # --- EDGE CASE 2: Unsupported File Types ---
        # Only process text files. If it's a picture, ignore it.
        allowed_extensions = ['.txt', '.csv', '.tsv']
        _, file_ext = os.path.splitext(input_file)
        
        if file_ext.lower() not in allowed_extensions:
            logging.warning(f"[WATCHER] ❌ Ignored unsupported file type: {file_ext}")
            return # Stop right here, don't crash the watcher

        # ---- THE CONVERSION LOGIC ----
        try:
            # We are calling the functions we built in Phase 2 directly!
            # This is why we modularised the code.
            converted_data = read_any_file(input_file)
            
            if not check_header_row(converted_data):
                logging.error("[WATCHER] ❌ Conversion aborted: Missing header row.")
                return

            input_stem = os.path.splitext(os.path.basename(input_file))[0]
            
            # Generate all outputs
            convert_to_csv(converted_data, os.path.join(processed_data_path, f"{input_stem}.csv"))
            convert_to_excel(converted_data, os.path.join(processed_data_path, f"{input_stem}.xlsx"))
            convert_to_json_flat(converted_data, os.path.join(processed_data_path, f"{input_stem}.json"))
            convert_to_json_nested(converted_data, os.path.join(processed_data_path, f"{input_stem}_nested.json"))
            
            logging.info(f"[WATCHER] 🎉 Auto-conversion successful for: {input_stem}")
            logging.info("-" * 60)

        except Exception as e:
            # --- EDGE CASE 3: Bad Data Crash ---
            # If the file is deeply corrupted, converter might throw a Python error.
            # We catch it here so the watcher STAYS ALIVE for the next file.
            logging.error(f"[WATCHER] 💥 ERROR during conversion: {e}")
            logging.error("-" * 60)

#--------------------------MAIN EXECUTION-----------------------------------#

if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info("   FILE WATCHER STARTED")
    logging.info(f"   Listening for drops in: {raw_data_path}")
    logging.info("   Press Ctrl+C to stop.")
    logging.info("=" * 60)

    # 1. Create the Instruction Manual
    event_handler = ConvertOnDrop()
    
    # 2. Create the Security Guard (Observer)
    observer = Observer()
    
    # 3. Tell the Guard what to monitor (the folder) and what manual to use
    observer.schedule(event_handler, path=raw_data_path, recursive=False)
    
    # 4. Start the Guard
    observer.start()

    # 5. LAYER 3: The Infinite Loop
    # Keep the main Python script running forever so the Observer stays alive.
    # time.sleep(1) prevents the script from using 100% CPU while doing nothing.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # If the user presses Ctrl+C in the terminal, cleanly shut down the guard
        logging.info("[WATCHER] Shutting down...")
        observer.stop()
    
    # Wait for the guard thread to fully finish before closing Python
    observer.join()
