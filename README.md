# 🕰️ Text → CSV → JSON Converter

A Python mini-project that demonstrates multi-format data conversion.  
Takes pipe-delimited raw text data and converts it into **CSV**, **Excel (.xlsx)**, **flat JSON**, and **nested JSON**.

---

## 📁 Project Structure

```
text-csv-json-converter/
├── src/
│   ├── __init__.py
│   └── converter.py        # Main conversion script
├── data/
│   ├── raw/
│   │   └── txt_file_.txt   # Source pipe-delimited text file (generated)
│   └── processed/
│       ├── watches_csv_file_.csv
│       ├── watches_.exel_file_.xlsx
│       ├── watches_.json
│       └── nested_watches_.json
├── requirements.txt
├── .gitignore
└── README.md
```

---

## ⚙️ What It Does

| Step | Input          | Output           | Method                           |
| ---- | -------------- | ---------------- | -------------------------------- |
| 1    | Delimited file | `.csv`           | Custom parsing + `csv` module    |
| 2    | Delimited file | `.xlsx` (Excel)  | `pandas` + `openpyxl`            |
| 3    | Delimited file | flat `.json`     | `json.dump()`                    |
| 4    | Delimited file | nested `.json`   | `json.dump()` with dict grouping |
| 5    | flat `.json`   | `.csv` (Reverse) | `csv.DictWriter`                 |

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/saumya-singh/text-csv-json-converter.git
cd text-csv-json-converter
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Usage & CLI Flags

The script now uses a robust command-line interface. By default, running it on an input file generates _all_ formats.

**Basic Conversion (All formats):**

```bash
python src/converter.py data/samples/employees.csv
```

**Selective Conversion (Only generate specific files):**

```bash
python src/converter.py data/samples/movies.txt --json --excel
```

**Reverse Conversion (JSON → CSV):**

```bash
python src/converter.py data/processed/employees.json --reverse
```

**Run Automated Background Watcher:**

```bash
python src/watcher.py
```

_(Leave this running. Any file dropped into `data/raw/` will automatically convert into all 4 formats in `data/processed/`)_

**View Help Page:**

```bash
python src/converter.py --help
```

All output files will be automatically generated inside the `data/processed/` folder.

---

## 📦 Dependencies

| Package    | Purpose                             |
| ---------- | ----------------------------------- |
| `pandas`   | DataFrame creation and Excel export |
| `openpyxl` | Excel file engine used by pandas    |

> Python's built-in `csv` and `json` modules are used for CSV and JSON — no extra install needed.

---

## 🗂️ Output Examples

**Flat JSON** (`watches_.json`)

```json
[
  {
    "REF_ID": "W-202",
    "BRAND": "Rolex",
    "MODEL": "Cosmograph Daytona",
    "MOVEMENT": "Automatic",
    "POWER_RESERVE_HRS": "72",
    "YEAR_INTRODUCED": "1963"
  }
]
```

**Nested JSON** (`nested_watches_.json`)

```json
{
  "E-1002": {
    "FULL_NAME": "Raj Mehta",
    "DEPARTMENT": "Engineering",
    "ROLE": "DevOps Engineer",
    "SALARY_USD": "88000",
    "JOINING_YEAR": "2020"
  }
}
```

---

## 📌 Notes

- The project dynamically handles `|`, `,`, `\t`, and `;` delimiters.
- If no input file is passed, it falls back to a built-in "luxury watch" demo dataset.
- All files in `data/processed/` are auto-generated and excluded from version control via `.gitignore`.

---

## 🛣️ Roadmap

- [x] Phase 1: Initial concept & basic manual workflow
- [x] Phase 2: Refactor, dynamic delimiter detection, handle any input file, robust error handling
- [x] Phase 3: CLI with `argparse`, selective format generation, and JSON -> CSV Reverse Conversion Engine
- [x] Phase 4: File Watcher / Background Daemon (auto-processes anything dropped into `data/raw/`)
- [ ] Phase 5: Flask/FastAPI Web UI for drag-and-drop conversion
