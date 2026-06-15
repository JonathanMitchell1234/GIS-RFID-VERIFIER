import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


def strip_last_five(value: str) -> str:
    """Remove the last 5 characters from a string."""
    return value[:-5] if len(value) >= 5 else value


def process_file(filepath: str) -> dict:
    """
    Read the CSV file and compare toterfidserial (last 5 chars removed)
    to toteserial. Returns a dict with file-level results.
    """
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

    return {
        'filepath': filepath,
        'filename': os.path.basename(filepath),
        'total': len(df),
        'matches': matches,
        'mismatches': mismatches,
        'all_ok': len(mismatches) == 0,
    }


class RFIDCheckerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("RFID Serial Checker - Bulk")
        self.root.resizable(False, False)

        self.file_list: list[str] = []
        self._processing = False

        # --- File selection frame ---
        frame_file = ttk.LabelFrame(root, text="Step 1: Select CSV File(s)", padding=10)
        frame_file.pack(fill='x', padx=10, pady=(10, 5))

        self.file_count_var = tk.StringVar(value="No files selected")

        ttk.Button(frame_file, text="Add Files...", command=self.browse_files).pack(side='left', padx=(0, 5))
        ttk.Button(frame_file, text="Clear All", command=self.clear_files).pack(side='left')

        lbl_count = ttk.Label(frame_file, textvariable=self.file_count_var)
        lbl_count.pack(side='left', padx=(15, 0))

        # --- Progress bar ---
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(root, orient='horizontal', length=400,
                                             mode='determinate', variable=self.progress_var)
        self.progress_bar.pack(pady=(5, 0))

        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(root, textvariable=self.status_var, foreground='gray')
        self.status_label.pack()

        # --- Run button ---
        self.run_btn = ttk.Button(root, text="Run Check on All Files", command=self.run_check, state='disabled')
        self.run_btn.pack(pady=5)

        # --- Results display ---
        frame_results = ttk.LabelFrame(root, text="Step 2: Results", padding=10)
        frame_results.pack(fill='both', expand=True, padx=10, pady=(5, 10))

        self.result_text = tk.Text(frame_results, height=22, width=90, wrap='word', state='disabled')
        self.result_text.pack(side='left', fill='both', expand=True)

        scrollbar = ttk.Scrollbar(frame_results, orient='vertical', command=self.result_text.yview)
        scrollbar.pack(side='right', fill='y')
        self.result_text.configure(yscrollcommand=scrollbar.set)

        # Colour tags
        self.result_text.tag_configure('success', foreground='green', font=('Segoe UI', 10, 'bold'))
        self.result_text.tag_configure('error', foreground='red', font=('Segoe UI', 10))
        self.result_text.tag_configure('warn', foreground='orange', font=('Segoe UI', 10, 'bold'))
        self.result_text.tag_configure('info', foreground='black', font=('Segoe UI', 10))
        self.result_text.tag_configure('header', foreground='darkblue', font=('Segoe UI', 10, 'bold'))
        self.result_text.tag_configure('summary_ok', foreground='green', font=('Segoe UI', 11, 'bold'))
        self.result_text.tag_configure('summary_fail', foreground='red', font=('Segoe UI', 11, 'bold'))
        self.result_text.tag_configure('filename_ok', foreground='green', font=('Segoe UI', 10, 'bold'))
        self.result_text.tag_configure('filename_bad', foreground='red', font=('Segoe UI', 10, 'bold'))

    def browse_files(self):
        filepaths = filedialog.askopenfilenames(
            title="Select CSV file(s)",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ]
        )
        if filepaths:
            # Add new files, deduplicate
            existing = {f.lower() for f in self.file_list}
            for fp in filepaths:
                if fp.lower() not in existing:
                    self.file_list.append(fp)
                    existing.add(fp.lower())
            self._update_file_count()
            self.run_btn.config(state='normal' if self.file_list else 'disabled')

    def clear_files(self):
        self.file_list.clear()
        self.file_count_var.set("No files selected")
        self.run_btn.config(state='disabled')
        self.status_var.set("")

    def _update_file_count(self):
        count = len(self.file_list)
        if count == 0:
            self.file_count_var.set("No files selected")
        elif count == 1:
            self.file_count_var.set(f"1 file selected: {os.path.basename(self.file_list[0])}")
        else:
            self.file_count_var.set(f"{count} files selected")

    def log(self, text: str, tag: str = 'info'):
        self.result_text.config(state='normal')
        self.result_text.insert(tk.END, text + '\n', tag)
        self.result_text.see(tk.END)
        self.result_text.config(state='disabled')

    def _process_results(self, results: list[dict]):
        """Display all results (called on main thread after parallel processing completes)."""
        total_files = len(results)
        all_files_ok = True
        files_ok_count = 0
        files_fail_count = 0
        grand_total_rows = 0
        grand_total_matches = 0
        grand_total_mismatches = 0

        for file_idx, result in enumerate(results, start=1):
            filename = result['filename']
            self.log(f"[{file_idx}/{total_files}] Checking: {filename}", 'header')

            if 'error' in result:
                files_fail_count += 1
                all_files_ok = False
                self.log(f"  ERROR: {result['error']}", 'error')
            else:
                grand_total_rows += result['total']
                grand_total_matches += result['matches']
                grand_total_mismatches += len(result['mismatches'])

                if result['all_ok']:
                    files_ok_count += 1
                    self.log(f"  ✓ ALL {result['total']} rows match.", 'success')
                else:
                    files_fail_count += 1
                    all_files_ok = False
                    self.log(f"  ✗ {len(result['mismatches'])} of {result['total']} rows MISMATCH.", 'error')

                    for m in result['mismatches'][:50]:  # Cap detail output at 50 rows per file
                        self.log(
                            f"    Row {m['row']}: "
                            f"toterfidserial='{m['toterfidserial_raw']}' "
                            f"(removed '{m['toterfidserial_last5']}' → '{m['toterfidserial_stripped']}') "
                            f"≠ toteserial='{m['toteserial']}'",
                            'error'
                        )
                    remaining = len(result['mismatches']) - 50
                    if remaining > 0:
                        self.log(f"    ... and {remaining} more mismatches (see CSV file for full list)", 'warn')

            self.log("", 'info')

        # --- Grand Summary ---
        self.log(f"{'='*80}", 'header')
        self.log("GRAND SUMMARY", 'header')
        self.log(f"{'='*80}", 'header')

        self.log(f"Total files checked: {total_files}", 'info')
        self.log(f"Files with all OK:  {files_ok_count}", 'success' if files_ok_count > 0 else 'info')
        self.log(f"Files with issues:  {files_fail_count}", 'error' if files_fail_count > 0 else 'info')
        self.log(f"", 'info')
        self.log(f"Total rows across all files: {grand_total_rows}", 'info')
        self.log(f"Total matches:               {grand_total_matches}", 'success')
        self.log(f"Total mismatches:            {grand_total_mismatches}", 'error' if grand_total_mismatches > 0 else 'info')
        self.log(f"", 'info')

        if all_files_ok:
            self.log("✓ ✓ ✓ ALL FILES PASSED! Every serial matches correctly. ✓ ✓ ✓", 'summary_ok')
            messagebox.showinfo("Success", f"All {total_files} file(s) passed!\nAll serials match correctly.")
        else:
            self.log("⚠ ⚠ ⚠ SOME FILES HAVE ISSUES. Please review the details above. ⚠ ⚠ ⚠", 'summary_fail')
            messagebox.showwarning(
                "Issues Found",
                f"{files_fail_count} of {total_files} file(s) have mismatches.\n"
                f"Total mismatches: {grand_total_mismatches} row(s).\n"
                f"See results window for details."
            )

        # Re-enable controls
        self._processing = False
        self.run_btn.config(state='normal')
        self.progress_var.set(100)
        self.status_var.set(f"Done. {files_ok_count} OK, {files_fail_count} with issues.")

    def _run_parallel(self):
        """Run process_file in parallel using a thread pool (runs in background thread)."""
        filepaths = list(self.file_list)
        total = len(filepaths)
        results = [None] * total

        with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 4, 8)) as executor:
            future_map = {}
            for i, fp in enumerate(filepaths):
                future = executor.submit(process_file, fp)
                future_map[future] = i

            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = {
                        'filepath': filepaths[idx],
                        'filename': os.path.basename(filepaths[idx]),
                        'error': str(e),
                        'total': 0, 'matches': 0, 'mismatches': [], 'all_ok': False,
                    }

                # Update progress on main thread
                completed = sum(1 for r in results if r is not None)
                self.root.after(0, self._update_progress, completed, total, filepaths)

        # All done — push results to main thread for display
        self.root.after(0, self._process_results, results)

    def _update_progress(self, completed: int, total: int, filepaths: list[str]):
        pct = int((completed / total) * 100)
        self.progress_var.set(pct)
        current_file = filepaths[min(completed, total) - 1] if completed > 0 else ""
        self.status_var.set(f"Processing {completed}/{total}: {os.path.basename(current_file)}")

    def run_check(self):
        if not self.file_list:
            messagebox.showerror("Error", "Please add at least one CSV file.")
            return
        if self._processing:
            return

        self._processing = True
        self.run_btn.config(state='disabled')

        # Clear previous results
        self.result_text.config(state='normal')
        self.result_text.delete('1.0', tk.END)
        self.result_text.config(state='disabled')

        self.log(f"RFID Serial Checker - Bulk Run (Parallel)", 'header')
        self.log(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 'info')
        self.log(f"Files to check: {len(self.file_list)}", 'info')
        self.log(f"Workers: {min(os.cpu_count() or 4, 8)} parallel threads", 'info')
        self.log(f"{'='*80}", 'header')
        self.log("", 'info')

        self.progress_var.set(0)
        self.status_var.set("Starting...")

        # Run parallel processing in a background thread so UI stays responsive
        thread = threading.Thread(target=self._run_parallel, daemon=True)
        thread.start()


def main():
    root = tk.Tk()
    app = RFIDCheckerApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()