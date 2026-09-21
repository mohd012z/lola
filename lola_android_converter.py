"""Android bytecode conversion plans and safe tool adapters for Lola.

Uses standard external tools when available.  Conversion operates only on a
user-selected file/workspace and never installs, runs, signs, or patches an APK.
"""
from __future__ import annotations
import shutil, subprocess
from pathlib import Path

def tools():
    return {"java":shutil.which("java"),"jadx":shutil.which("jadx") or shutil.which("jadx-gui"),
            "baksmali":shutil.which("baksmali"),"smali":shutil.which("smali")}

def _run(argv,cwd=None,timeout=300):
    p=subprocess.run(argv,cwd=cwd,capture_output=True,text=True,timeout=timeout,check=False)
    return {"argv":argv,"returncode":p.returncode,"stdout":p.stdout[-20000:],"stderr":p.stderr[-20000:]}

def dex_to_smali(dex,out):
    dex=Path(dex);out=Path(out);out.mkdir(parents=True,exist_ok=True);t=tools()
    if t["baksmali"]:return _run([t["baksmali"],"d",str(dex),"-o",str(out)])
    return {"ok":False,"missing":"baksmali","plan":["baksmali","d",str(dex),"-o",str(out)],
            "note":"Install/detect baksmali; Lola does not substitute fabricated smali."}

def smali_to_dex(smali_dir,out_dex):
    src=Path(smali_dir);dst=Path(out_dex);dst.parent.mkdir(parents=True,exist_ok=True);t=tools()
    if t["smali"]:return _run([t["smali"],"a",str(src),"-o",str(dst)])
    return {"ok":False,"missing":"smali","plan":["smali","a",str(src),"-o",str(dst)]}

def dex_to_java(dex,out):
    dex=Path(dex);out=Path(out);out.mkdir(parents=True,exist_ok=True);t=tools()
    jadx=t["jadx"]
    if jadx and Path(jadx).name!="jadx-gui":return _run([jadx,"-d",str(out),str(dex)])
    return {"ok":False,"missing":"jadx-cli","plan":["jadx","-d",str(out),str(dex)],
            "note":"Java is decompiler output and may differ from original source."}

def apk_to_java(apk,out):
    return dex_to_java(apk,out)

def conversion_matrix():
    return [
      {"from":"DEX","to":"SMALI","method":"baksmali disassembly","fidelity":"bytecode-oriented"},
      {"from":"SMALI","to":"DEX","method":"smali assembly","fidelity":"assembled bytecode"},
      {"from":"DEX/APK","to":"JAVA","method":"JADX decompilation","fidelity":"reconstructed source"},
      {"from":"SMALI","to":"JAVA","method":"assemble temporary DEX then JADX","fidelity":"reconstructed source"},
      {"from":"JAVA","to":"DEX","method":"project compiler/D8 required","fidelity":"new compilation, not original DEX"},
    ]

def smali_to_java(smali_dir,out,work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True);dex=work/"classes.dex"
    a=smali_to_dex(smali_dir,dex)
    if a.get("returncode")!=0:return {"assemble":a}
    return {"assemble":a,"decompile":dex_to_java(dex,out)}
