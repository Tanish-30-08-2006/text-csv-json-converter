import os
import csv
import sys
import time
import pandas as pd
import json
import argparse
from security import validate_and_sanitize_file

#--------------------------IMPORTS & PATH SETUP--------------------------#

# os      : lets Python talk to the operating system — file paths, directory navigation
# csv     : built-in module for reading and writing Comma Separated Values files
# sys     : gives access to command-line arguments passed when running the script
#           Example: python converter.py myfile.txt  ->  sys.argv[1] = "myfile.txt"
# pandas  : powerful data library — we use it to create DataFrames and export to Excel
# json    : built-in module for reading and writing JSON files

base_dir              = os.path.dirname(__file__)
raw_data_path         = os.path.join(base_dir, "..", "data", "raw")
processed_data_path   = os.path.join(base_dir, "..", "data", "processed")
samples_data_path     = os.path.join(base_dir, "..", "data", "samples")

# NOTE: csv_file_path, excel_file_path, json_file_path, nested_json_path are NO LONGER hardcoded here.
# They are now built dynamically inside main() based on the input file's name.

#--------------------------HELPER FUNCTIONS---------------------------------#


def detect_delimiter(first_line):
    """
    Given the FIRST LINE of a file as a plain string, figures out which
    delimiter (separator character) is being used — '|', ',', '\t', or ';'.

    Bug 10 fix: This function NO LONGER opens a file itself.
    The caller (read_any_file) now opens the file once, loads all lines,
    and passes line[0] here as a string — avoiding the double file-open.

    Returns the detected delimiter as a string character.
    Falls back to '|' if no candidate appears at all.
    """

    # These are the 4 most common delimiters used in data files:
    # '|'  pipe          -> used in our default watch_data
    # ','  comma         -> standard CSV files
    # '\t' tab           -> TSV files (Tab Separated Values)
    # ';'  semicolon     -> common in European CSV exports (Excel Germany, etc.)
    candidates = ['|', ',', '\t', ';']

    # Count how many times each candidate character appears in the first line.
    # str.count(char) returns an integer: how many times 'char' appears in the string.
    # Example: "W-101|Rolex|Daytona".count('|') -> 2
    #          "W-101|Rolex|Daytona".count(',') -> 0

    counts = {}
    for char in candidates:
        counts[char] = first_line.count(char)

    # max(counts, key=counts.get) finds the key (delimiter) with the highest count.
    # counts.get is a method reference — max() calls it on each key to compare values.
    # Example: counts = {'|': 5, ',': 0, '\t': 0, ';': 0}
    #          max(counts, key=counts.get) -> '|'
    detected = max(counts, key=counts.get)

    if counts[detected] == 0:
        # None of the candidates appear even once — very unusual file.
        # Fall back to pipe which is what our default watch_data uses.
        print("  [detect_delimiter] No known delimiter found — defaulting to '|'")
        return "|"

    print(f"  [detect_delimiter] Detected delimiter: '{detected}'  (appeared {counts[detected]} times in row 1)")
    return detected

    # ---- detect_delimiter: Syntax Reference ----
    #
    # def detect_delimiter(first_line):
    #   'def'        : keyword that tells Python "I am defining a function here"
    #   'first_line' : the parameter — a STRING (raw first line of the file).
    #                  Previously this was 'file_path'. Now the caller passes the line.
    #
    # candidates = ['|', ',', '\t', ';']
    #   A plain list of the 4 characters we check. '\t' is the escape sequence for Tab.
    #
    # counts = {}
    #   An empty dictionary. We'll fill it as: {'|': 5, ',': 0, '\t': 0, ';': 0}
    #   The key is the delimiter character, the value is how many times it appears.
    #
    # first_line.count(char)
    #   .count() is a built-in string method.
    #   It scans the string and counts exact matches of the given character.
    #
    # max(counts, key=counts.get)
    #   max() finds the largest item in a collection.
    #   By default max() on a dict compares keys alphabetically.
    #   'key=counts.get' tells max() to compare by VALUE (the count number) instead.
    #   It returns the KEY (delimiter) that has the highest value (count).
    #
    # if counts[detected] == 0
    #   After finding the 'max', we check if even that max is zero.
    #   If yes — no delimiter was found at all — we fall back to '|'.
    #
    # f"..." (f-string)
    #   A formatted string. Whatever is inside {} gets evaluated and inserted.
    #   f"Detected: '{detected}'" -> "Detected: '|'" if detected is '|'


def write_txt_file(data, output_path):
    """
    Writes a list of pipe-delimited strings to a .txt file.
    Each string in 'data' becomes one line in the file.
    This is used to save the hardcoded watch_data to disk.
    """

    with open(output_path, "w", encoding="utf-8") as tfp:
        tfp.writelines([line + "\n" for line in data])

    print(f"  [write_txt_file] Written -> {output_path}")

    # ---- write_txt_file: Syntax Reference ----
    #
    # def write_txt_file(data, output_path):
    #   'data'        : the list of strings to write (the watch_data list)
    #   'output_path' : the full file path where we want to save the .txt file
    #
    # open(output_path, "w")
    #   "w" mode = write mode. Creates the file if it doesn't exist.
    #   If the file already exists, it OVERWRITES it completely (no append).
    #
    # tfp.writelines([line + "\n" for line in data])
    #   writelines() writes every item in the list to the file, one after another.
    #   [line + "\n" for line in data] is a LIST COMPREHENSION —
    #   it loops through every string in 'data' and adds a newline character at the end.
    #   Without "\n", all lines would be mashed onto one single line in the file.
    #   Example: "W-101|Rolex" + "\n" -> "W-101|Rolex\n"


def read_any_file(file_path):
    """
    Reads ANY pipe-delimited, comma-delimited, tab-delimited, or semicolon-delimited
    text file and returns 'converted_data' — a list of lists.

    This replaces the old hardcoded open/read block.
    It auto-detects the delimiter using detect_delimiter() first.

    Bug 10 fix: File is opened ONCE using readlines().
    All lines load into memory. The first line is passed to detect_delimiter() as a string.
    No second file open needed — previously the file was opened twice per run.
    """

    # Step 1: Open the file ONCE and load all lines into memory.
    # readlines() reads the entire file and returns a LIST of strings, one per line.
    # Each string includes the '\n' newline character at the end.
    # After this with-block closes, the file is done — we work from 'all_lines' only.
    with open(file_path, "r", encoding="utf-8") as tfp1:
        all_lines = tfp1.readlines()

    # Step 2: Pass the first line as a string to detect_delimiter.
    # Previously: detect_delimiter(file_path) — opened the file AGAIN just to read line 1.
    # Now:        detect_delimiter(all_lines[0]) — line 1 is already in memory.
    # 'if all_lines else ""' guards against an empty file (all_lines would be []).
    first_line = all_lines[0] if all_lines else ""
    detected_delimiter = detect_delimiter(first_line)

    #for csv file we need to remove the delimiter and '\n' at the end of each line
    #as just pure rows without any interruption of characters..
    converted_data = []
    # in this converted_data we will store list of lists by .split which returns a list

    for line in all_lines:

        removed_new_line = line.strip()

        # Skip completely empty lines — they produce [''] which breaks downstream logic
        if not removed_new_line:
            continue

        # .split(detected_delimiter) cuts the string wherever it sees the delimiter
        # and returns a LIST
        # Example: "W-101|Rolex" -> ["W-101", "Rolex"]  (list of a row with separated elements)
        # Now it works for ANY delimiter, not just '|'
        split_data = removed_new_line.split(detected_delimiter)

        converted_data.append(split_data)

    print(f"  [read_any_file] Read {len(converted_data)} rows from -> {file_path}")
    return converted_data

    # ---- read_any_file: Syntax Reference ----
    #
    # tfp1.readlines()
    #   readlines() is a file method that reads the ENTIRE file at once.
    #   It returns a LIST of strings — one string per line, each ending with '\n'.
    #   Example: ["REF_ID|BRAND\n", "W-101|Rolex\n", ""]
    #   After this, the file is closed. We loop over 'all_lines', not the file handle.
    #
    # all_lines[0] if all_lines else ""
    #   all_lines[0] = the first string in the list = the first line of the file.
    #   'if all_lines' = truthy check: an empty list [] is False in Python.
    #   'else ""'      = if the file was completely empty, pass "" to avoid IndexError.
    #
    # detected_delimiter = detect_delimiter(first_line)
    #   We call our helper with a string now, not a file path.
    #   The result (a single character like '|' or ',') is stored in 'detected_delimiter'.
    #
    # if not removed_new_line: continue
    #   'if not ...' checks if the string is empty ("").
    #   An empty string evaluates to False in Python, so 'not ""' is True.
    #   'continue' tells the loop: "skip this iteration, move to the next line."
    #   This prevents blank lines at the end of a file from becoming [''] in our list.
    #
    # converted_data.append(split_data)
    #   .append() adds one item to the END of a list.
    #   After the loop, converted_data = [['REF_ID','BRAND',...], ['W-101','Rolex',...], ...]
    #
    # return converted_data
    #   'return' sends the result OUT of the function so the caller can use it.
    #   Without 'return', the variable stays trapped inside the function.


def check_header_row(converted_data):
    """
    Bug 8 fix — Header row assumed always present.

    Looks at the FIRST row of converted_data and decides:
    does it look like column headers, or like real data?

    Heuristic: if EVERY cell in the first row is a pure number,
    it's almost certainly data and NOT a header row.
    Prints a clear warning so the user knows before outputs are wrong.

    Returns True if it looks like a valid header, False if it looks like data.
    """

    if not converted_data:
        print("\n[ERROR] Conversion aborted: The input file is completely empty.")
        return False

    first_row = converted_data[0]

    # Try to convert each cell to a float (number).
    # If it succeeds -> the cell is numeric -> probably a data value, not a column name.
    # If it fails (ValueError) -> the cell is text -> almost certainly a header name.
    all_numeric = True

    for cell in first_row:

        try:
            float(cell.strip())
            # float() converts a string to a floating-point number.
            # float("72") -> 72.0   float("Rolex") -> ValueError
            # .strip() removes any leading/trailing whitespace before the check.

        except ValueError:
            # ValueError is raised when the string can't be converted to a number.
            # Example: float("REF_ID") raises ValueError.
            # The moment we find ONE non-numeric cell, we know it's likely a header.
            all_numeric = False
            break
            # 'break' exits the for loop immediately — no need to check remaining cells.

    if all_numeric:
        print("\n[WARNING] The first row of your file looks like DATA, not column headers.")
        print("          Example first row:", first_row)
        print("          If your file has no header row, column names will be wrong.")
        print("          Add a header row at the top of your file, then re-run.")
        return False

    return True

    # ---- check_header_row: Syntax Reference ----
    #
    # for cell in first_row:
    #   Loops through each string in the first row list.
    #   Example: first_row = ['REF_ID', 'Rolex', '72'] -> checks 'REF_ID', then 'Rolex', etc.
    #
    # try / except ValueError:
    #   'try'   : attempt the conversion. If it works, the cell IS a number.
    #   'except': if float() raises a ValueError, the cell is text -> it's a header.
    #
    # all_numeric = True / False
    #   We start assuming all cells are numeric (True).
    #   If we find even one non-numeric cell, we set it to False and break out.
    #
    # break
    #   Immediately stops the for loop. No need to check more cells once we know
    #   at least one header-like cell exists.


#--------------------------CONVERSION FUNCTIONS-----------------------------#


def convert_to_csv(converted_data, output_path):
    """
    Takes 'converted_data' (list of lists) and writes it as a .csv file.
    The first inner list is treated as the header row.
    """

    # now write converted data into csv file ...

    #csv file is a COMMA SEPARATED VALUES FILE
    # tables where next box is separated by comma in a row..

    with open(output_path, "w", newline='', encoding="utf-8") as csv_file:

        writer = csv.writer(csv_file, delimiter=",")

        writer.writerows(converted_data)

    print(f"  [convert_to_csv] Written -> {output_path}")

    #----------csv functions-------------#

    #  csv.writer(file_object, delimiter=',')
    # This function creates a Writer Object.
    # Think of the file_object as the "Paper" you are writing on.
    # Think of the writer as the "Special Pen" that knows the rules of CSV.
    # delimiter: This tells the pen what symbol to use to separate the boxes. By default, it's a comma.

    #   writer.writerow(list)
    # This takes a single list (one row) and writes it to the file.
    # If you give it ['W-101', 'Rolex'], the "Special Pen" writes W-101,Rolex to the file
    # and handles all the formatting rules.

    # writer.writerows(list_of_lists)
    # This is the "Turbo" version. It takes your Master List (converted_data) and loops through every internal list for you, writing them row by row. This is what you should use for your converted_data.

    # Why newline=''?
    # Python's open() function and the csv library both try to manage line endings. If you don't include newline='',
    # some systems (especially Windows) will add an extra blank line between every row of your data.
    # This makes the Excel sheet look like it has empty rows between every watch.


def convert_to_excel(converted_data, output_path):
    """
    Takes 'converted_data' (list of lists) and exports it to an Excel .xlsx file.
    Uses pandas DataFrame as the bridge — handles data typing and compression.
    """

    # -----------------------------CONVERSION TO EXCEL BY PANDAS-------------------------#

    #Pandas acts as the translator. It takes your list, organizes it into a DataFrame,
    # and then uses an "Engine" (like openpyxl) to pack it into an Excel file.

    #Initialize the DataFrame
    # We pass 'converted_data' which is your list of lists.
    # Since the first list in 'converted_data' contains the headers,
    # Pandas is smart enough to see that, but we can be explicit:

    df = pd.DataFrame(converted_data[1:], columns=converted_data[0])

    # converted_data[1:]  -> This tells Pandas: "Use everything from the second row onwards as data"
    # columns=converted_data[0] -> This tells Pandas: "Use the very first row as my table headers"

    #  Write to Excel
    # index=False is VITAL. If you set it to True, Excel will add a 0, 1, 2 column on the left.
    df.to_excel(output_path, index=False, engine='openpyxl')

    print(f"  [convert_to_excel] Written -> {output_path}")

    # By using df.to_excel(), you are doing more than just saving text. You are creating a file that:
    # Recognizes Data Types: Excel will now know that "2005" is a number, allowing you to sort it chronologically immediately.
    # Is Compressed: .xlsx files are actually zipped, so they take up less space than a massive .txt file for huge datasets.

    #-------diff between csv excel json--------------#

    # Why move to Excel in your project?
    # If a CSV can look like a table, why did we bother with the Pandas step to create an .xlsx?

    # Data Types: In a CSV, everything is technically a "string" (text). In Excel, Pandas tells the file: "This column is a Number, and this column is a Date." This makes sorting much faster.

    # Protection: You can password-protect an Excel file; you can't do that with a CSV.

    # Multiple Sheets: An Excel file can have "Sheet1", "Sheet2", and "Sheet3". A CSV can only ever have one single table.

    # Feature,   CSV (Comma Separated Values),                        Excel (.xlsx)
    # What it is,A plain text file.,                                  A complex binary/XML file.
    # How it's stored,Data is separated by commas (or pipes).,        "Data is stored in a compressed ""workbook"" format."
    # Memory/Size,Very small and lightweight.,                        "Larger because it stores ""metadata"" (formatting)."
    # Capabilities,Stores only raw data.,                             "Stores formulas, charts, bold text, and colors."
    # Compatibility,Universal (any text editor can open it            "Requires specific software (Excel, Numbers, Pandas)."


def convert_to_json_flat(converted_data, output_path):
    """
    Converts 'converted_data' into a flat (un-nested) JSON file.
    Each row becomes one dictionary with headers as keys.
    """

    #----------------------------------CONVERSION TO JSON FILE-----------------------------------#

    # What is JSON?
    # JSON stands for JavaScript Object Notation.
    # Unlike a CSV, which stores data in rows and columns, JSON stores data in Key-Value Pairs

    headers   = converted_data[0]
    data_rows = converted_data[1:]

    #  Create a List of Dictionaries
    # We 'zip' the header with each row to create Key-Value pairs
    # Example: zip(['BRAND'], ['Rolex']) -> {'BRAND': 'Rolex'}

    #---------Simple json file(un-nested)----------------#
    json_list = []
    for row in data_rows:

        # ---- Bug 11 fix: Handle ragged rows (missing columns) ----
        # If a row has fewer items than the headers, zip() silently drops the extra headers.
        # Example: headers=['A','B','C'], row=['1','2'] -> dict is {'A':'1', 'B':'2'}. 'C' is lost.
        # Fix: Pad the row with empty strings "" until it matches the length of the headers.
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))

        single_row_dict = dict(zip(headers, row))
        json_list.append(single_row_dict)

    with open(output_path, "w", encoding="utf-8") as jf:
        # indent=4 makes the file 'Pretty' and readable for JSON Crack
        # sort_keys=False keeps the columns in the same order as our CSV
        json.dump(json_list, jf, indent=4, sort_keys=False)

    print(f"  [convert_to_json_flat] Written -> {output_path}")

    # ---------- JSON Functions & Definitions ------------- #

    # json.dump(data, file_object):
    # This 'pours' your Python list/dictionary into a physical file.

    # indent=4:
    # Adds 4 spaces of 'nesting' so humans can read the hierarchy.
    # Without this, the whole file would be one single line (indent=None).

    # indent = none means everything will be in one line
    #[{"REF_ID":"W-101","BRAND":"Rolex"},{"REF_ID":"W-102","BRAND":"Tudor"}]

    # indent=4 (Pretty-Printed)
    # This is the "human-optimized" version. Every time Python sees a new level of data (like entering a dictionary), it adds 4 spaces to the margin.

    # Calculation: * Root level [: 0 spaces.

    # First level {: 4 spaces.

    # Data inside {: 8 spaces (if nested further).

    # Look: It creates a clear "staircase" effect that makes it easy to see where one watch ends and the next begins.

    # zip(headers, row):
    # Pairs up items like a zipper.
    # It takes the 1st item of 'headers' and pairs it with the 1st item of 'row'.


def convert_to_json_nested(converted_data, output_path):
    """
    Converts 'converted_data' into a NESTED JSON file.

    GENERIC — works with ANY dataset, any number of columns.
    Groups rows by the FIRST column's value.
    All remaining columns become key-value pairs inside that group.

    Example — students data:
        Input row : ['S-001', 'Alice', 'Math', 'A', '95', '2024']
        Headers   : ['STUDENT_ID', 'NAME', 'SUBJECT', 'GRADE', 'MARKS', 'YEAR']
        Output    : { "S-001": { "NAME": "Alice", "SUBJECT": "Math", ... } }
    """

    #-----------nested json file (generic)------------#

    headers   = converted_data[0]        # ['STUDENT_ID', 'NAME', 'SUBJECT', ...]
    # Bug 9 fix: Removed 'group_key' variable that was declared but never used.
    detail_headers = headers[1:]         # remaining headers = the nested field names

    nested_data = {}  # this will be key pair as ["first-column-value" : "details dict"]

    for row in converted_data[1:]:

        key_value      = row[0]          # the value of the first column (e.g. 'S-001')
        detail_values  = row[1:]         # all remaining values (e.g. ['Alice', 'Math', ...])

        # ---- Bug 11 fix: Handle ragged rows for nested JSON too ----
        # Pad detail_values with empty strings if it's shorter than detail_headers.
        if len(detail_values) < len(detail_headers):
            detail_values = detail_values + [""] * (len(detail_headers) - len(detail_values))

        # created a small dictionary pairing each detail header with its value
        # zip(detail_headers, detail_values) pairs them up like a zipper
        # Example: zip(['NAME','SUBJECT'], ['Alice','Math']) -> {'NAME':'Alice', 'SUBJECT':'Math'}
        row_details = dict(zip(detail_headers, detail_values))

        if key_value not in nested_data:
            # If it's a new key, initialise it as an empty LIST (not a dict).
            # A list lets us safely store MULTIPLE rows that share the same key
            # without the second row silently overwriting the first.
            # Example: weather data where all rows share the same DATE key.
            nested_data[key_value] = []

        # .append() adds this row's details to the list for this key.
        # If the key is unique (like a student ID), the list will have just 1 item.
        # If the key repeats (like a shared DATE), the list grows — no data is lost.
        nested_data[key_value].append(row_details)  # details appended to the grouping key

    with open(output_path, "w", encoding="utf-8") as njf:

        # We use indent=4 to make the nesting visible
        json.dump(nested_data, njf, indent=4)

    print(f"  [convert_to_json_nested] Written -> {output_path}")

    # ---- convert_to_json_nested: Syntax Reference ----
    #
    # headers[0]     : index 0 of a list = the very first item
    # headers[1:]    : slice from index 1 to the end = everything EXCEPT the first item
    # row[0]         : same idea — first element of the row list (the grouping key value)
    # row[1:]        : everything after the first element (the detail values)
    #
    # dict(zip(detail_headers, detail_values))
    #   zip() pairs up two lists element by element like a zipper
    #   dict() converts those pairs into a dictionary
    #   Example: zip(['NAME','GRADE'], ['Alice','A']) -> [('NAME','Alice'), ('GRADE','A')]
    #            dict([...])                          -> {'NAME': 'Alice', 'GRADE': 'A'}
    #
    # nested_data[key_value] = {}
    #   Creating a new empty dictionary at that key position, ready to be filled.
    #
    # nested_data[key_value] = row_details
    #   Assigning the details dict to the grouping key in the outer dict.

def convert_json_to_csv(json_path, csv_path):
    """
    Phase 3: Reverse Engine
    Reads a flat JSON file (list of dictionaries) and converts it back into a CSV.
    Dynamically extracts headers from the keys of the first dictionary.
    """
    print("\n[REVERSE ENGINE] Reading JSON file...")
    with open(json_path, "r", encoding="utf-8") as jf:
        data = json.load(jf)
        
    if not isinstance(data, list) or len(data) == 0:
        print(f"  [ERROR] JSON file empty or not a flat list of dictionaries.")
        sys.exit(1)
        
    # --- BUG 3 FIX: Extract headers from ALL dictionaries to catch every possible key ---
    # We loop through all dictionaries to find unique keys, preserving order where possible.
    headers = []
    for row_dict in data:
        for key in row_dict.keys():
            if key not in headers:
                headers.append(key)
    
    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        writer = csv.DictWriter(cf, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)
        
    print(f"  [REVERSE ENGINE] Written -> {csv_path}")


def convert_file_for_web(input_path, output_dir):
    """
    Web-callable function that runs the full conversion pipeline and returns
    a dictionary with success status, generated files, and processing time.
    """
    start_time = time.time()
    try:
        converted_data = read_any_file(input_path)
        if not check_header_row(converted_data):
            return {
                "success": False,
                "input_file": os.path.basename(input_path),
                "outputs": [],
                "error": "Conversion aborted due to missing header row.",
                "processing_time_ms": int((time.time() - start_time) * 1000)
            }
        
        input_stem = os.path.splitext(os.path.basename(input_path))[0]
        csv_file = f"{input_stem}.csv"
        excel_file = f"{input_stem}.xlsx"
        json_flat_file = f"{input_stem}.json"
        json_nested_file = f"{input_stem}_nested.json"

        convert_to_csv(converted_data, os.path.join(output_dir, csv_file))
        convert_to_excel(converted_data, os.path.join(output_dir, excel_file))
        convert_to_json_flat(converted_data, os.path.join(output_dir, json_flat_file))
        convert_to_json_nested(converted_data, os.path.join(output_dir, json_nested_file))

        return {
            "success": True,
            "input_file": os.path.basename(input_path),
            "outputs": [csv_file, excel_file, json_flat_file, json_nested_file],
            "error": None,
            "processing_time_ms": int((time.time() - start_time) * 1000)
        }
    except Exception as e:
        return {
            "success": False,
            "input_file": os.path.basename(input_path),
            "outputs": [],
            "error": str(e),
            "processing_time_ms": int((time.time() - start_time) * 1000)
        }

#--------------------------MAIN EXECUTION-----------------------------------#

# This is the entry point of the entire script.
# main() orchestrates everything — it decides the input file, then calls
# each conversion function in sequence.
#
# HOW TO RUN:
#   Default (uses built-in watch data):
#       python src/converter.py
#
#   Custom file (your own .txt, .csv, or any delimited file):
#       python src/converter.py path/to/your_file.txt
#
# sys.argv is a LIST of command-line arguments.
#   sys.argv[0] = the script name itself ("converter.py")
#   sys.argv[1] = the FIRST argument the user typed after the script name
#   len(sys.argv) > 1 checks: "did the user pass anything extra?"

def main():

    print("\n" + "="*55)
    print("   UNIVERSAL FILE FORMAT CONVERTER")
    print("   TXT / CSV / TSV <--> JSON / XLSX")
    print("="*55)

    # ---- Phase 3: Setup argparse CLI ----
    parser = argparse.ArgumentParser(
        description="Universal File Format Converter: Text/CSV to multiple formats, or JSON to CSV.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument("input_file", nargs="?", default=None,
                        help="Path to input file (e.g., data/samples/students.txt). If omitted, uses built-in demo data.")
    
    # Toggle flags for specific outputs
    parser.add_argument("--csv", action="store_true", help="Generate CSV output")
    parser.add_argument("--excel", action="store_true", help="Generate Excel (.xlsx) output")
    parser.add_argument("--json", action="store_true", help="Generate flat JSON output")
    parser.add_argument("--nested", action="store_true", help="Generate nested JSON output")
    
    # Reverse mode flag
    parser.add_argument("--reverse", action="store_true", help="Run in reverse mode: convert flat JSON back to CSV")

    args = parser.parse_args()

    # Determine which formats to generate
    specific_requested = args.csv or args.excel or args.json or args.nested
    
    # If no specific output flag is provided and we are NOT in reverse mode, generate all 4 formats.
    generate_csv    = args.csv    or (not specific_requested and not args.reverse)
    generate_excel  = args.excel  or (not specific_requested and not args.reverse)
    generate_json   = args.json   or (not specific_requested and not args.reverse)
    generate_nested = args.nested or (not specific_requested and not args.reverse)


    # ---- Step 1: Decide which input file to use ----
    if args.input_file:
        input_file = args.input_file
        print(f"\n[INPUT] Custom file provided: {input_file}")

        if not os.path.exists(input_file):
            print(f"\n[ERROR] File not found: '{input_file}'")
            print("        Check the path and make sure the file exists.")
            sys.exit(1)

        # --- BUG 4 FIX: The Directory Imposter Crash ---
        if os.path.isdir(input_file):
            print(f"\n[ERROR] You provided a directory: '{input_file}'")
            print("        Please provide the path to a specific file instead.")
            sys.exit(1)

        # --- SECURITY PHASE FIX: Strict Input Validation & Sanitization ---
        # Before we even process the extension, we run it through our strict security module.
        # This checks against file size limit, malicious extensions, and sanitizes characters.
        # We assume size is safely under limit for local CLI, but validate string.
        filename_only = os.path.basename(input_file)
        file_sz = os.path.getsize(input_file)
        is_safe, sanitized_name_or_err = validate_and_sanitize_file(filename_only, file_size=file_sz)
        
        if not is_safe:
            print(f"\n[SECURITY BLOCKED] {sanitized_name_or_err}")
            sys.exit(1)
            

        # In reverse mode, we strictly need a .json file.
        # In normal mode, we need .txt, .csv, or .tsv.
        _, file_ext = os.path.splitext(input_file)
        
        if args.reverse:
            if file_ext.lower() != '.json':
                print(f"\n[ERROR] Reverse mode requires a .json file. You provided: '{file_ext}'")
                sys.exit(1)
        else:
            allowed_extensions = ['.txt', '.csv', '.tsv']
            if file_ext.lower() not in allowed_extensions:
                print(f"\n[ERROR] Unsupported file type: '{file_ext}'")
                print(f"        Allowed types for normal conversion: {allowed_extensions}")
                sys.exit(1)
    else:
        if args.reverse:
            print("\n[ERROR] Reverse mode requires an explicit input .json file.")
            sys.exit(1)
            
        # No argument passed -> fall back to default hardcoded demo watch_data
        watch_data = [
            "REF_ID|BRAND|MODEL|MOVEMENT|POWER_RESERVE_HRS|YEAR_INTRODUCED",
            "W-101|Patek Philippe|Grand Complications|Manual|72|2005",
            "W-202|Rolex|Cosmograph Daytona|Automatic|72|1963",
            "W-303|Audemars Piguet|Royal Oak|Automatic|60|1972",
            "W-505|A. Lange & Sohne|Lange 1|Manual|72|1994"
        ]
        text_file_path = os.path.join(raw_data_path, "demo_data.txt")
        
        print("\n[INPUT] No file provided — using compact built-in demo data")
        print("        Tip: pass any sample file → python src/converter.py data/samples/students.txt")
        write_txt_file(watch_data, text_file_path)
        input_file = text_file_path

    # ---- Bug 5 fix: Auto-create the processed/ folder if it doesn't exist ----
    # On a fresh clone, data/processed/ might not exist yet.
    # Without this line, every open(output_path, "w") would crash immediately.
    #
    # os.makedirs(path, exist_ok=True)
    #   makedirs() creates the folder AND any missing parent folders in the path.
    #   exist_ok=True means: "if the folder already exists, do NOT raise an error — just continue."
    #   Without exist_ok=True, running the script twice would crash on the second run.
    os.makedirs(processed_data_path, exist_ok=True)
    os.makedirs(raw_data_path, exist_ok=True)

    # ---- Step 2: Build output paths dynamically from the input file's name ----

    # os.path.basename() strips the folder path and returns just the filename
    # Example: "data/samples/students.txt" -> "students.txt"
    input_filename = os.path.basename(input_file)

    # os.path.splitext() splits a filename into (name, extension) tuple
    # Example: "students.txt" -> ("students", ".txt")
    # [0] takes the name part only, ignoring the extension
    input_stem = os.path.splitext(input_filename)[0]

    # Now build all 4 output paths using the input file's name as a prefix
    # This ensures each input file gets its own set of outputs in data/processed/
    csv_file_path    = os.path.join(processed_data_path, f"{input_stem}.csv")
    excel_file_path  = os.path.join(processed_data_path, f"{input_stem}.xlsx")
    json_file_path   = os.path.join(processed_data_path, f"{input_stem}.json")
    nested_json_path = os.path.join(processed_data_path, f"{input_stem}_nested.json")
    reverse_csv_path = os.path.join(processed_data_path, f"{input_stem}_reversed.csv")

    # ---- Phase 3: Execute Reverse Mode ----
    if args.reverse:
        print(f"\n[REVERSE MODE] Converting JSON -> CSV")
        convert_json_to_csv(input_file, reverse_csv_path)
        
        print("\n" + "="*55)
        print("   REVERSE CONVERSION COMPLETE")
        print(f"   Input : {input_file}")
        print(f"   Output: {reverse_csv_path}")
        print("="*55 + "\n")
        sys.exit(0)

    # ---- Normal Mode Output Logging ----
    print(f"\n[OUTPUT] Files to be generated:")
    if generate_csv:    print(f"         {input_stem}.csv")
    if generate_excel:  print(f"         {input_stem}.xlsx")
    if generate_json:   print(f"         {input_stem}.json")
    if generate_nested: print(f"         {input_stem}_nested.json")

    # ---- Step 3: Read & parse the input file ----
    # detect_delimiter() runs inside read_any_file() automatically

    print("\n[STEP 1] Reading input file...")
    converted_data = read_any_file(input_file)

    # ---- Check headers and actually stop if it fails ----
    is_valid_header = check_header_row(converted_data)
    if not is_valid_header:
        print("\n[ERROR] Conversion aborted due to missing header row.")
        sys.exit(1)

    # ---- Step 4: Run all conversions based on format flags ----

    if generate_csv:
        print("\n[STEP 2] Converting to CSV...")
        convert_to_csv(converted_data, csv_file_path)
    else:
        print("\n[STEP 2] CSV skipped (flag not provided)")

    if generate_excel:
        print("\n[STEP 3] Converting to Excel...")
        convert_to_excel(converted_data, excel_file_path)
    else:
        print("\n[STEP 3] Excel skipped (flag not provided)")

    if generate_json:
        print("\n[STEP 4] Converting to flat JSON...")
        convert_to_json_flat(converted_data, json_file_path)
    else:
        print("\n[STEP 4] Flat JSON skipped (flag not provided)")

    if generate_nested:
        print("\n[STEP 5] Converting to nested JSON...")
        convert_to_json_nested(converted_data, nested_json_path)
    else:
        print("\n[STEP 5] Nested JSON skipped (flag not provided)")


    # ---- Accurate final summary ----
    print("\n" + "="*55)
    print("   ALL CONVERSIONS COMPLETE")
    print(f"   Input : {input_file}")
    
    generated = []
    if generate_csv:    generated.append(f"{input_stem}.csv")
    if generate_excel:  generated.append(f"{input_stem}.xlsx")
    if generate_json:   generated.append(f"{input_stem}.json")
    if generate_nested: generated.append(f"{input_stem}_nested.json")
    
    if generated:
        print("   Generated Files in data/processed/:")
        for g in generated:
            print(f"      - {g}")
    else:
        print("   No files generated (all output flags set to False).")
    
    print("="*55 + "\n")


# ---- if __name__ == "__main__" ----
#
# This is a Python safety guard.
# When Python runs a file directly (python converter.py), it sets the special
# variable __name__ to the string "__main__".
# When a file is IMPORTED by another file (import converter), __name__ is set
# to the module name ("converter") instead.
#
# So this block says: "Only run main() if THIS file is the one being executed directly.
# Don't run it automatically if someone else just imports this file."
# This makes the code safe to import as a module in future phases.

if __name__ == "__main__":
    main()