"""Targeted repair planner for Office -> HTML conversion diagnostics."""
from __future__ import annotations

def repair_plan(source, diagnostics):
    issues=diagnostics.get("issues",[])
    actions=[]
    for item in issues:
        loc=item.get("location","document"); problem=item.get("issue","")
        if loc.startswith("sheet:"):
            sheet=loc.split(":",1)[1]
            if "image" in problem:
                action="re-render-sheet-images"
            elif "chart" in problem:
                action="office-render-chart-fallback"
            elif "cell" in problem:
                action="re-render-sheet-grid"
            else:
                action="re-render-sheet"
            actions.append({"scope":"sheet","target":sheet,"action":action,"reason":problem})
        elif loc.startswith("page:"):
            page=int(loc.split(":",1)[1])
            actions.append({"scope":"page","target":page,"action":"re-render-pdf-page","reason":problem,
                            "fallback":"OCR page if searchable text is absent"})
        else:
            if "table" in problem: action="re-render-word-tables"
            elif "image" in problem: action="re-render-word-images"
            else: action="re-render-document"
            actions.append({"scope":"document","target":"document","action":action,"reason":problem})
    # Deduplicate while preserving order.
    seen=set(); unique=[]
    for a in actions:
        key=(a["scope"],str(a["target"]),a["action"])
        if key not in seen:
            seen.add(key); unique.append(a)
    return {"source":str(source),"needed":bool(unique),"actions":unique,
            "policy":"target only failed content; preserve successful rendered sections"}

def can_auto_repair(action):
    # These routes are deterministic local re-renders. Chart visual fallback may need LibreOffice.
    return action.get("action") in {"re-render-sheet-images","re-render-sheet-grid","re-render-sheet",
        "re-render-pdf-page","re-render-word-tables","re-render-word-images","re-render-document"}
