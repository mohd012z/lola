#!/usr/bin/env python3
"""CLI for Lola universal extractor."""
import argparse, json
from pathlib import Path
from lola_extractor_core import extract, save

def main():
    ap=argparse.ArgumentParser(description="Lola read-only evidence extractor")
    ap.add_argument("target")
    ap.add_argument("-o","--output",default=".lola-extract")
    ap.add_argument("--no-numbers",action="store_true")
    ap.add_argument("--stdout",action="store_true")
    args=ap.parse_args()
    report=extract(args.target,not args.no_numbers)
    out=save(report,args.output)
    if args.stdout: print(json.dumps(report,indent=2,ensure_ascii=False))
    else:
        print("Evidence:",out/"evidence360.json")
        print("SHA-256:",report["sha256"])
        print("Kind:",report["kind"],"Size:",report["size"])
        print("Static/read-only: target was not executed.")

if __name__=="__main__":main()
