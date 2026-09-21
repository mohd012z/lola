#!/usr/bin/env python3
import argparse, json, ipaddress
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

PUBLIC_IP_SERVICES=("ipify","ipinfo","ifconfig","icanhazip","my-ip","ipapi","ip-api","whatismyip")

def read_json(path, default):
    p=Path(path)
    if not p.exists(): return default
    try: return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception: return default

def classify_ip(raw):
    try:
        ip=ipaddress.ip_address(str(raw).split("%",1)[0])
        if ip.is_global: return "public"
        if ip.is_loopback: return "loopback"
        if ip.is_private: return "private"
        if ip.is_link_local: return "link-local"
        if ip.is_reserved: return "reserved"
        if ip.is_multicast: return "multicast"
        if ip.is_unspecified: return "unspecified"
        return "non-public"
    except Exception:
        return "unknown"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--urls",default="url-report.json")
    ap.add_argument("--semgrep",default="semgrep-results.json")
    ap.add_argument("--code",default="code-analysis.json")
    ap.add_argument("--manifest",default="target-manifest.json")
    ap.add_argument("--output",default="network-analysis.json")
    args=ap.parse_args()

    urls=read_json(args.urls,{"urls":[]})
    sem=read_json(args.semgrep,{"results":[]})
    code=read_json(args.code,{})
    manifest=read_json(args.manifest,{"files":[]})

    traces=[]
    domains=Counter()
    protocols=Counter()
    public_ips=Counter()
    private_ips=Counter()
    redirect_count=0
    tls_count=0
    realip_refs=[]

    nodes={}
    edges=[]
    def add_node(node_id,label,kind,meta=None):
        if node_id not in nodes:
            nodes[node_id]={"id":node_id,"label":label,"kind":kind,"meta":meta or {}}
    def add_edge(a,b,label):
        edges.append({"from":a,"to":b,"label":label})

    for idx,u in enumerate(urls.get("urls",[])):
        src=u.get("sourceUrl","")
        final=u.get("finalUrl","")
        host=u.get("host","") or (urlsplit(src).hostname if src else "")
        scheme=(u.get("scheme","") or (urlsplit(src).scheme if src else "")).lower()
        if host: domains[host]+=1
        if scheme: protocols[scheme]+=1
        ips=u.get("resolvedIps",[]) or []
        for ip in ips:
            cls=classify_ip(ip)
            (public_ips if cls=="public" else private_ips)[ip]+=1
        redirects=u.get("redirects",[]) or []
        redirect_count += len(redirects)
        if (u.get("tls") or {}).get("version"): tls_count += 1

        if any(x in (host or "").lower() or x in src.lower() for x in PUBLIC_IP_SERVICES):
            realip_refs.append({"sourceUrl":src,"host":host,"occurrences":u.get("occurrences",[])})

        trace={
            "sourceUrl":src,"finalUrl":final,"host":host,"scheme":scheme,
            "status":u.get("status"),"destinationClass":u.get("destinationClass",""),
            "resolvedIps":ips,"redirects":redirects,"tls":u.get("tls",{}),
            "occurrences":u.get("occurrences",[]),"error":u.get("error","")
        }
        traces.append(trace)

        src_id=f"url:{idx}:source"
        add_node(src_id,src or "[url]","url",{"status":u.get("status")})
        if host:
            host_id=f"host:{host}"
            add_node(host_id,host,"host")
            add_edge(src_id,host_id,"host")
            for ip in ips:
                ip_id=f"ip:{ip}"
                add_node(ip_id,ip,"ip",{"class":classify_ip(ip)})
                add_edge(host_id,ip_id,"dns")
        prev=src_id
        for ri,r in enumerate(redirects):
            to=r.get("to","")
            if not to: continue
            rid=f"url:{idx}:redirect:{ri}"
            add_node(rid,to,"redirect",{"status":r.get("status")})
            add_edge(prev,rid,f"HTTP {r.get('status','')}".strip())
            prev=rid
        if final and final!=src:
            fid=f"url:{idx}:final"
            add_node(fid,final,"final-url",{"status":u.get("status")})
            add_edge(prev,fid,"final")

        for occ in u.get("occurrences",[]) or []:
            p=occ.get("path","")
            if p:
                file_id=f"file:{p}"
                add_node(file_id,p,"source-file")
                add_edge(file_id,src_id,f"line {occ.get('line','?')}")

    routes=(code.get("extraction",{}) or {}).get("routes",[]) or []
    route_items=[]
    for i,r in enumerate(routes):
        route_items.append(r)
        rid=f"route:{i}"
        label=f"{r.get('method','')} {r.get('route','')}".strip()
        add_node(rid,label,"app-route",{"path":r.get("path"),"line":r.get("line")})
        if r.get("path"):
            fid=f"file:{r['path']}"
            add_node(fid,r["path"],"source-file")
            add_edge(fid,rid,f"line {r.get('line','?')}")

    network_findings=[]
    for r in sem.get("results",[]):
        ex=r.get("extra") or {}
        md=ex.get("metadata") or {}
        surface=str(md.get("surface") or md.get("category") or "")
        if surface in {
            "network-addresses","private-network","client-ip","proxy-trust","listeners","dns",
            "cleartext-http","tls","protocol","raw-socket","privacy-network-exposure",
            "device-local-network","privacy-ip-exposure"
        }:
            network_findings.append({
                "rule":r.get("check_id",""),"severity":str(ex.get("severity") or "INFO").upper(),
                "message":ex.get("message",""),"path":r.get("path",""),
                "line":(r.get("start") or {}).get("line",0),"surface":surface
            })

    visible={
        "publicHosts":[{"host":h,"references":c} for h,c in domains.most_common()],
        "publicIps":[{"ip":ip,"references":c} for ip,c in public_ips.most_common()],
        "nonPublicIps":[{"ip":ip,"class":classify_ip(ip),"references":c} for ip,c in private_ips.most_common()],
        "networkFindings":network_findings,
        "note":"This is source/resolution visibility, not an external port scan."
    }

    out={
        "summary":{
            "files":manifest.get("fileCount",len(manifest.get("files",[]))),
            "urls":len(traces),"domains":len(domains),"publicIps":len(public_ips),
            "nonPublicIps":len(private_ips),"redirectHops":redirect_count,
            "tlsEndpoints":tls_count,"appRoutes":len(route_items),
            "networkFindings":len(network_findings),"realIpServiceRefs":len(realip_refs)
        },
        "trace":{"items":traces},
        "route":{"items":route_items},
        "map":{"nodes":list(nodes.values()),"edges":edges},
        "visible":visible,
        "realip":{
            "resolvedPublicIps":[{"ip":ip,"references":c} for ip,c in public_ips.most_common()],
            "publicIpDiscoveryReferences":realip_refs,
            "deviceCurrentPublicIp":None,
            "note":"A browser cannot know its reliable public IP without contacting a server. Use the explicit runtime check in network-monitor.html if desired."
        },
        "protocols":dict(protocols),
        "normal":{"note":"Normal mode shows the compact network summary without deep trace expansion."}
    }
    Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Network analysis written: {Path(args.output).resolve()}")

if __name__=="__main__":
    main()
