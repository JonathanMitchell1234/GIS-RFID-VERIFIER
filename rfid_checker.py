import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import os


def strip_last_five(value: str) -> str:
    """Remove the last 5 characters from a string."""
    return value[:-5] if len(value) >= 5 else value


def process_file(filepath: str) -> tuple:
    """
    Read the CSV file and compare toterfidserial (with trailing numbers stripped)
    to toteserial. Returns (total_rows, matches, mismatches) where mismatches is
    a list of dicts with row info.
    """
    # Read the CSV file
    df = pd.read_csv(filepath, dtype=str)

    # Check required columns exist
    required = {'toterfidserial', 'toteserial'}
    missing = required - set(df.columns.str.lower())
    if missing:
        raise ValueError(
            f"Missing required columns: {', '.join(sorted(missing))}\n"
            f"Found columns: {', '.join(df.columns)}"
        )

    # Normalise column names to lowercase for case-insensitive access
    df.columns = df.columns.str.lower()

    mismatches = []
    matches = 0

    for idx, row in df.iterrows():
        raw = str(row['toterfidserial']).strip()
        toteserial = str(row['toteserial']).strip()

        stripped = strip_last_five(raw)

        if stripped == toteserial:
            matches += 1
        else:
            mismatches.append({
                'row': idx + 2,  # +1 for header, +1 for 0-index
                'toterfidserial_raw': raw,
                'toterfidserial_stripped': stripped,
                'toterfidserial_last5': raw[-5:] if len(raw) >= 5 else raw,
                'toteserial': toteserial,
            })

    return len(df), matches, mismatches


class RFIDCheckerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("RFID Serial Checker")
        root.resizable(False, False)

        # --- File selection frame ---
        frame_file = ttk.LabelFrame(root, text="Step 1: Select CSV File", padding=10)
        frame_file.pack(fill='x', padx=10, pady=(10, 5))

        self.filepath_var = tk.StringVar()

        ttk.Entry(frame_file, textvariable=self.filepath_var, width=60).pack(side='left', padx=(0, 5))
        ttk.Button(frame_file, text="Browse...", command=self.browse_file).pack(side='left')

        # --- Run button ---
        self.run_btn = ttk.Button(root, text="Run Check", command=self.run_check, state='disabled')
        self.run_btn.pack(pady=5)

        # --- Results display ---
        frame_results = ttk.LabelFrame(root, text="Step 2: Results", padding=10)
        frame_results.pack(fill='both', expand=True, padx=10, pady=(5, 10))

        self.result_text = tk.Text(frame_results, height=16, width=80, wrap='word', state='disabled')
        self.result_text.pack(side='left', fill='both', expand=True)

        scrollbar = ttk.Scrollbar(frame_results, orient='vertical', command=self.result_text.yview)
        scrollbar.pack(side='right', fill='y')
        self.result_text.configure(yscrollcommand=scrollbar.set)

        # Colour tags
        self.result_text.tag_configure('success', foreground='green', font=('Segoe UI', 10, 'bold'))
        self.result_text.tag_configure('error', foreground='red', font=('Segoe UI', 10))
        self.result_text.tag_configure('info', foreground='black', font=('Segoe UI', 10))
        self.result_text.tag_configure('header', foreground='darkblue', font=('Segoe UI', 10, 'bold'))

    def browse_file(self):
        filepath = filedialog.askopenfilename(
            title="Select CSV file",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ]
        )
        if filepath:
            self.filepath_var.set(filepath)
            self.run_btn.config(state='normal')

    def log(self, text: str, tag: str = 'info'):
        self.result_text.config(state='normal')
        self.result_text.insert(tk.END, text + '\n', tag)
        self.result_text.see(tk.END)
        self.result_text.config(state='disabled')

    def run_check(self):
        filepath = self.filepath_var.get()
        if not filepath or not os.path.isfile(filepath):
            messagebox.showerror("Error", "Please select a valid CSV file.")
            return

        # Clear previous results
        self.result_text.config(state='normal')
        self.result_text.delete('1.0', tk.END)
        self.result_text.config(state='disabled')

        self.log(f"File: {os.path.basename(filepath)}", 'header')
        self.log(f"{'='*60}", 'header')

        try:
            total, matches, mismatches = process_file(filepath)
            self.log(f"Total rows checked: {total}", 'info')
            self.log(f"Matches: {matches}", 'success' if matches == total else 'info')

            if not mismatches:
                self.log("", 'info')
                self.log("✓ ALL SERIALS MATCH! Everything is good.", 'success')
                messagebox.showinfo("Success", "All serials match correctly!")
            else:
                self.log(f"Mismatches: {len(mismatches)}", 'error')
                self.log("", 'info')
                self.log("--- Mismatch Details ---", 'header')

                for m in mismatches:
                    self.log(
                        f"Row {m['row']}: "
                        f"toterfidserial='{m['toterfidserial_raw']}' "
                        f"(last 5 removed '{m['toterfidserial_last5']}' → '{m['toterfidserial_stripped']}') "
                        f"≠ toteserial='{m['toteserial']}'",
                        'error'
                    )

                self.log("", 'info')
                self.log(f"⚠  {len(mismatches)} mismatch(es) found. Please review.", 'error')

        except Exception as e:
            self.log(f"ERROR: {e}", 'error')
            messagebox.showerror("Error", str(e))


def main():
    root = tk.Tk()
    app = RFIDCheckerApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()