#!/usr/bin/env python3
"""Normalize Lola analyzer output into provenance-preserving Evidence records."""
from __future__ import annotations

from typing import Any
from lola_evidence import Evidence


def _unique(rows: list[Evidence]) -> list[Evidence]:
    out=[]; seen=set()
    for row in rows:
        key=(row.kind,row.source,row.observation,row.locator,row.tool)
        if key not in seen:
            seen.add(key); out.append(row)
    return out


def _loc(entry: Any, offset: Any=None) -> str:
    entry=str(entry or "")
    return f"{entry}@{offset}" if entry and offset is not None else entry


def apk_observations(data: dict | None) -> list[Evidence]:
    if not isinstance(data,dict): return []
    rows=[]
    for item in data.get("urls",[]) or []:
        if not isinstance(item,dict): continue
        url=str(item.get("url", ""))
        if url:
            rows.append(Evidence("apk.url","apk-analysis",url,_loc(item.get("entry"),item.get("offset")),"analyze-apk",0.75,
                                 {k:item.get(k) for k in ("host","scheme") if item.get(k) is not None}))
    for permission in data.get("permissions",[]) or []:
        if permission:
            rows.append(Evidence("apk.permission","apk-analysis",str(permission),"AndroidManifest.xml","analyze-apk",0.9))
    for item in data.get("components",[]) or []:
        if not isinstance(item,dict): continue
        name=str(item.get("name", ""))
        if name:
            rows.append(Evidence("apk.component","apk-analysis",name,"AndroidManifest.xml","analyze-apk",0.9,
                                 {k:item.get(k) for k in ("type","exported") if item.get(k) is not None}))
    for key,kind in (("api_refs","apk.api_ref"),("secret_refs","apk.secret_ref"),("webview","apk.webview"),("crypto","apk.crypto"),("indicators","apk.indicator")):
        for item in data.get(key,[]) or []:
            if not isinstance(item,dict): continue
            text=str(item.get("preview") or item.get("name") or "")
            if text:
                rows.append(Evidence(kind,"apk-analysis",text,_loc(item.get("entry"),item.get("offset")),"analyze-apk",0.65))
    return _unique(rows)


def code_observations(report: dict | None) -> list[Evidence]:
    if not isinstance(report,dict): return []
    rows=[]
    for item in report.get("files",[]) or []:
        if not isinstance(item,dict): continue
        path=str(item.get("file", ""))
        if item.get("syntax_ok") is False:
            line=item.get("line")
            rows.append(Evidence("code.syntax_error","code-inspector",str(item.get("error") or "syntax error"),
                                 f"{path}:{line}" if line else path,"lola_code_inspector",0.95))
            continue
        for imp in item.get("imports",[]) or []:
            if imp: rows.append(Evidence("code.import","code-inspector",str(imp),path,"lola_code_inspector",0.8))
        for definition in item.get("definitions",[]) or []:
            if not isinstance(definition,dict): continue
            name=str(definition.get("name", "")); line=definition.get("line")
            if name:
                rows.append(Evidence("code.definition","code-inspector",name,f"{path}:{line}" if line else path,
                                     "lola_code_inspector",0.9,{"type":definition.get("type")}))
        for call in item.get("calls",[]) or []:
            if not isinstance(call,dict): continue
            name=str(call.get("name", "")); line=call.get("line")
            if name:
                rows.append(Evidence("code.call","code-inspector",name,f"{path}:{line}" if line else path,"lola_code_inspector",0.7))
    return _unique(rows)
