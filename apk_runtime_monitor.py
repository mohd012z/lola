#!/usr/bin/env python3
"""Read-only runtime observer for an authorized installed Android package.

Uses ADB/logcat only. It does not install, patch, proxy, intercept TLS, automate purchases,
alter subscriptions, or change app/device state.
"""
from __future__ import annotations
import argparse, json, os, re, shutil, signal, subprocess, sys, time
from collections import Counter
from pathlib import Path

SECRET_RE=re.compile(r"""(?ix)
\b(authorization|bearer|access[_-]?token|refresh[_-]?token|purchase[_-]?token|api[_-]?key|client[_-]?secret|password|passwd|pwd)
(\s*[:=]\s*|\s+)(["']?)([A-Za-z0-9._~+/=-]{6,})(["']?)
""")
URL_QUERY_SECRET_RE=re.compile(r"""(?ix)([?&](?:token|access_token|refresh_token|key|api_key|apikey|auth|authorization|password|secret|signature|sig|client_secret)=)[^&\s]+""")
CATEGORIES={
 "billing":re.compile(r"(?i)\b(BillingClient|BillingResult|BillingResponseCode|ProductDetails|Purchase|PurchasesUpdatedListener|launchBillingFlow|queryProductDetailsAsync|queryPurchasesAsync|acknowledgePurchase|consumeAsync)\b"),
 "subscription":re.compile(r"(?i)\b(subscription|SUBS|basePlan|offerToken|replacementMode|renew|entitlement|purchaseToken)\b"),
 "callback":re.compile(r"(?i)\b(onPurchasesUpdated|onProductDetailsResponse|onBillingSetupFinished|onBillingServiceDisconnected|on[A-Z]\w*|callback|listener)\b"),
 "fallback":re.compile(r"(?i)\b(fallback|retry|reconnect|backoff|SERVICE_DISCONNECTED|timeout|catch|exception|failed|failure)\b"),
 "verify":re.compile(r"(?i)\b(verify|verification|signature|acknowledge|isAcknowledged|purchaseState|PURCHASED|PENDING|server|backend)\b"),
 "network":re.compile(r"(?i)\b(https?://|okhttp|retrofit|volley|websocket|dns|socket)\b"),
 "lifecycle":re.compile(r"(?i)\b(ActivityTaskManager|ActivityManager|onCreate|onStart|onResume|onPause|onStop|onDestroy)\b"),
 "error":re.compile(r"(?i)\b(FATAL EXCEPTION|AndroidRuntime|Exception|Error|ANR|crash)\b"),
}

def redact(line:str)->str:
    line=SECRET_RE.sub(lambda m:f"{m.group(1)}{m.group(2)}<REDACTED>",line)
    return URL_QUERY_SECRET_RE.sub(lambda m:m.group(1)+"<REDACTED>",line)

def adb(args,timeout=15):
    p=subprocess.run(["adb",*args],capture_output=True,text=True,timeout=timeout,errors="ignore")
    return p.returncode,p.stdout.strip(),p.stderr.strip()

def connected_devices():
    rc,out,err=adb(["devices"])
    if rc:return []
    rows=[]
    for line in out.splitlines()[1:]:
        if "\tdevice" in line:
            rows.append(line.split("\t",1)[0].strip())
    return rows

def classify(line):
    return [k for k,p in CATEGORIES.items() if p.search(line)]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--package",required=True)
    ap.add_argument("--duration",type=int,default=120)
    ap.add_argument("--output",default="runtime-analysis.json")
    ap.add_argument("--events",default="runtime-events.jsonl")
    args=ap.parse_args()

    if not shutil.which("adb"):
        raise SystemExit("ADB not found. Runtime test unavailable; static APK analysis still works.")
    devices=connected_devices()
    if len(devices)!=1:
        raise SystemExit(f"Expected exactly one authorized ADB device; found {len(devices)}.")

    rc,path,err=adb(["shell","pm","path",args.package])
    if rc or not path:
        raise SystemExit("Package is not installed or is not visible through the authorized ADB device.")

    rc,pid,_=adb(["shell","pidof",args.package])
    if rc or not pid.strip():
        raise SystemExit("Package is installed but not currently running. Open the test app manually, then start runtime tracing.")
    pid=pid.split()[0]

    snapshot={
      "package":args.package,"device":devices[0],"pid":pid,"packagePath":path,
      "started":time.time(),"durationRequested":max(1,min(args.duration,3600)),
      "mode":"read-only-adb-logcat","events":[],"counts":{}
    }
    events_path=Path(args.events)
    output_path=Path(args.output)
    counts=Counter()
    cmd=["adb","logcat","--pid",pid,"-v","threadtime"]
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,errors="ignore")
    deadline=time.time()+snapshot["durationRequested"]
    try:
        with events_path.open("w",encoding="utf-8") as ef:
            while time.time()<deadline:
                line=proc.stdout.readline() if proc.stdout else ""
                if not line:
                    if proc.poll() is not None:break
                    time.sleep(.05);continue
                safe=redact(line.rstrip())
                cats=classify(safe)
                if not cats:continue
                for cat in cats:counts[cat]+=1
                event={"time":time.time(),"categories":cats,"line":safe[:3000]}
                ef.write(json.dumps(event,ensure_ascii=False)+"\n")
                ef.flush()
                if len(snapshot["events"])<500:
                    snapshot["events"].append(event)
    except KeyboardInterrupt:
        pass
    finally:
        try:proc.terminate()
        except Exception:pass
        try:proc.wait(timeout=2)
        except Exception:
            try:proc.kill()
            except Exception:pass

    snapshot["finished"]=time.time()
    snapshot["counts"]=dict(counts)
    snapshot["eventsFile"]=str(events_path.resolve())
    snapshot["note"]="Read-only logcat observation. No payment/subscription state is modified and no network interception is performed."
    output_path.write_text(json.dumps(snapshot,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"ok":True,"package":args.package,"pid":pid,"counts":dict(counts),"output":str(output_path.resolve())}))

if __name__=="__main__":
    main()
