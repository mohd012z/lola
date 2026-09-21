#!/usr/bin/env python3
"""Safe internal Frida instrumentation library for Lola.

Designed for apps/builds the tester owns or is authorized to instrument.
Probes are observation-only and redact or avoid sensitive values.
"""

from __future__ import annotations
from typing import Any

FRIDA_MODES = [
    {
        "id":"root-server","label":"Root / frida-server","rootRequired":True,
        "description":"Attach through an already-running frida-server on an authorized rooted test device/emulator."
    },
    {
        "id":"gadget","label":"Unrooted / Frida Gadget","rootRequired":False,
        "description":"Attach to Frida Gadget embedded in an app/test build you own or are authorized to instrument."
    },
    {
        "id":"adb-logcat","label":"Unrooted / ADB logcat fallback","rootRequired":False,
        "description":"Read-only categorized logcat observer when Frida injection is unavailable."
    },
]

RELATED_TOOLS = [
    {"id":"frida-python","label":"Frida Python bindings","purpose":"Session/device/script control","optional":True},
    {"id":"frida-tools","label":"Frida CLI tools","purpose":"frida, frida-ps, frida-trace utilities","optional":True},
    {"id":"frida-server","label":"Frida Server","purpose":"Rooted-device attach backend","optional":True,"root":True},
    {"id":"frida-gadget","label":"Frida Gadget","purpose":"Embedded instrumentation backend for authorized unrooted test builds","optional":True,"root":False},
    {"id":"adb","label":"Android Debug Bridge","purpose":"Device discovery, forwarding and logcat fallback","optional":True},
    {"id":"jadx","label":"JADX","purpose":"Static/decompiled source context","optional":True},
    {"id":"apktool","label":"APKTool","purpose":"Manifest/resource context","optional":True},
]

PROBES = [
    {"id":"overview","label":"Process Overview","description":"App package, process/session and loaded app classes","sensitive":False},
    {"id":"classes","label":"App Classes","description":"Enumerate loaded classes under the app package prefix only","sensitive":False},
    {"id":"methods","label":"Interesting Methods","description":"List method names for app classes matching billing/auth/network/callback/storage terms","sensitive":False},
    {"id":"lifecycle","label":"Activity Lifecycle","description":"Observe Activity onCreate/onStart/onResume/onPause/onStop/onDestroy","sensitive":False},
    {"id":"urls","label":"URL Open","description":"Observe URL strings and connection destinations; no request/response bodies","sensitive":False},
    {"id":"dns","label":"DNS","description":"Observe hostname lookups and resolved addresses","sensitive":False},
    {"id":"intents","label":"Intents","description":"Observe Intent action/component/category and extra-key names, not extra values","sensitive":False},
    {"id":"storage","label":"Storage Writes","description":"Observe SharedPreferences key names and value lengths/types, not secret values","sensitive":False},
    {"id":"crypto","label":"Crypto Metadata","description":"Observe cipher/KDF/key algorithm and sizes only; never dump key bytes/plaintext","sensitive":False},
    {"id":"billing","label":"Billing Signals","description":"Observe Google Play Billing method/callback names and response codes without changing purchase state","sensitive":False},
    {"id":"callbacks","label":"Callbacks","description":"Observe app callback/listener method names in matching classes","sensitive":False},
    {"id":"timers","label":"Timers","description":"Observe delayed tasks and delays without modifying scheduling","sensitive":False},
]

SAFE_JS = r"""
'use strict';
const CFG = __CFG__;
const OUT = (kind, data) => send({kind: kind, time: Date.now(), data: data || {}});
const safe = (x, n) => {
  try {
    const s = String(x === null || x === undefined ? '' : x);
    return s.length > (n || 500) ? s.slice(0, n || 500) + '…' : s;
  } catch (_) { return ''; }
};
const enabled = (name) => (CFG.probes || []).indexOf(name) !== -1;
const pkg = CFG.package || '';

Java.perform(function () {
  OUT('session', {package: pkg, probes: CFG.probes || []});

  if (enabled('classes') || enabled('overview') || enabled('methods') || enabled('callbacks') || enabled('billing')) {
    const matches = [];
    Java.enumerateLoadedClasses({
      onMatch: function (name) {
        if (!pkg || name.indexOf(pkg) === 0) {
          if (matches.length < 3000) matches.push(name);
        }
      },
      onComplete: function () {
        OUT('classes', {count: matches.length, items: matches.slice(0, 1500)});
        if (enabled('methods') || enabled('callbacks') || enabled('billing')) {
          const rx = /(bill|purch|subscr|payment|callback|listener|auth|login|token|network|http|storage|pref|database|verify|receipt)/i;
          matches.filter(x => rx.test(x)).slice(0, 180).forEach(function (name) {
            try {
              const c = Java.use(name);
              const methods = c.class.getDeclaredMethods();
              const names = [];
              for (let i = 0; i < methods.length && i < 120; i++) names.push(methods[i].getName().toString());
              OUT('methods', {className: name, methods: names});
            } catch (_) {}
          });
        }
      }
    });
  }

  if (enabled('lifecycle')) {
    try {
      const Activity = Java.use('android.app.Activity');
      ['onCreate','onStart','onResume','onPause','onStop','onDestroy'].forEach(function (m) {
        try {
          const ovs = Activity[m].overloads;
          ovs.forEach(function (ov) {
            ov.implementation = function () {
              OUT('lifecycle', {event: m, activity: this.getClass().getName().toString()});
              return ov.apply(this, arguments);
            };
          });
        } catch (_) {}
      });
    } catch (_) {}
  }

  if (enabled('urls')) {
    try {
      const URL = Java.use('java.net.URL');
      URL.$init.overload('java.lang.String').implementation = function (u) {
        OUT('url', {url: safe(u, 1000)});
        return this.$init(u);
      };
    } catch (_) {}
  }

  if (enabled('dns')) {
    try {
      const InetAddress = Java.use('java.net.InetAddress');
      const ov = InetAddress.getAllByName.overload('java.lang.String');
      ov.implementation = function (host) {
        const out = ov.call(this, host);
        const ips = [];
        try { for (let i=0; i<out.length && i<12; i++) ips.push(out[i].getHostAddress().toString()); } catch (_) {}
        OUT('dns', {host: safe(host, 300), addresses: ips});
        return out;
      };
    } catch (_) {}
  }

  if (enabled('intents')) {
    try {
      const ContextWrapper = Java.use('android.content.ContextWrapper');
      const ov = ContextWrapper.startActivity.overload('android.content.Intent');
      ov.implementation = function (intent) {
        let action='', component='', categories=[];
        try { action=safe(intent.getAction(),300); } catch (_) {}
        try { const c=intent.getComponent(); component=c?safe(c.flattenToShortString(),500):''; } catch (_) {}
        try {
          const cats=intent.getCategories();
          if (cats) {
            const it=cats.iterator();
            while(it.hasNext() && categories.length<20) categories.push(safe(it.next(),200));
          }
        } catch (_) {}
        OUT('intent', {action:action, component:component, categories:categories});
        return ov.call(this, intent);
      };
    } catch (_) {}
  }

  if (enabled('storage')) {
    try {
      const Editor = Java.use('android.app.SharedPreferencesImpl$EditorImpl');
      const ps = Editor.putString.overload('java.lang.String','java.lang.String');
      ps.implementation = function (key, value) {
        OUT('storage', {op:'putString', key:safe(key,300), valueLength:value?String(value).length:0});
        return ps.call(this,key,value);
      };
      const pb = Editor.putBoolean.overload('java.lang.String','boolean');
      pb.implementation = function (key, value) {
        OUT('storage', {op:'putBoolean', key:safe(key,300), valueType:'boolean'});
        return pb.call(this,key,value);
      };
    } catch (_) {}
  }

  if (enabled('crypto')) {
    try {
      const Cipher = Java.use('javax.crypto.Cipher');
      const gi = Cipher.getInstance.overload('java.lang.String');
      gi.implementation = function (transformation) {
        OUT('crypto', {event:'Cipher.getInstance', transformation:safe(transformation,200)});
        return gi.call(this,transformation);
      };
    } catch (_) {}
    try {
      const SKS = Java.use('javax.crypto.spec.SecretKeySpec');
      const init = SKS.$init.overload('[B','java.lang.String');
      init.implementation = function (key, algo) {
        OUT('crypto', {event:'SecretKeySpec', algorithm:safe(algo,100), keyLength:key?key.length:0});
        return init.call(this,key,algo);
      };
    } catch (_) {}
  }

  if (enabled('billing')) {
    try {
      const BC = Java.use('com.android.billingclient.api.BillingClient');
      OUT('billing', {event:'BillingClient available'});
    } catch (_) {
      OUT('billing', {event:'BillingClient class not loaded'});
    }
  }

  if (enabled('timers')) {
    try {
      const Handler = Java.use('android.os.Handler');
      const pd = Handler.postDelayed.overload('java.lang.Runnable','long');
      pd.implementation = function (r, delay) {
        if (delay >= 1000) OUT('timer', {delayMs:Number(delay)});
        return pd.call(this,r,delay);
      };
    } catch (_) {}
  }
});
"""

def catalog() -> dict[str, Any]:
    return {
        "modes": FRIDA_MODES,
        "tools": RELATED_TOOLS,
        "probes": PROBES,
        "safety": {
            "observationOnly": True,
            "excluded": [
                "certificate-pinning bypass",
                "root/Frida hiding",
                "premium/subscription/receipt tampering",
                "payment modification",
                "secret/private-key extraction",
                "response manipulation",
            ],
        },
    }

def build_script(package: str, probes: list[str]) -> str:
    import json
    allowed={x["id"] for x in PROBES}
    cfg={"package":package,"probes":[x for x in probes if x in allowed]}
    return SAFE_JS.replace("__CFG__",json.dumps(cfg,separators=(",",":")))
