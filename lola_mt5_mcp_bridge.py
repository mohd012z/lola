"""MetaTrader 5 MCP bridge for Lola.

Connects only to an explicitly configured local/authorized MCP transport. It
discovers tools before calling them and never guesses an endpoint or credentials.
EX4/EX5 payloads are evidence summaries only; protected binaries are not sent for
decompilation or protection bypass.
"""
from __future__ import annotations
import json, os, shlex, subprocess
from pathlib import Path
from lola_extractor_core import extract

ENV_COMMAND="LOLA_MT5_MCP_COMMAND"

def configuration():
    command=os.environ.get(ENV_COMMAND,"").strip()
    return {"configured":bool(command),"transport":"stdio" if command else None,
            "command_source":ENV_COMMAND if command else None,
            "note":"Set an authorized MetaTrader/MetaEditor MCP command locally; credentials are never stored in Lola."}

def evidence_packet(path,question=None):
    p=Path(path);ext=p.suffix.lower()
    if ext not in (".mq4",".mq5",".ex4",".ex5"):
        return {"ok":False,"error":"MT4/MT5 source or compiled artifact required"}
    ev=extract(p,include_numbers=False)
    # Keep packet bounded and evidence-oriented.
    return {"ok":True,"target":{"name":p.name,"extension":ext,"size":p.stat().st_size},
            "question":question or "Inspect the available MetaTrader evidence and identify supported troubleshooting steps.",
            "evidence":{"sha256":ev.get("sha256"),"kind":ev.get("kind"),
                        "signatures":ev.get("signatures",[])[:64],
                        "strings":ev.get("strings",[])[:256]},
            "constraints":["do not claim original source recovery from EX4/EX5",
                           "do not bypass protection or guess passwords",
                           "distinguish observed evidence from inference"]}

class StdioMCP:
    def __init__(self,command=None):
        command=(command or os.environ.get(ENV_COMMAND,"")).strip()
        if not command:raise RuntimeError("MT5 MCP command is not configured")
        self.p=subprocess.Popen(shlex.split(command),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,text=True,bufsize=1)
        self.seq=0
    def rpc(self,method,params=None):
        self.seq+=1;rid=self.seq
        msg={"jsonrpc":"2.0","id":rid,"method":method}
        if params is not None:msg["params"]=params
        self.p.stdin.write(json.dumps(msg,separators=(",",":"))+"\n");self.p.stdin.flush()
        while True:
            line=self.p.stdout.readline()
            if not line:raise RuntimeError("MT5 MCP transport closed")
            obj=json.loads(line)
            if obj.get("id")==rid:
                if "error" in obj:raise RuntimeError(str(obj["error"]))
                return obj.get("result")
    def initialize(self):
        result=self.rpc("initialize",{"protocolVersion":"2025-06-18",
            "capabilities":{},"clientInfo":{"name":"lola-mt5-bridge","version":"1"}})
        # Notification has no id.
        self.p.stdin.write(json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"})+"\n");self.p.stdin.flush()
        return result
    def tools(self):return self.rpc("tools/list",{})
    def call(self,name,args):return self.rpc("tools/call",{"name":name,"arguments":args})
    def close(self):
        if self.p.poll() is None:self.p.terminate()

def _tool_rows(result):
    if isinstance(result,dict):return result.get("tools",[])
    return []

def discover():
    cfg=configuration()
    if not cfg["configured"]:return {"ok":False,"configuration":cfg,"help_required":True,
        "help":{"command":"/help","reason":"MetaTrader 5 MCP transport is not configured"}}
    c=None
    try:
        c=StdioMCP();init=c.initialize();tools=c.tools()
        return {"ok":True,"configuration":cfg,"initialize":init,"tools":_tool_rows(tools)}
    except Exception as e:
        return {"ok":False,"configuration":cfg,"error":str(e),"help_required":True,
                "help":{"command":"/help","reason":"MT5 MCP discovery failed"}}
    finally:
        if c:c.close()

def ask(path,question=None,tool_name=None):
    packet=evidence_packet(path,question)
    if not packet.get("ok"):return packet
    cfg=configuration()
    if not cfg["configured"]:return {"ok":False,"packet":packet,"configuration":cfg,"help_required":True,
        "help":{"command":"/help","reason":"Configure the authorized MT5 MCP transport before communication"}}
    c=None
    try:
        c=StdioMCP();c.initialize();listed=_tool_rows(c.tools())
        names=[x.get("name","") for x in listed]
        chosen=tool_name if tool_name in names else next((n for n in names if any(k in n.lower() for k in ("assistant","chat","ask","ai"))),None)
        if not chosen:
            return {"ok":False,"packet":packet,"available_tools":names,"help_required":True,
                    "help":{"command":"/help","reason":"No AI/assistant MCP tool was discoverable; select a tool explicitly"}}
        result=c.call(chosen,{"prompt":json.dumps(packet,ensure_ascii=False)})
        return {"ok":True,"tool":chosen,"response":result,"packet":packet}
    except Exception as e:
        return {"ok":False,"packet":packet,"error":str(e),"help_required":True,
                "help":{"command":"/help","reason":"MT5 AI communication failed"}}
    finally:
        if c:c.close()
