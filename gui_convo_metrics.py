# gui_convo_metrics_plus.py — paste-or-drop GUI for convo metrics (ChatGPT + Claude)
# Now supports .txt, .docx (Word), and .json conversation exports.
# Requires: pandas, openpyxl. Optional: tkinterdnd2 for drag & drop of files. For .docx: pip install python-docx
# It imports processing from convo_metrics_batch_v4.py (same folder).

import os, sys, time, re, json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

OUTPUT_FOLDER = "output"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ---- Try to import processing from the batch script ----
try:
    from convo_metrics_batch_v4 import process_conversation, negative_control_prompt_shuffle, HOT_THRESHOLD
except Exception as e:
    try:
        messagebox.showerror("Import Error", "Couldn't import convo_metrics_batch_v4.py: {}\nPut this GUI file in the same folder as convo_metrics_batch_v4.py.".format(e))
    except Exception:
        print("[Import Error] Couldn't import convo_metrics_batch_v4.py:", e)
    raise

import pandas as pd

# ---- helpers to read convo text from multiple formats ----

def _read_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _read_docx(path: str) -> str:
    try:
        from docx import Document
    except Exception as e:
        raise RuntimeError("python-docx is required for .docx files. Install with: pip install python-docx") from e
    doc = Document(path)
    paras = []
    for p in doc.paragraphs:
        paras.append(p.text)
    text = "\n".join(paras).strip()
    return text

def _flatten_openai_contents(content):
    """OpenAI JSON may have content as string or list of {'type':'text','text':...} blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, dict):
                # 'text' for text blocks; assist if name differs
                if 'text' in part and isinstance(part['text'], str):
                    out.append(part['text'])
                elif 'image_url' in part:
                    out.append("[image]")
        return "\n".join(out)
    if isinstance(content, dict) and 'text' in content:
        return content.get('text','')
    return str(content)

ROLE_MAP = {
    'user':'User', 'human':'User', 'system':'User', # treat system as user context
    'assistant':'Assistant', 'claude':'Assistant', 'model':'Assistant'
}

def _read_json(path: str) -> str:
    """Best-effort loader for common ChatGPT/Claude exports.
    Produces a normalized plain text with explicit headers like 'User:' / 'Assistant:' so the downstream parser works.
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    lines = []

    # Case 1: {'messages': [...]} like OpenAI
    msgs = None
    if isinstance(data, dict) and isinstance(data.get('messages'), list):
        msgs = data['messages']
    elif isinstance(data, list) and data and isinstance(data[0], dict) and 'messages' in data[0]:
        msgs = data[0]['messages']
    elif isinstance(data, list):
        # sometimes the root is already a list of message dicts
        if all(isinstance(m, dict) and ('role' in m or 'sender' in m) for m in data):
            msgs = data

    if msgs is not None:
        for m in msgs:
            role = m.get('role') or m.get('sender') or m.get('author')
            role_norm = ROLE_MAP.get(str(role).lower(), 'User' if str(role).lower() in ('system',) else 'Assistant' if str(role).lower() in ('assistant','claude','model') else 'User')
            content = m.get('content')
            text = _flatten_openai_contents(content)
            header = 'User:' if role_norm == 'User' else 'Assistant:'
            lines.append(f"{header} {text}")
        return "\n".join(lines)

    # Case 2: Anthropic-style {'type':'message','role':'assistant','content':...}
    if isinstance(data, dict) and data.get('type') == 'message' and 'role' in data and 'content' in data:
        role_norm = ROLE_MAP.get(str(data.get('role')).lower(), 'Assistant')
        text = _flatten_openai_contents(data.get('content'))
        header = 'Assistant:' if role_norm == 'Assistant' else 'User:'
        return f"{header} {text}"

    # Case 3: Unknown structure — fallback to raw dump
    return json.dumps(data, ensure_ascii=False, indent=2)


def read_convo_from_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == '.txt':
        return _read_txt(path)
    if ext == '.docx':
        return _read_docx(path)
    if ext == '.json':
        return _read_json(path)
    raise ValueError("Unsupported file type: {}".format(ext))

# ---- Excel writer helper ----

def write_workbook(df: pd.DataFrame, base_name: str) -> str:
    # --- defensive checks ---
    if "E_score" not in df.columns:
        raise KeyError("Missing E_score column — parsing likely failed. Make sure the text has clear User/Assistant turns.")
    if df.empty:
        out_xlsx = os.path.join(OUTPUT_FOLDER, f"{base_name}_results.xlsx")
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="metrics")
        return out_xlsx

    E = df["E_score"].astype(float)
    summary = {
        "rows": [len(df)],
        "E_mean": [round(E.mean(),3)],
        "E_median": [round(E.median(),3)],
        "E_min": [round(E.min(),3)],
        "E_max": [round(E.max(),3)],
        f"hot_share_E≥{HOT_THRESHOLD:.2f}": [round((E>=HOT_THRESHOLD).mean(),3)],
        "third_mean": [round(df["third_present_legacy"].astype(float).mean(),3)],
        "third_median": [round(df["third_present_legacy"].astype(float).median(),3)],
        "third_min": [round(df["third_present_legacy"].astype(float).min(),3)],
        "third_max": [round(df["third_present_legacy"].astype(float).max(),3)],
    }
    try:
        q = E.quantile([0.25,0.5,0.75]).round(3)
        summary["E_Q1"] = [q.loc[0.25]]; summary["E_Q2"] = [q.loc[0.5]]; summary["E_Q3"] = [q.loc[0.75]]
    except Exception:
        summary["E_Q1"] = [float("nan")]; summary["E_Q2"] = [float("nan")]; summary["E_Q3"] = [float("nan")]

    try:
        bin_summary = (
            df.groupby("Assistant_len_bin")["E_score"]
              .agg(['count','mean','median','min','max'])
              .round(3).reset_index()
        )
    except Exception:
        bin_summary = pd.DataFrame(columns=["Assistant_len_bin","count","mean","median","min","max"])  # empty fallback

    even = df[df["Turn"]%2==0]["E_score"]; odd = df[df["Turn"]%2==1]["E_score"]
    def _safe_mean(s):
        try: return round(float(s.mean()),3)
        except Exception: return float("nan")
    def _safe_share(s):
        try: return round(float((s>=HOT_THRESHOLD).mean()),3)
        except Exception: return float("nan")
    exp_checks = {
        "even_count": [len(even)], "even_E_mean": [_safe_mean(even)],
        "odd_count": [len(odd)],   "odd_E_mean":  [_safe_mean(odd)],
        "hot_share_even": [_safe_share(even)],
        "hot_share_odd":  [_safe_share(odd)],
    }

    if "E_score_prompt_shuffle" in df.columns:
        ctrl = df["E_score_prompt_shuffle"]
        exp_checks.update({
            "ctrl_prompt_shuffle_mean": [_safe_mean(ctrl)],
            "ctrl_prompt_shuffle_hot_share": [_safe_share(ctrl)],
            "delta_mean_E_minus_ctrl": [round(E.mean() - ctrl.mean(),3)]
        })

    summary_df    = pd.DataFrame(summary)
    exp_checks_df = pd.DataFrame(exp_checks)
    topN = df.sort_values("E_score", ascending=False).head(10).copy()

    out_xlsx = os.path.join(OUTPUT_FOLDER, f"{base_name}_results.xlsx")
    try:
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="metrics")
            summary_df.to_excel(writer, index=False, sheet_name="summary")
            bin_summary.to_excel(writer, index=False, sheet_name="bin_summary")
            exp_checks_df.to_excel(writer, index=False, sheet_name="exp_checks")
            topN.to_excel(writer, index=False, sheet_name="top_emergent")
    except Exception as e:
        # CSV fallback
        df.to_csv(os.path.join(OUTPUT_FOLDER, f"{base_name}_metrics.csv"), index=False)
        summary_df.to_csv(os.path.join(OUTPUT_FOLDER, f"{base_name}_summary.csv"), index=False)
        bin_summary.to_csv(os.path.join(OUTPUT_FOLDER, f"{base_name}_bin_summary.csv"), index=False)
        exp_checks_df.to_csv(os.path.join(OUTPUT_FOLDER, f"{base_name}_exp_checks.csv"), index=False)
        topN.to_csv(os.path.join(OUTPUT_FOLDER, f"{base_name}_top_emergent.csv"), index=False)
        print(f"[WARN] Excel write failed ({e}). Wrote CSVs instead.")
    return out_xlsx

# ---- GUI ----

class App:
    def __init__(self, root):
        self.root = root
        root.title("Convo Metrics — Paste/Drop (.txt, .docx, .json)")
        root.geometry("1000x680")

        self.make_widgets()
        self.enable_dnd_if_available()

    def make_widgets(self):
        frm_top = ttk.Frame(self.root)
        frm_top.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(frm_top, text="Paste conversation text below (ChatGPT or Claude).\nOr drag one or more files: .txt, .docx, .json").pack(anchor=tk.W)

        self.text = tk.Text(self.root, wrap=tk.WORD, undo=True)
        self.text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,8))

        frm_btn = ttk.Frame(self.root)
        frm_btn.pack(fill=tk.X, padx=10, pady=8)

        self.btn_process = ttk.Button(frm_btn, text="Process Pasted Text", command=self.process_pasted)
        self.btn_process.pack(side=tk.LEFT)

        self.btn_load = ttk.Button(frm_btn, text="Load Files…", command=self.load_files)
        self.btn_load.pack(side=tk.LEFT, padx=6)

        self.btn_clear = ttk.Button(frm_btn, text="Clear", command=self.clear_box)
        self.btn_clear.pack(side=tk.LEFT, padx=6)

        self.btn_open = ttk.Button(frm_btn, text="Open Output Folder", command=self.open_output_folder)
        self.btn_open.pack(side=tk.LEFT, padx=6)

        self.status = ttk.Label(self.root, text="Ready.")
        self.status.pack(fill=tk.X, padx=10, pady=(0,10))

    # --- Drag & Drop support (optional) ---
    def enable_dnd_if_available(self):
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            if not isinstance(self.root, TkinterDnD.Tk):
                self.root.destroy()
                new_root = TkinterDnD.Tk()
                self.__init__(new_root)
                return
        except Exception:
            pass
        try:
            from tkinterdnd2 import DND_FILES
            self.text.drop_target_register(DND_FILES)
            self.text.dnd_bind('<<Drop>>', self.on_drop)
            self.status.configure(text="Ready. (Drag & drop enabled)")
        except Exception:
            pass

    def on_drop(self, event):
        paths = self._parse_drop_list(event.data)
        files = [p for p in paths if os.path.splitext(p)[1].lower() in ('.txt','.docx','.json')]
        if not files:
            messagebox.showwarning("Unsupported", "Drop .txt, .docx, or .json files.")
            return
        self.process_files(files)

    def _parse_drop_list(self, data: str):
        parts = re.findall(r"\{([^}]+)\}|([^\s]+)", data)
        paths = []
        for a,b in parts:
            paths.append(a if a else b)
        return paths

    # --- Buttons ---
    def process_pasted(self):
        import traceback
        txt = self.text.get("1.0", tk.END).strip()
        if not txt:
            messagebox.showinfo("Nothing to do", "Paste some text first.")
            return
        self.disable_ui()
        self.status.configure(text="Processing pasted text…")
        self.root.update_idletasks()
        try:
            df = process_conversation(txt)
            if "E_score" not in df.columns:
                raise KeyError("Missing E_score — check transcript headers.")
            ctrl = negative_control_prompt_shuffle(df)
            if ctrl is not None:
                df = pd.concat([df, ctrl], axis=1)
            base = time.strftime("pasted_%Y%m%d_%H%M%S")
            out = write_workbook(df, base)
            messagebox.showinfo("Done", f"Wrote: {os.path.basename(out)}")
            self.clear_box()
            self.status.configure(text=f"Done. Output → {out}")
        except Exception as e:
            tb = traceback.format_exc()
            messagebox.showerror("Error", "❌ {}\n\nDetails:\n{}".format(e, tb))
            self.status.configure(text="Error. See message.")
        finally:
            self.enable_ui()

    def load_files(self):
        files = filedialog.askopenfilenames(title="Choose files", filetypes=[
            ("Supported","*.txt;*.docx;*.json"),
            ("Text","*.txt"),
            ("Word","*.docx"),
            ("JSON","*.json")
        ])
        if not files:
            return
        self.process_files(files)

    def process_files(self, files):
        import traceback
        self.disable_ui()
        try:
            last_out = None
            for i, path in enumerate(files, 1):
                self.status.configure(text=f"Processing {i}/{len(files)}: {os.path.basename(path)}…")
                self.root.update_idletasks()
                try:
                    text = read_convo_from_path(path)
                except Exception as read_err:
                    messagebox.showwarning("Skip", "Could not read {}: {}".format(os.path.basename(path), read_err))
                    continue
                df = process_conversation(text)
                if "E_score" not in df.columns:
                    raise KeyError("Missing E_score for {} — check transcript structure.".format(os.path.basename(path)))
                ctrl = negative_control_prompt_shuffle(df)
                if ctrl is not None:
                    df = pd.concat([df, ctrl], axis=1)
                base = os.path.splitext(os.path.basename(path))[0]
                last_out = write_workbook(df, base)
            if last_out:
                messagebox.showinfo("Done", f"Processed {len(files)} file(s). Last output: {os.path.basename(last_out)}")
                self.clear_box()
                self.status.configure(text="Batch complete.")
            else:
                messagebox.showinfo("No files processed", "Nothing was processed.")
                self.status.configure(text="No files processed.")
        except Exception as e:
            tb = traceback.format_exc()
            messagebox.showerror("Error", "❌ {}\n\nDetails:\n{}".format(e, tb))
            self.status.configure(text="Error during batch.")
        finally:
            self.enable_ui()

    def clear_box(self):
        self.text.delete("1.0", tk.END)

    def open_output_folder(self):
        path = os.path.abspath(OUTPUT_FOLDER)
        if sys.platform.startswith('darwin'):
            os.system(f"open '{path}'")
        elif os.name == 'nt':
            os.startfile(path)
        else:
            os.system(f"xdg-open '{path}'")

    def disable_ui(self):
        self.btn_process.configure(state=tk.DISABLED)
        self.btn_load.configure(state=tk.DISABLED)
        self.btn_clear.configure(state=tk.DISABLED)
        self.btn_open.configure(state=tk.DISABLED)

    def enable_ui(self):
        self.btn_process.configure(state=tk.NORMAL)
        self.btn_load.configure(state=tk.NORMAL)
        self.btn_clear.configure(state=tk.NORMAL)
        self.btn_open.configure(state=tk.NORMAL)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
