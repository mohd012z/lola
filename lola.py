#!/usr/bin/env python3
r"""
Lola master launcher.

Examples:
    python lola.py "C:\Apps\sample.apk"
    python lola.py --target "C:\Projects\MyApp"
    python lola.py "C:\Apps\sample.apk" --mode /apkpermissions
    python lola.py --cognitive-smoke
    python lola.py --cognitive-loop-smoke
    python lola.py --tiny-beast-smoke
    python lola.py --tiny-beast-benchmark benchmark.json
    python lola.py --controlled-transfer-benchmark
    python lola.py --historical-replay-scanner-cwd
    python lola.py --historical-transfer-benchmark
    python lola.py --prospective-transfer-prereg
    python lola.py --prospective-holdout-observe workflow-event.json --holdout-observation-output observation.json
    python lola.py --prospective-holdout-lock candidate.json --holdout-lock-output selection-lock.json
    python lola.py --prospective-transfer-result result.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from lola_library import register_target, set_plan, complete_scan, catalog


ROOT = Path(__file__).resolve().parent


def run(cmd: list[str]) -> int:
    print("\nLOLA MASTER")
    print("Command:", " ".join(f'"{x}"' if " " in x else x for x in cmd))
    print()
    return subprocess.call(cmd)


def normalize_mode(mode: str | None, is_apk: bool) -> str:
    if not mode:
        return "/apk360" if is_apk else "/360"
    if not mode.startswith("/"):
        mode = "/" + mode
    if is_apk and not mode.startswith("/apk"):
        return "/apk360"
    return mode


def run_apk(args: argparse.Namespace, target: Path) -> int:
    analyzer = ROOT / "analyze-apk.py"
    report_builder = ROOT / "build-apk-report.py"

    if not analyzer.exists():
        raise SystemExit(f"Missing APK analyzer: {analyzer}")
    if not report_builder.exists():
        raise SystemExit(f"Missing APK report builder: {report_builder}")

    mode = normalize_mode(args.mode, True)
    allowed_checks={x["id"] for x in catalog()["apkPlan"]}
    checks=[x.strip() for x in (args.checks or "").split(",") if x.strip() in allowed_checks]
    if not checks:
        checks=[x["id"] for x in catalog()["apkPlan"] if x.get("default")]
    if args.decompile and "decompile" not in checks:
        checks.append("decompile")
    target_record=register_target(target,target.name)
    if "store_target" in checks:
        set_plan(target_record["id"],checks,mode,{
            "decompile":args.decompile,"keepDecompiled":args.keep_decompiled,"cleanup":args.cleanup
        })
    analysis = Path(args.apk_analysis).resolve()
    html_report = Path(args.apk_report).resolve()

    cmd = [
        sys.executable,
        str(analyzer),
        str(target),
        "--output",
        str(analysis),
        "--checks",
        ",".join(checks),
    ]
    if args.decompile:
        cmd.append("--decompile")
    if args.keep_decompiled:
        cmd.append("--keep-extracted")

    rc = run(cmd)
    if rc != 0:
        return rc

    rc = run(
        [
            sys.executable,
            str(report_builder),
            "--input",
            str(analysis),
            "--output",
            str(html_report),
            "--mode",
            mode,
        ]
    )
    if rc != 0:
        return rc

    print("APK ANALYSIS:", analysis)
    print("APK VISUAL  :", html_report)
    try:
        analysis_data=json.loads(analysis.read_text(encoding="utf-8-sig"))
    except Exception:
        analysis_data={}
    if "store_target" in checks:
        complete_scan(
            target_record["id"],"complete",mode,checks,analysis_data,
            {"analysis":str(analysis),"report":str(html_report)}
        )

    if not args.no_open:
        try:
            import webbrowser
            webbrowser.open(html_report.as_uri())
        except Exception as exc:
            print("Could not open report automatically:", exc)

    if args.cleanup:
        decompiled = ROOT / ".lola-apk" / "decompiled"
        if decompiled.exists():
            shutil.rmtree(decompiled, ignore_errors=True)
            print("CLEANUP     :", decompiled)

    return 0


def find_powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")


def run_project(args: argparse.Namespace, target: Path) -> int:
    ps = find_powershell()
    scanner = ROOT / "scan-security.ps1"

    if not scanner.exists():
        raise SystemExit(f"Missing project scanner: {scanner}")
    if not ps:
        raise SystemExit(
            "Project/folder scanning currently uses scan-security.ps1. "
            "Install PowerShell 7 (pwsh) or run Lola on Windows."
        )

    mode = normalize_mode(args.mode, False)

    cmd = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(scanner),
        str(target),
        "-Mode",
        mode,
    ]

    if args.resolve_urls:
        cmd.append("-ResolveUrls")
    if args.live_monitor:
        cmd.append("-LiveMonitor")
    if args.capture_all_code:
        cmd.append("-CaptureAllCode")
    if args.copy_public_certs:
        cmd.append("-CopyPublicCerts")
    if args.cleanup:
        cmd.append("-CleanupLolaTemp")
    if args.no_persist_events:
        cmd.append("-NoPersistEvents")
    if args.no_open:
        cmd.append("-NoOpen")

    return run(cmd)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Lola master target launcher for APKs and source/project targets."
    )

    p.add_argument(
        "target_positional",
        nargs="?",
        help="Target APK, source file, or project/folder.",
    )
    p.add_argument(
        "--target",
        dest="target_option",
        help="Target APK, source file, or project/folder. Overrides positional target.",
    )
    p.add_argument(
        "--mode",
        default=None,
        help="Mode such as /apk360, /apkpermissions, /360, /deep-dive, /anonymus.",
    )
    p.add_argument(
        "--cognitive-smoke",
        action="store_true",
        help="Run the deterministic offline S0 sovereign cognitive smoke test.",
    )
    p.add_argument(
        "--cognitive-loop-smoke",
        action="store_true",
        help="Run the end-to-end offline smoke of the New LOLA cognitive loop (triage, radar, novelty gate, planner, flow, governor).",
    )
    p.add_argument(
        "--cognitive-loop",
        help="Run the New LOLA cognitive loop on a real input JSON file (question + optional verified_state/inspectable/inventory/frozen_idea/external_hits/prediction/observed); prints the report JSON.",
    )
    p.add_argument(
        "--cognitive-entry",
        help="Run one raw human input through the full cognitive entry: Interaction Gateway (normalize + default-deny gate) -> KIPEnvelope -> cognitive loop -> answer + /flow + epistemic fuse. Input JSON: {transport, raw, actor: {actor_id, trust_class, granted_scopes[]}, session_id, capability?, verified_state?, inspectable?, inventory?, frozen_idea?, external_hits?, prediction?, observed?}.",
    )
    p.add_argument(
        "--tiny-beast-smoke",
        action="store_true",
        help="Run a synthetic smoke of the Tiny-to-Beast benchmark harness.",
    )
    p.add_argument(
        "--tiny-beast-benchmark",
        help="Evaluate a JSON baseline/learned benchmark pair with fixed-model rules.",
    )
    p.add_argument(
        "--controlled-transfer-benchmark",
        action="store_true",
        help="Run the controlled empirical T2/T3 transfer suite through Lola learning governance.",
    )
    p.add_argument(
        "--historical-replay-scanner-cwd",
        action="store_true",
        help="Replay the provenance-pinned historical scanner CWD path-resolution incident.",
    )
    p.add_argument(
        "--historical-transfer-benchmark",
        action="store_true",
        help="Run the multi-incident historical preflight-validity transfer benchmark.",
    )
    p.add_argument(
        "--prospective-transfer-prereg",
        action="store_true",
        help="Validate the sealed prospective transfer preregistration; this never claims success before holdout reveal.",
    )
    p.add_argument(
        "--prospective-holdout-observe",
        help="Observe one GitHub workflow_run event and emit review-only post-anchor failure evidence; never selects or locks a holdout.",
    )
    p.add_argument(
        "--holdout-observation-output",
        help="Output JSON path for --prospective-holdout-observe. Written only for OBSERVED_REVIEW_REQUIRED.",
    )
    p.add_argument(
        "--prospective-holdout-lock",
        help="Validate the first eligible natural failure and create a pre-repair selection lock using real Git ancestry.",
    )
    p.add_argument(
        "--holdout-lock-output",
        help="Output JSON path for --prospective-holdout-lock. Written only when the candidate is valid.",
    )
    p.add_argument(
        "--prospective-transfer-result",
        help="Validate a Phase-B prospective transfer result using the sealed anchor and real local Git ancestry.",
    )
    p.add_argument(
        "--require-sovereign",
        action="store_true",
        help="Require the learned benchmark trial to use no external AI.",
    )

    # Shared / source-project options
    p.add_argument("--resolve-urls", action="store_true")
    p.add_argument("--live-monitor", action="store_true")
    p.add_argument("--capture-all-code", action="store_true")
    p.add_argument("--copy-public-certs", action="store_true")
    p.add_argument("--no-persist-events", action="store_true")

    # APK options
    p.add_argument("--decompile", action="store_true")
    p.add_argument("--keep-decompiled", action="store_true")
    p.add_argument("--apk-analysis", default="apk-analysis.json")
    p.add_argument("--apk-report", default="apk-report.html")
    p.add_argument("--checks", default="", help="Comma-separated APK target-plan checks from the built-in library.")

    # Shared output behavior
    p.add_argument("--cleanup", action="store_true")
    p.add_argument("--no-open", action="store_true")
    p.add_argument(
        "--handoff-validate",
        help="Validate a local handoff contract v1.0 JSON manifest.",
    )
    p.add_argument(
        "--handoff-run",
        help="Execute a local handoff contract v1.0 JSON manifest.",
    )
    p.add_argument(
        "--handoff-result",
        help="Optional output path for handoff result JSON.",
    )

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.handoff_validate and args.handoff_run:
        parser.error("--handoff-validate and --handoff-run cannot be used together.")
    if args.holdout_observation_output and not args.prospective_holdout_observe:
        parser.error("--holdout-observation-output requires --prospective-holdout-observe.")
    if args.holdout_lock_output and not args.prospective_holdout_lock:
        parser.error("--holdout-lock-output requires --prospective-holdout-lock.")

    special_modes = sum(
        bool(value)
        for value in (
            args.cognitive_smoke,
            args.cognitive_loop_smoke,
            args.tiny_beast_smoke,
            args.tiny_beast_benchmark,
            args.controlled_transfer_benchmark,
            args.historical_replay_scanner_cwd,
            args.historical_transfer_benchmark,
            args.prospective_transfer_prereg,
            args.prospective_holdout_observe,
            args.prospective_holdout_lock,
            args.prospective_transfer_result,
            args.handoff_validate,
            args.handoff_run,
            args.cognitive_loop,
            args.cognitive_entry,
        )
    )
    if special_modes > 1:
        parser.error("Choose only one cognitive/benchmark/handoff command at a time.")

    if args.cognitive_smoke:
        if args.target_option or args.target_positional:
            parser.error("--cognitive-smoke must run without target inputs.")
        from lola_sovereign_runtime import run_sovereign_smoke

        result = run_sovereign_smoke()
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("passed") else 1

    if args.cognitive_loop_smoke and args.cognitive_loop:
        parser.error("--cognitive-loop-smoke and --cognitive-loop cannot be used together.")
    if args.cognitive_loop_smoke:
        if args.target_option or args.target_positional:
            parser.error("--cognitive-loop-smoke must run without target inputs.")
        from lola_cognitive_loop_smoke import run_cognitive_loop_smoke

        result = run_cognitive_loop_smoke()
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("passed") else 1

    if args.cognitive_loop:
        if args.target_option or args.target_positional:
            parser.error("--cognitive-loop must run without target inputs.")
        from lola_cognitive_loop import run_cognitive_loop

        input_doc = json.loads(Path(args.cognitive_loop).read_text(encoding="utf-8"))
        result = run_cognitive_loop(input_doc)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0

    if args.cognitive_entry:
        if args.target_option or args.target_positional:
            parser.error("--cognitive-entry must run without target inputs.")
        from dataclasses import asdict
        from lola_cognitive_entry import cognitive_entry
        from lola_interaction_gateway import ActorIdentity, TrustClass

        doc = json.loads(Path(args.cognitive_entry).read_text(encoding="utf-8"))
        actor_doc = doc.get("actor") or {}
        actor = ActorIdentity(
            actor_id=str(actor_doc.get("actor_id", "")),
            trust_class=TrustClass(str(actor_doc.get("trust_class", "UNTRUSTED"))),
            granted_scopes=frozenset(actor_doc.get("granted_scopes") or ()),
        )
        # the actors table is the gate's source of truth; when omitted,
        # the single supplied actor is trusted to be known.
        actors = doc.get("actors")
        if actors is None:
            actors = {actor.actor_id: actor}
        else:
            actors = {
                str(aid): ActorIdentity(
                    actor_id=str(aid),
                    trust_class=TrustClass(str(ad.get("trust_class", "UNTRUSTED"))),
                    granted_scopes=frozenset(ad.get("granted_scopes") or ()),
                )
                for aid, ad in actors.items()
            }
        result = cognitive_entry(
            str(doc.get("transport", "")),
            str(doc.get("raw", "")),
            actor,
            session_id=str(doc.get("session_id", "")),
            actors=actors,
            capability=str(doc.get("capability", "cognitive_query")),
            verified_state=doc.get("verified_state") or {},
            inspectable=tuple(doc.get("inspectable") or ()),
            inventory=doc.get("inventory"),
            frozen_idea=doc.get("frozen_idea"),
            external_hits=tuple(doc.get("external_hits") or ()),
            prediction=doc.get("prediction"),
            observed=doc.get("observed"),
        )
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False,
                         sort_keys=True))
        return 0

    if args.tiny_beast_smoke:
        if args.target_option or args.target_positional:
            parser.error("--tiny-beast-smoke must run without target inputs.")
        from lola_tiny_beast_benchmark import run_tiny_beast_smoke

        result = run_tiny_beast_smoke()
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("passed") else 1

    if args.tiny_beast_benchmark:
        if args.target_option or args.target_positional:
            parser.error("--tiny-beast-benchmark must run without target inputs.")
        from lola_tiny_beast_benchmark import evaluate_growth, load_benchmark_pair

        baseline, learned = load_benchmark_pair(Path(args.tiny_beast_benchmark))
        result = evaluate_growth(
            baseline,
            learned,
            require_sovereign=bool(args.require_sovereign),
        )
        payload = result.as_dict()
        payload["empirical_beast_claim"] = bool(result.passed)
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.passed else 2

    if args.controlled_transfer_benchmark:
        if args.target_option or args.target_positional:
            parser.error("--controlled-transfer-benchmark must run without target inputs.")
        from lola_controlled_transfer_benchmark import run_controlled_transfer_suite

        result = run_controlled_transfer_suite()
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("controlled_empirical_claim") else 2

    if args.historical_replay_scanner_cwd:
        if args.target_option or args.target_positional:
            parser.error("--historical-replay-scanner-cwd must run without target inputs.")
        from lola_historical_replay import run_scanner_cwd_historical_replay

        result = run_scanner_cwd_historical_replay()
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("historical_replay_claim") else 2

    if args.historical_transfer_benchmark:
        if args.target_option or args.target_positional:
            parser.error("--historical-transfer-benchmark must run without target inputs.")
        from lola_historical_transfer import run_historical_transfer_suite

        result = run_historical_transfer_suite()
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("historical_transfer_claim") else 2

    if args.prospective_transfer_prereg:
        if args.target_option or args.target_positional:
            parser.error("--prospective-transfer-prereg must run without target inputs.")
        from lola_prospective_prereg import load_preregistration, validate_preregistration

        result = validate_preregistration(load_preregistration())
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("valid") else 2

    if args.prospective_holdout_observe:
        if args.target_option or args.target_positional:
            parser.error("--prospective-holdout-observe must run without target inputs.")
        if not args.holdout_observation_output:
            parser.error("--prospective-holdout-observe requires --holdout-observation-output.")
        from lola_prospective_holdout_observer import observe_workflow_event

        event_path = Path(args.prospective_holdout_observe)
        event = json.loads(event_path.read_text(encoding="utf-8"))
        result = observe_workflow_event(event, repository_root=ROOT)
        if result.get("observation_created"):
            output_path = Path(args.holdout_observation_output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0

    if args.prospective_holdout_lock:
        if args.target_option or args.target_positional:
            parser.error("--prospective-holdout-lock must run without target inputs.")
        if not args.holdout_lock_output:
            parser.error("--prospective-holdout-lock requires --holdout-lock-output.")
        from lola_prospective_holdout import build_selection_lock, validate_holdout_candidate

        candidate_path = Path(args.prospective_holdout_lock)
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        if not isinstance(candidate, dict):
            result = {
                "valid_candidate": False,
                "status": "REJECTED_HOLDOUT_CANDIDATE",
                "reasons": ["candidate_must_be_json_object"],
                "prospective_claim": False,
                "blind_holdout_claim": False,
                "production_world_claim": False,
            }
            print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
            return 2

        verdict = validate_holdout_candidate(candidate, repository_root=ROOT)
        if not verdict.get("valid_candidate"):
            print(json.dumps(verdict, indent=2, ensure_ascii=False, sort_keys=True))
            return 2

        lock = build_selection_lock(candidate, repository_root=ROOT)
        output_path = Path(args.holdout_lock_output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True))
        return 0

    if args.prospective_transfer_result:
        if args.target_option or args.target_positional:
            parser.error("--prospective-transfer-result must run without target inputs.")
        from lola_prospective_result import load_prospective_result, evaluate_prospective_result

        result = evaluate_prospective_result(
            load_prospective_result(Path(args.prospective_transfer_result)),
            repository_root=ROOT,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("prospective_claim") else 2

    if args.handoff_validate or args.handoff_run:
        if args.target_option or args.target_positional:
            parser.error(
                "Handoff commands cannot be combined with --target or positional targets."
            )
        from lola_handoff_adapter import (
            execute_handoff_manifest,
            handoff_exit_code,
            validate_handoff_manifest,
        )

        if args.handoff_validate:
            payload, code = validate_handoff_manifest(Path(args.handoff_validate))
            print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
            return code

        result = execute_handoff_manifest(
            Path(args.handoff_run),
            Path(args.handoff_result).resolve() if args.handoff_result else None,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return handoff_exit_code(result)

    raw_target = args.target_option or args.target_positional
    if not raw_target:
        parser.error(
            "No target supplied. Example: python lola.py --target C:\\Apps\\sample.apk"
        )

    target = Path(raw_target).expanduser().resolve()
    if not target.exists():
        parser.error(f"Target does not exist: {target}")

    is_apk = target.is_file() and target.suffix.lower() == ".apk"

    print("TARGET      :", target)
    print("TYPE        :", "APK" if is_apk else ("DIRECTORY" if target.is_dir() else "FILE"))

    if is_apk:
        return run_apk(args, target)

    return run_project(args, target)


if __name__ == "__main__":
    raise SystemExit(main())