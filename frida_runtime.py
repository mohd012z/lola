#!/usr/bin/env python3
"""Lola safe Frida runtime runner.

Attach-only instrumentation for apps/builds the tester owns or is authorized to test.
No APK patching/installing, no pinning/root bypasses, no purchase modification.
"""

from __future__ import annotations

import argparse
import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from frida_library import build_script, catalog

MAX_DURATION=3600

def require_authorized(v: bool):
    if not v:
        raise SystemExit("Authorization acknowledgement required (--authorized).")

def ensure_frida():
    try:
        import frida
        return frida
    except Exception:
        raise SystemExit("Python Frida bindings are not installed. Install the official frida Python package in your authorized test environment.")

def adb_forward(port:int):
    if not shutil.which("adb"):
        return False, "adb unavailable"
    p=subprocess.run(["adb","forward",f"tcp:{port}",f"tcp:{port}"],capture_output=True,text=True,timeout=10)
    if p.returncode!=0:
        return False,(p.stderr or p.stdout or "adb forward failed").strip()
    return True,"ok"

def choose_device(frida, mode:str, remote:str, gadget_port:int):
    if remote:
        return frida.get_device_manager().add_remote_device(remote), f"remote:{remote}"
    if mode=="gadget":
        adb_forward(gadget_port)
        endpoint=f"127.0.0.1:{gadget_port}"
        return frida.get_device_manager().add_remote_device(endpoint), f"gadget:{endpoint}"
    # Root/frida-server attach. Prefer USB host connection, then localhost server.
    try:
        return frida.get_usb_device(timeout=5), "usb/frida-server"
    except Exception:
        endpoint=f"127.0.0.1:{gadget_port}"
        return frida.get_device_manager().add_remote_device(endpoint), f"server:{endpoint}"

def find_process(device, package:str):
    procs=device.enumerate_processes()
    exact=[p for p in procs if p.name==package]
    if exact:return exact[0]
    # Some process names use package:service suffix.
    pref=[p for p in procs if p.name.startswith(package+":")]
    if pref:return pref[0]
    # Android app identifiers may be exposed in application list instead.
    try:
        apps=device.enumerate_applications()
        app=next((a for a in apps if a.identifier==package),None)
        if app and app.pid:
            return type("Proc",(),{"pid":app.pid,"name":app.identifier})()
    except Exception:
        pass
    return None

def redact_event(obj):
    # Probe scripts intentionally avoid secret values. Keep a final defensive sanitizer.
    import re
    raw=json.dumps(obj,ensure_ascii=False)
    raw=re.sub(r'(?i)("?(?:authorization|access[_-]?token|refresh[_-]?token|password|secret|api[_-]?key)"?\s*[:=]\s*")([^"]+)(")',r'\1<REDACTED>\3',raw)
    try:return json.loads(raw)
    except Exception:return {"kind":"message","data":{"text":"<redacted/unparsed>"}}

def main():
    ap=argparse.ArgumentParser(description="Safe read-only Frida observer")
    ap.add_argument("--package",required=True)
    ap.add_argument("--mode",choices=["root-server","gadget"],default="gadget")
    ap.add_argument("--probes",default="overview,classes,lifecycle,urls,dns,intents,storage,crypto,billing,callbacks,timers")
    ap.add_argument("--duration",type=int,default=120)
    ap.add_argument("--output",default="frida-analysis.json")
    ap.add_argument("--events",default="frida-events.jsonl")
    ap.add_argument("--remote",default="")
    ap.add_argument("--gadget-port",type=int,default=27042)
    ap.add_argument("--authorized",action="store_true")
    args=ap.parse_args()

    require_authorized(args.authorized)
    frida=ensure_frida()
    allowed={x["id"] for x in catalog()["probes"]}
    probes=[x.strip() for x in args.probes.split(",") if x.strip() in allowed]
    if not probes:
        raise SystemExit("No valid Frida probes selected.")

    duration=max(5,min(args.duration,MAX_DURATION))
    out_path=Path(args.output)
    events_path=Path(args.events)
    device,transport=choose_device(frida,args.mode,args.remote,args.gadget_port)
    proc=find_process(device,args.package)
    if not proc:
        raise SystemExit("Target package is not currently running. Open your authorized test app manually, then attach.")

    session=device.attach(proc.pid)
    script=session.create_script(build_script(args.package,probes))
    q=queue.Queue()
    counts={}

    def on_message(message,data):
        if message.get("type")=="send":
            ev=redact_event(message.get("payload") or {})
        else:
            ev={"kind":"frida-error","time":int(time.time()*1000),"data":{"description":str(message.get("description") or message.get("stack") or "Frida script error")[:1500]}}
        q.put(ev)

    script.on("message",on_message)
    script.load()

    summary={
        "package":args.package,"pid":proc.pid,"mode":args.mode,"transport":transport,
        "probes":probes,"started":time.time(),"durationRequested":duration,
        "events":[],"counts":{},"observationOnly":True,
        "note":"Attach-only authorized instrumentation. No bypass, tampering, purchase modification, secret dumping, or TLS interception."
    }

    deadline=time.time()+duration
    try:
        with events_path.open("w",encoding="utf-8") as ef:
            while time.time()<deadline:
                try: ev=q.get(timeout=.25)
                except queue.Empty: continue
                kind=str(ev.get("kind") or "message")
                counts[kind]=counts.get(kind,0)+1
                ef.write(json.dumps(ev,ensure_ascii=False)+"\n")
                ef.flush()
                if len(summary["events"])<600:summary["events"].append(ev)
    except KeyboardInterrupt:
        pass
    finally:
        try: script.unload()
        except Exception: pass
        try: session.detach()
        except Exception: pass

    summary["finished"]=time.time()
    summary["counts"]=counts
    summary["eventsFile"]=str(events_path.resolve())
    out_path.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"ok":True,"package":args.package,"mode":args.mode,"transport":transport,"counts":counts,"output":str(out_path.resolve())}))

if __name__=="__main__":
    main()
