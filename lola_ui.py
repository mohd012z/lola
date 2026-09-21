#!/usr/bin/env python3
"""
Lola Desktop Control Panel
No command typing required.

Run:
    python lola_ui.py
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from lola_library import catalog, register_target, set_plan, list_targets, load_target


ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "lola.py"

APK_MODES = [
    ("/apk360", "APK 360", "Complete APK overview"),
    ("/apkmanifest", "Manifest", "Package, SDK and application manifest"),
    ("/apkpermissions", "Permissions", "Declared and sensitive Android permissions"),
    ("/apkcomponents", "Components", "Activities, services, receivers and providers"),
    ("/apkurls", "URLs", "Literal endpoints recovered from the APK"),
    ("/apkapi", "API", "API/auth/media/GraphQL-style endpoint references"),
    ("/apkkeys", "Keys", "Redacted password/token/key references"),
    ("/apkcerts", "Certificates", "Signing and certificate metadata"),
    ("/apknative", "Native .SO", "ABI and native library inventory"),
    ("/apkwebview", "WebView", "WebView and JavaScript bridge references"),
    ("/apkcrypto", "Crypto", "Cipher/hash/KDF/key-store references"),
    ("/apkfiles", "Files", "Full APK ZIP/file inventory"),
    ("/apkcode", "Code / JADX", "Optional decompilation status"),
    ("/apkrisk", "Risk Review", "Consolidated APK review findings"),
    ("/apktools", "Tools", "Show available local APK analysis tools"),
]

SECURITY_MODES = [
    ("/360", "360 Overview", "Whole source/security surface"),
    ("/deep-dive", "Deep Dive", "Every Semgrep detection and evidence"),
    ("/securitycheck", "Security Check", "Security control review"),
    ("/anonymus", "Privacy / Anonymous", "Privacy and identity exposure audit"),
    ("/stepview", "Step View", "Before / during / after scan"),
    ("/protocol", "Protocol", "Protocol inventory"),
    ("/hidden", "Hidden", "Hidden files/config/UI surfaces"),
]

CODE_MODES = [
    ("/deep-code", "Deep Code", "Combined source analysis"),
    ("/extraction", "Extraction", "Imports, functions, classes, routes"),
    ("/codesummary", "Code Summary", "Repository/source summary"),
    ("/codeview", "Code View", "Redacted source browser"),
    ("/codepassword", "Password / Key", "Redacted password/token/key locations"),
    ("/codestring", "Strings", "Static string inventory"),
    ("/codetransparent", "Transparent Flow", "Heuristic source/sink map"),
    ("/codemodification", "Modification", "File/storage/DB/UI/network writes"),
    ("/codefallback", "Fallback", "Try/catch/retry/default/fallback paths"),
    ("/codeurls", "Code URLs", "URLs linked to source"),
    ("/codeencryption", "Encryption", "Crypto/password/key usage"),
    ("/hiddenmode", "Hidden Mode", "Hidden code/UI/config evidence"),
]

NETWORK_MODES = [
    ("/deep-network", "Deep Network", "Combined network analysis"),
    ("/trace", "Trace", "URL/DNS/redirect/TLS trace"),
    ("/route", "Route", "Application route map"),
    ("/map", "Map", "Logical network graph"),
    ("/visible", "Visible", "Publicly visible source/resolution surface"),
    ("/realip", "Real IP", "Resolved public IPs and discovery references"),
    ("/cctv", "CCTV Monitor", "Live scan-process control-room view"),
    ("/normal", "Normal", "Compact network view"),
]

PREFLIGHT_MODES = [
    ("/preflight", "Preflight", "Before-Semgrep target analysis"),
    ("/viewextraction", "View Extraction", "Pre-scan functions/classes/routes"),
    ("/viewurls", "View URLs", "Pre-scan URL inventory"),
    ("/routes", "Routes", "Pre-scan app routes"),
    ("/api", "API", "Pre-scan API references"),
    ("/keys", "Keys", "Pre-scan redacted key references"),
    ("/hiddentraces", "Hidden Traces", "Detect hidden/stealth-like references"),
    ("/hidemodes", "Hide Modes", "Detect hidden/private/silent mode references"),
    ("/hidelog", "Hide Log Detection", "Detect log suppression/clearing code"),
    ("/ipmirror", "IP Mirror", "App destination IP mirror"),
    ("/certs", "Certs", "Certificate inventory"),
]

OUTPUTS = [
    ("APK Visual", ROOT / "apk-report.html"),
    ("APK JSON", ROOT / "apk-analysis.json"),
    ("Security Visual", ROOT / "semgrep-report.html"),
    ("Network Monitor", ROOT / "network-monitor.html"),
    ("Semgrep JSON", ROOT / "semgrep-results.json"),
    ("Code JSON", ROOT / "code-analysis.json"),
    ("Network JSON", ROOT / "network-analysis.json"),
    ("Preflight JSON", ROOT / "preflight-analysis.json"),
    ("URL JSON", ROOT / "url-report.json"),
    ("Manifest JSON", ROOT / "target-manifest.json"),
    ("Mode JSON", ROOT / "scan-modes.json"),
]


class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self.window, width=e.width),
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._wheel)

    def _wheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass


class LolaUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lola Security & APK Control Panel")
        self.geometry("1250x840")
        self.minsize(940, 650)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.selected_mode = tk.StringVar(value="/apk360")
        self.target = tk.StringVar()
        self.target_type = tk.StringVar(value="No target selected")
        self.status = tk.StringVar(value="Ready")
        self.library_data = catalog()
        self.current_target_record = None
        self.apk_plan_vars = {
            item["id"]: tk.BooleanVar(value=bool(item.get("default")))
            for item in self.library_data.get("apkPlan", [])
        }
        self.library_search = tk.StringVar()

        self.resolve_urls = tk.BooleanVar(value=False)
        self.live_monitor = tk.BooleanVar(value=False)
        self.capture_all_code = tk.BooleanVar(value=False)
        self.copy_public_certs = tk.BooleanVar(value=False)
        self.decompile = tk.BooleanVar(value=False)
        self.keep_decompiled = tk.BooleanVar(value=False)
        self.cleanup = tk.BooleanVar(value=False)
        self.no_persist_events = tk.BooleanVar(value=False)
        self.no_open = tk.BooleanVar(value=False)

        self.configure_styles()
        self.build_ui()
        self.after(120, self.pump_logs)
        self.after(1200, self.poll_outputs)

    def configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        bg = "#0b1220"
        panel = "#111b2e"
        text = "#eef4ff"
        muted = "#9fb0cc"
        accent = "#2f6fed"

        self.configure(bg=bg)
        style.configure(".", background=bg, foreground=text)
        style.configure("TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("Muted.TLabel", background=bg, foreground=muted)
        style.configure("Header.TLabel", background=bg, foreground=text, font=("Segoe UI", 18, "bold"))
        style.configure("Mode.TButton", padding=(10, 8), font=("Segoe UI", 10))
        style.configure("Run.TButton", padding=(16, 11), font=("Segoe UI", 11, "bold"))
        style.configure("Stop.TButton", padding=(13, 11), font=("Segoe UI", 10, "bold"))
        style.configure("TCheckbutton", background=bg, foreground=text)
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(13, 8))
        style.map("TNotebook.Tab", background=[("selected", accent)])

    def build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(12, 8))

        ttk.Label(top, text="🛡 Lola Control Panel", style="Header.TLabel").pack(side="left")
        ttk.Label(top, textvariable=self.status, style="Muted.TLabel").pack(side="right")

        target_box = ttk.LabelFrame(self, text="1. Choose Target")
        target_box.pack(fill="x", padx=14, pady=6)

        target_row = ttk.Frame(target_box)
        target_row.pack(fill="x", padx=10, pady=8)

        ttk.Entry(target_row, textvariable=self.target).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(target_row, text="📦 Browse APK", command=self.browse_apk).pack(side="left", padx=3)
        ttk.Button(target_row, text="📄 Browse File", command=self.browse_file).pack(side="left", padx=3)
        ttk.Button(target_row, text="📁 Browse Folder", command=self.browse_folder).pack(side="left", padx=3)

        ttk.Label(target_box, textvariable=self.target_type, style="Muted.TLabel").pack(anchor="w", padx=11, pady=(0, 7))

        action_row = ttk.Frame(self)
        action_row.pack(fill="x", padx=14, pady=6)

        ttk.Label(action_row, text="Selected mode:").pack(side="left")
        self.mode_label = ttk.Label(action_row, textvariable=self.selected_mode)
        self.mode_label.pack(side="left", padx=(6, 15))

        ttk.Button(action_row, text="▶ RUN SCAN", style="Run.TButton", command=self.run_scan).pack(side="left", padx=4)
        ttk.Button(action_row, text="■ STOP", style="Stop.TButton", command=self.stop_scan).pack(side="left", padx=4)
        ttk.Button(action_row, text="Open Last Report", command=self.open_best_report).pack(side="left", padx=4)
        ttk.Button(action_row, text="Open Output Folder", command=self.open_root).pack(side="left", padx=4)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=14, pady=8)

        self.quick_tab = ttk.Frame(notebook)
        self.plan_tab = ScrollFrame(notebook)
        self.library_tab = ScrollFrame(notebook)
        self.apk_tab = ScrollFrame(notebook)
        self.security_tab = ScrollFrame(notebook)
        self.code_tab = ScrollFrame(notebook)
        self.network_tab = ScrollFrame(notebook)
        self.preflight_tab = ScrollFrame(notebook)
        self.options_tab = ScrollFrame(notebook)
        self.outputs_tab = ScrollFrame(notebook)
        self.log_tab = ttk.Frame(notebook)

        notebook.add(self.quick_tab, text="⭐ Quick")
        notebook.add(self.plan_tab, text="✅ Target Plan")
        notebook.add(self.library_tab, text="📚 Library")
        notebook.add(self.apk_tab, text="📦 APK")
        notebook.add(self.security_tab, text="🛡 Security")
        notebook.add(self.code_tab, text="💻 Code")
        notebook.add(self.network_tab, text="🌐 Network")
        notebook.add(self.preflight_tab, text="🔎 Pre-scan")
        notebook.add(self.options_tab, text="⚙ Options")
        notebook.add(self.outputs_tab, text="📂 Outputs")
        notebook.add(self.log_tab, text="📟 Live Log")

        self.build_quick()
        self.build_target_plan()
        self.build_library()
        self.build_mode_tab(self.apk_tab.inner, "APK Analysis", APK_MODES)
        self.build_mode_tab(self.security_tab.inner, "Security & Privacy", SECURITY_MODES)
        self.build_mode_tab(self.code_tab.inner, "Code Analysis", CODE_MODES)
        self.build_mode_tab(self.network_tab.inner, "Network Analysis", NETWORK_MODES)
        self.build_mode_tab(self.preflight_tab.inner, "Before-Scan / Target Analysis", PREFLIGHT_MODES)
        self.build_options()
        self.build_outputs()
        self.build_log()

    def build_quick(self):
        wrap = ttk.Frame(self.quick_tab)
        wrap.pack(fill="both", expand=True, padx=18, pady=18)

        ttk.Label(wrap, text="Quick Actions", style="Header.TLabel").pack(anchor="w", pady=(0, 12))

        quick = [
            ("📦 APK Full Scan", "/apk360", {"decompile": False}, "Fast full APK overview"),
            ("🔬 APK Deep + JADX", "/apk360", {"decompile": True}, "APK scan plus optional JADX extraction"),
            ("⚠ APK Risk Review", "/apkrisk", {}, "Jump directly to APK review findings"),
            ("🛡 Project Deep Dive", "/deep-dive", {"resolve_urls": True}, "Deep source/security scan"),
            ("🕶 Privacy Audit", "/anonymus", {"resolve_urls": True}, "Privacy / identity exposure"),
            ("🌐 Deep Network", "/deep-network", {"resolve_urls": True}, "Network trace/map/routes"),
            ("🎥 Live Monitor", "/cctv", {"resolve_urls": True, "live_monitor": True}, "Watch scan stages live"),
            ("💻 Deep Code", "/deep-code", {}, "Source structure, flows, modifications and fallbacks"),
        ]

        grid = ttk.Frame(wrap)
        grid.pack(fill="both", expand=True)
        for i, (label, mode, opts, desc) in enumerate(quick):
            card = ttk.LabelFrame(grid, text=label)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            ttk.Label(card, text=desc, style="Muted.TLabel", wraplength=430).pack(anchor="w", padx=10, pady=(8, 5))
            ttk.Button(
                card,
                text="Select",
                style="Mode.TButton",
                command=lambda m=mode, o=opts: self.apply_quick(m, o),
            ).pack(anchor="e", padx=10, pady=(2, 10))

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)


    def build_target_plan(self):
        p = self.plan_tab.inner
        ttk.Label(p, text="What should Lola do with the target?", style="Header.TLabel").pack(anchor="w", padx=14, pady=(14, 6))
        ttk.Label(
            p,
            text="For APK targets, these checks control which analysis categories run. The plan is also saved into the Target Library.",
            style="Muted.TLabel",
            wraplength=980,
        ).pack(anchor="w", padx=14, pady=(0, 10))

        presets = ttk.Frame(p)
        presets.pack(fill="x", padx=14, pady=4)
        ttk.Button(presets, text="Light", command=lambda: self.apply_plan_preset("light")).pack(side="left", padx=3)
        ttk.Button(presets, text="Recommended", command=lambda: self.apply_plan_preset("recommended")).pack(side="left", padx=3)
        ttk.Button(presets, text="Deep", command=lambda: self.apply_plan_preset("deep")).pack(side="left", padx=3)
        ttk.Button(presets, text="Clear", command=lambda: self.apply_plan_preset("none")).pack(side="left", padx=3)

        grid = ttk.Frame(p)
        grid.pack(fill="x", padx=10, pady=8)
        for i, item in enumerate(self.library_data.get("apkPlan", [])):
            card = ttk.LabelFrame(grid, text=item["label"])
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=5, pady=5)
            ttk.Checkbutton(card, text="Include", variable=self.apk_plan_vars[item["id"]]).pack(anchor="w", padx=9, pady=(7, 2))
            ttk.Label(card, text=item["description"], wraplength=430).pack(anchor="w", padx=9, pady=2)
            ttk.Label(card, text=f"Cost: {item['cost']}", style="Muted.TLabel").pack(anchor="w", padx=9, pady=(0, 8))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.plan_summary = ttk.Label(p, text="", style="Muted.TLabel", wraplength=980)
        self.plan_summary.pack(anchor="w", padx=14, pady=10)
        self.refresh_plan_summary()
        for var in self.apk_plan_vars.values():
            var.trace_add("write", lambda *_: self.refresh_plan_summary())

    def apply_plan_preset(self, name):
        items = self.library_data.get("apkPlan", [])
        chosen = set()
        if name == "light":
            chosen = {"identity","manifest","permissions","components","files","store_target"}
        elif name == "recommended":
            chosen = {x["id"] for x in items if x.get("default")}
        elif name == "deep":
            chosen = {x["id"] for x in items}
        for item in items:
            self.apk_plan_vars[item["id"]].set(item["id"] in chosen)

    def selected_apk_checks(self):
        return [k for k, v in self.apk_plan_vars.items() if v.get()]

    def refresh_plan_summary(self):
        if not hasattr(self, "plan_summary"):
            return
        checks = set(self.selected_apk_checks())
        labels = [x["label"] for x in self.library_data.get("apkPlan", []) if x["id"] in checks]
        self.plan_summary.configure(
            text=(f"{len(labels)} selected: " + " · ".join(labels)) if labels else "No APK checks selected."
        )
        self.decompile.set("decompile" in checks)

    def build_library(self):
        p = self.library_tab.inner
        ttk.Label(p, text="Built-in /library", style="Header.TLabel").pack(anchor="w", padx=14, pady=(14, 6))
        ttk.Label(
            p,
            text="Search every command/function, its purpose, supported platform, cost, required tools, and output.",
            style="Muted.TLabel",
            wraplength=980,
        ).pack(anchor="w", padx=14, pady=(0, 8))

        search_row = ttk.Frame(p)
        search_row.pack(fill="x", padx=14, pady=6)
        ttk.Entry(search_row, textvariable=self.library_search).pack(side="left", fill="x", expand=True)
        ttk.Button(search_row, text="Search", command=self.refresh_library_view).pack(side="left", padx=5)
        ttk.Button(search_row, text="Refresh Targets", command=self.refresh_library_view).pack(side="left")

        self.library_commands_frame = ttk.LabelFrame(p, text="Command / Function Library")
        self.library_commands_frame.pack(fill="x", padx=14, pady=8)

        self.target_library_frame = ttk.LabelFrame(p, text="Target Library")
        self.target_library_frame.pack(fill="x", padx=14, pady=8)

        self.library_search.trace_add("write", lambda *_: self.refresh_library_view())
        self.refresh_library_view()

    def refresh_library_view(self):
        if not hasattr(self, "library_commands_frame"):
            return
        for child in self.library_commands_frame.winfo_children():
            child.destroy()
        q = self.library_search.get().strip().lower()
        actual_modes = {x[0] for x in APK_MODES + SECURITY_MODES + CODE_MODES + NETWORK_MODES + PREFLIGHT_MODES}
        commands = [
            x for x in self.library_data.get("commands", [])
            if not q or q in str(x).lower()
        ]
        for item in commands[:120]:
            row = ttk.Frame(self.library_commands_frame)
            row.pack(fill="x", padx=8, pady=4)
            ttk.Label(row, text=f"{item['label']}  {item['id']}", width=30).pack(side="left", anchor="w")
            ttk.Label(row, text=item["purpose"], style="Muted.TLabel", wraplength=560).pack(side="left", fill="x", expand=True)
            if item["id"] in actual_modes:
                ttk.Button(row, text="Use", command=lambda m=item["id"]: self.select_mode(m)).pack(side="right", padx=4)

        for child in self.target_library_frame.winfo_children():
            child.destroy()
        ttk.Label(
            self.target_library_frame,
            text="Storage: .lola-library/targets/<SHA-based-id>.json",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=8, pady=5)
        for ref in list_targets()[:60]:
            row = ttk.Frame(self.target_library_frame)
            row.pack(fill="x", padx=8, pady=4)
            ttk.Label(row, text=ref.get("name","target"), width=30).pack(side="left", anchor="w")
            meta = f"{ref.get('id','')} · scans {ref.get('scanCount',0)} · package {ref.get('package') or '-'} · risk {ref.get('riskFindings',0)}"
            ttk.Label(row, text=meta, style="Muted.TLabel").pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Load Plan", command=lambda tid=ref.get("id",""): self.load_library_plan(tid)).pack(side="right")

    def load_library_plan(self, target_id):
        rec = load_target(target_id)
        if not rec:
            return
        plan = set(rec.get("lastPlan", []))
        for key, var in self.apk_plan_vars.items():
            var.set(key in plan)
        if rec.get("lastMode"):
            self.selected_mode.set(rec["lastMode"])
        self.status.set(f"Loaded library plan: {rec.get('name', target_id)}")

    def build_mode_tab(self, parent, title, modes):
        ttk.Label(parent, text=title, style="Header.TLabel").pack(anchor="w", padx=12, pady=(14, 8))
        ttk.Label(
            parent,
            text="Click a button to choose the mode, then press RUN SCAN.",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        grid = ttk.Frame(parent)
        grid.pack(fill="x", padx=8, pady=4)

        for i, (mode, label, desc) in enumerate(modes):
            card = ttk.LabelFrame(grid, text=label)
            card.grid(row=i // 3, column=i % 3, sticky="nsew", padx=5, pady=5)
            ttk.Label(card, text=mode, style="Muted.TLabel").pack(anchor="w", padx=9, pady=(7, 2))
            ttk.Label(card, text=desc, wraplength=300).pack(anchor="w", padx=9, pady=(0, 6))
            ttk.Button(
                card,
                text="Use This Mode",
                style="Mode.TButton",
                command=lambda m=mode: self.select_mode(m),
            ).pack(anchor="e", padx=9, pady=(0, 8))

        for col in range(3):
            grid.columnconfigure(col, weight=1)

    def build_options(self):
        p = self.options_tab.inner
        ttk.Label(p, text="Scan Options", style="Header.TLabel").pack(anchor="w", padx=14, pady=(14, 8))

        options = [
            ("Resolve public URLs / redirects / TLS", self.resolve_urls),
            ("Open live network monitor", self.live_monitor),
            ("Capture redacted source snapshot", self.capture_all_code),
            ("Copy public certificates", self.copy_public_certs),
            ("Decompile APK with JADX if available", self.decompile),
            ("Keep JADX decompiled output", self.keep_decompiled),
            ("Clean Lola temporary data after scan", self.cleanup),
            ("Do not persist Lola event JSON", self.no_persist_events),
            ("Do not auto-open final HTML", self.no_open),
        ]

        for text, var in options:
            ttk.Checkbutton(p, text=text, variable=var).pack(anchor="w", padx=18, pady=6)

        info = ttk.LabelFrame(p, text="Safety / Privacy")
        info.pack(fill="x", padx=14, pady=14)
        ttk.Label(
            info,
            text=(
                "Secret values are redacted in generated code/APK reports. "
                "Lola cleanup removes only Lola-generated temporary data; "
                "it does not erase operating-system, browser, application, audit, antivirus or security logs."
            ),
            wraplength=950,
        ).pack(anchor="w", padx=10, pady=10)

    def build_outputs(self):
        p = self.outputs_tab.inner
        ttk.Label(p, text="Generated Outputs", style="Header.TLabel").pack(anchor="w", padx=14, pady=(14, 8))
        self.output_rows = {}

        for label, path in OUTPUTS:
            row = ttk.Frame(p)
            row.pack(fill="x", padx=14, pady=4)
            state = ttk.Label(row, text="○", width=3)
            state.pack(side="left")
            ttk.Label(row, text=label, width=22).pack(side="left")
            ttk.Label(row, text=str(path), style="Muted.TLabel").pack(side="left", fill="x", expand=True)
            btn = ttk.Button(row, text="Open", command=lambda p=path: self.open_path(p))
            btn.pack(side="right")
            self.output_rows[path] = (state, btn)

        ttk.Button(p, text="Refresh Outputs", command=self.refresh_outputs).pack(anchor="e", padx=14, pady=12)

    def build_log(self):
        frame = self.log_tab
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", padx=8, pady=8)
        ttk.Button(toolbar, text="Clear Log", command=lambda: self.log_text.delete("1.0", "end")).pack(side="left")
        ttk.Button(toolbar, text="Copy Log", command=self.copy_log).pack(side="left", padx=5)

        self.log_text = tk.Text(
            frame,
            bg="#050a13",
            fg="#d9e6ff",
            insertbackground="white",
            wrap="word",
            font=("Consolas", 10),
        )
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def browse_apk(self):
        path = filedialog.askopenfilename(
            title="Choose APK",
            filetypes=[("Android APK", "*.apk"), ("All files", "*.*")],
        )
        if path:
            self.set_target(path)

    def browse_file(self):
        path = filedialog.askopenfilename(title="Choose File")
        if path:
            self.set_target(path)

    def browse_folder(self):
        path = filedialog.askdirectory(title="Choose Project Folder")
        if path:
            self.set_target(path)

    def set_target(self, value):
        self.target.set(value)
        p = Path(value)
        if p.is_file() and p.suffix.lower() == ".apk":
            self.target_type.set("Target type: APK")
            if not self.selected_mode.get().startswith("/apk"):
                self.selected_mode.set("/apk360")
            try:
                self.current_target_record = register_target(p, p.name)
                if self.current_target_record.get("lastPlan"):
                    plan=set(self.current_target_record["lastPlan"])
                    for key,var in self.apk_plan_vars.items():
                        var.set(key in plan)
                self.target_type.set(f"Target type: APK · Library ID {self.current_target_record['id']}")
                self.refresh_library_view()
            except Exception as exc:
                self.status.set(f"Library warning: {exc}")
        elif p.is_dir():
            self.target_type.set("Target type: Project / Folder")
            if self.selected_mode.get().startswith("/apk"):
                self.selected_mode.set("/360")
        elif p.is_file():
            self.target_type.set("Target type: Source / File")
            if self.selected_mode.get().startswith("/apk"):
                self.selected_mode.set("/360")
        else:
            self.target_type.set("Target not found")

    def select_mode(self, mode):
        self.selected_mode.set(mode)
        self.status.set(f"Mode selected: {mode}")

    def apply_quick(self, mode, opts):
        self.selected_mode.set(mode)
        for name, value in opts.items():
            var = getattr(self, name, None)
            if isinstance(var, tk.BooleanVar):
                var.set(value)
        self.status.set(f"Quick action ready: {mode}")

    def build_command(self):
        target = self.target.get().strip()
        if not target:
            raise ValueError("Choose an APK, file or project folder first.")
        p = Path(target)
        if not p.exists():
            raise ValueError("Selected target does not exist.")

        if not MASTER.exists():
            raise ValueError(f"Missing master launcher: {MASTER}")

        mode = self.selected_mode.get()
        is_apk = p.is_file() and p.suffix.lower() == ".apk"
        if is_apk and not mode.startswith("/apk"):
            raise ValueError("APK target selected. Choose a mode from the APK tab, such as /apk360.")
        if is_apk:
            checks=self.selected_apk_checks()
            if not checks:
                raise ValueError("Select at least one APK target check in the Target Plan tab.")
            cmd_checks=",".join(checks)
            if not self.current_target_record:
                self.current_target_record=register_target(p,p.name)
            set_plan(
                self.current_target_record["id"], checks, mode,
                {"decompile":self.decompile.get(),"keepDecompiled":self.keep_decompiled.get(),"cleanup":self.cleanup.get()}
            )
        if not is_apk and mode.startswith("/apk"):
            raise ValueError("Project/source target selected. Choose a Security, Code, Network, or Pre-scan mode.")

        cmd = [
            sys.executable,
            str(MASTER),
            "--target",
            str(p),
            "--mode",
            mode,
        ]

        if is_apk:
            cmd.extend(["--checks", cmd_checks])
        if self.resolve_urls.get():
            cmd.append("--resolve-urls")
        if self.live_monitor.get():
            cmd.append("--live-monitor")
        if self.capture_all_code.get():
            cmd.append("--capture-all-code")
        if self.copy_public_certs.get():
            cmd.append("--copy-public-certs")
        if self.decompile.get():
            cmd.append("--decompile")
        if self.keep_decompiled.get():
            cmd.append("--keep-decompiled")
        if self.cleanup.get():
            cmd.append("--cleanup")
        if self.no_persist_events.get():
            cmd.append("--no-persist-events")
        if self.no_open.get():
            cmd.append("--no-open")
        return cmd

    def run_scan(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Lola", "A scan is already running.")
            return

        try:
            cmd = self.build_command()
        except ValueError as exc:
            messagebox.showwarning("Lola", str(exc))
            return

        self.log_text.insert("end", "\n" + "=" * 80 + "\n")
        self.log_text.insert("end", "START: " + " ".join(cmd) + "\n")
        self.log_text.see("end")
        self.status.set("Running…")

        def worker():
            try:
                kwargs = {
                    "cwd": str(ROOT),
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.STDOUT,
                    "text": True,
                    "bufsize": 1,
                    "universal_newlines": True,
                }
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

                self.process = subprocess.Popen(cmd, **kwargs)
                assert self.process.stdout is not None
                for line in self.process.stdout:
                    self.log_queue.put(line)
                rc = self.process.wait()
                self.log_queue.put(f"\n[LOLA] Process finished with exit code {rc}\n")
                self.log_queue.put("__LOLA_DONE__")
            except Exception as exc:
                self.log_queue.put(f"\n[ERROR] {exc}\n")
                self.log_queue.put("__LOLA_DONE__")

        threading.Thread(target=worker, daemon=True).start()

    def stop_scan(self):
        if not self.process or self.process.poll() is not None:
            self.status.set("No active scan")
            return

        if not messagebox.askyesno("Stop Lola", "Stop the current Lola scan?"):
            return

        try:
            self.process.terminate()
            time.sleep(0.2)
            if self.process.poll() is None:
                self.process.kill()
            self.status.set("Stopped")
            self.log_text.insert("end", "\n[LOLA] Scan stopped by user.\n")
        except Exception as exc:
            messagebox.showerror("Lola", str(exc))

    def pump_logs(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item == "__LOLA_DONE__":
                    self.status.set("Finished")
                    self.refresh_outputs()
                    self.refresh_library_view()
                    continue
                self.log_text.insert("end", item)
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.after(120, self.pump_logs)

    def refresh_outputs(self):
        if hasattr(self, "output_rows"):
            for path, (state, btn) in self.output_rows.items():
                exists = path.exists()
                state.configure(text="●" if exists else "○")
                btn.configure(state="normal" if exists else "disabled")

    def poll_outputs(self):
        self.refresh_outputs()
        self.after(2500, self.poll_outputs)

    def open_path(self, path: Path):
        if not path.exists():
            messagebox.showinfo("Lola", f"Output not found yet:\n{path}")
            return
        try:
            if path.suffix.lower() in {".html", ".htm"}:
                webbrowser.open(path.resolve().as_uri())
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Lola", str(exc))

    def open_best_report(self):
        target = Path(self.target.get()) if self.target.get() else None
        apk = bool(target and target.suffix.lower() == ".apk")
        preferred = ROOT / ("apk-report.html" if apk else "semgrep-report.html")
        if preferred.exists():
            self.open_path(preferred)
            return
        self.open_path(ROOT / "apk-report.html" if (ROOT / "apk-report.html").exists() else ROOT / "semgrep-report.html")

    def open_root(self):
        try:
            if os.name == "nt":
                os.startfile(str(ROOT))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(ROOT)])
            else:
                subprocess.Popen(["xdg-open", str(ROOT)])
        except Exception as exc:
            messagebox.showerror("Lola", str(exc))

    def copy_log(self):
        data = self.log_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(data)
        self.status.set("Log copied")

    def on_close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Exit Lola", "A scan is running. Stop it and exit?"):
                return
            try:
                self.process.terminate()
            except Exception:
                pass
        self.destroy()


def main():
    if not MASTER.exists():
        messagebox.showerror("Lola", f"Missing master launcher:\n{MASTER}")
        return 1
    app = LolaUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
