#!/usr/bin/env python3
"""Phase 2 gate: ERC plus net-by-net comparison against channel_netlist.py.

    python3 tools/gen_schematic.py
    python3 tools/check_schematic.py

Compares one channel (CH1_TWEETER / R1xx) of the exported KiCad netlist to
channel_netlist.py --netlist, after mapping pin names to KiCad pin numbers.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from channel_netlist import (  # noqa: E402
    ALLOWED_SINGLE_PIN,
    COMPONENTS,
    HIER_PINS,
    NETLIST,
    Comp,
    check as check_netlist,
)
from gen_schematic import (  # noqa: E402
    AMP,
    CH_RENAME,
    PROJECT_AMP,
    PSU,
    ROOT,
    U2_PIN,
    annotate_ref,
    kicad_pin,
    setup_cache,
    sch_ref,
)

# Supporting sheets (regulators / protection / interface) and the PSU project
# place BoM parts without a pin-accurate netlist. Their ERC is waived until
# those sheets get the same treatment as amp_channel. See DEVIATIONS.md item 9.
PLACEHOLDER_SHEETS = ("/REGULATORS/", "/PROTECTION/", "/INTERFACE/")
PLACEHOLDER_TYPES = {
    "pin_not_connected",
    "label_dangling",
    "pin_not_driven",
    "power_pin_not_driven",
    "pin_to_pin",
}
# MUTE_CTL is driven from the protection sheet, which is not pin-accurate yet.
MUTE_FET = {
    "/CH1_TWEETER/": "Q116",
    "/CH2_MID/": "Q216",
    "/CH3_MIDBASS/": "Q316",
}

# Flattened hierarchical nets use the root name (IN_HOT_T). Map back to the
# channel_netlist name (IN_HOT) so one-channel compare still works.
_CANONICAL_NET = {
    tmpl.format(s=s): pin
    for pin, tmpl in CH_RENAME.items()
    for s in "TMB"
}


def _canonical_hier_name(name: str) -> str:
    return _CANONICAL_NET.get(name, name)


def golden_channel(channel: int = 1) -> dict[str, set[tuple[str, str]]]:
    """net -> {(annotated_ref, kicad_pin_number)} for one channel."""
    by_c = {c.ref: c for c in COMPONENTS}
    nets: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for ref, pin, net in NETLIST:
        c = by_c[ref]
        kn = kicad_pin(c, pin)
        aref = annotate_ref(sch_ref(c), channel)
        nets[net].add((aref, kn))
    return dict(nets)


def parse_kicad_netlist(path: Path) -> dict[str, set[tuple[str, str]]]:
    """Parse kicad-cli sexpr netlist into net -> {(ref, pin)}."""
    text = path.read_text(encoding="utf-8")
    nets: dict[str, set[tuple[str, str]]] = defaultdict(set)
    # (net (code "N") (name "NAME") ... (node (ref "R101") (pin "1") ...)
    net_blocks = re.finditer(
        r'\(net\s+\(code\s+"[^"]+"\)\s+\(name\s+"([^"]+)"\)(.*?)(?=\n\s+\(net\s+\(code|\n\s+\)\s*\n\))',
        text,
        re.S,
    )
    found = 0
    for m in net_blocks:
        raw_name = m.group(1)
        body = m.group(2)
        nodes = re.findall(r'\(node\s+\(ref\s+"([^"]+)"\)\s+\(pin\s+"([^"]+)"\)', body)
        if not nodes:
            continue
        found += 1
        # Strip sheet path: /CH1_TWEETER/FB or /CH1_TWEETER/FB (netclass)
        name = raw_name.split("/")[-1]
        name = _canonical_hier_name(name)
        if name.startswith("unconnected-"):
            continue
        for ref, pin in nodes:
            nets[name].add((ref, pin))
    if found == 0:
        # Fallback: looser scan
        for m in re.finditer(r'\(name\s+"([^"]+)"\)', text):
            pass
        raise RuntimeError(f"no nets parsed from {path}")
    return dict(nets)


def filter_channel(nets: dict[str, set[tuple[str, str]]], channel: int = 1
                   ) -> dict[str, set[tuple[str, str]]]:
    """Keep nodes whose refs match this channel's annotation (R1xx, Q1xx, …)."""
    pat = re.compile(rf"^[A-Z]+{channel}\d{{2}}[A-Z]*$")
    out: dict[str, set[tuple[str, str]]] = {}
    for net, nodes in nets.items():
        kept = {n for n in nodes if pat.match(n[0]) or n[0] == f"U{channel}02"}
        # U2 annotates to U102; also #power symbols if any
        if kept:
            out[net] = kept
    return out


def compare(golden: dict[str, set[tuple[str, str]]],
            got: dict[str, set[tuple[str, str]]]) -> list[str]:
    errs = []
    skip = set(ALLOWED_SINGLE_PIN)
    for net in sorted(set(golden) | set(got)):
        if net in skip:
            continue
        g = golden.get(net, set())
        h = got.get(net, set())
        # Hierarchical pin nets may pick up parent-sheet nodes (connectors). Drop
        # anything that is not a channel-annotated ref from `h` already.
        extra = h - g
        missing = g - h
        if missing:
            errs.append(f"{net}: missing {sorted(missing)}")
        if extra:
            errs.append(f"{net}: extra {sorted(extra)}")
    return errs


def run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def export_netlist(sch: Path, out: Path) -> None:
    r = run_cli(
        ["kicad-cli", "sch", "export", "netlist", "--output", str(out), str(sch)],
        sch.parent,
    )
    if r.returncode != 0:
        sys.stderr.write(r.stderr or r.stdout)
        raise SystemExit(f"kicad-cli netlist failed ({r.returncode})")


def run_erc(sch: Path, report: Path) -> list[tuple[str, str, str]]:
    """Return (sheet_path, erc_type, description) for error-severity items."""
    r = run_cli(
        ["kicad-cli", "sch", "erc", "--format", "json", "--severity-error",
         "--output", str(report), str(sch)],
        sch.parent,
    )
    if not report.exists():
        sys.stderr.write(r.stderr or r.stdout)
        return [("", "erc_failed", f"ERC did not write {report} (exit {r.returncode})")]
    data = json.loads(report.read_text(encoding="utf-8"))
    errs: list[tuple[str, str, str]] = []
    sheets = data.get("sheets") or []
    for sheet in sheets:
        path = sheet.get("path") or sheet.get("uuid") or ""
        for v in sheet.get("violations", []):
            if str(v.get("severity", "")).lower() not in {"error", "2"}:
                continue
            typ = v.get("type") or ""
            items = v.get("items") or []
            extra = "; ".join(i.get("description", "") for i in items if i.get("description"))
            desc = extra or v.get("description") or v.get("title") or str(v)
            errs.append((path, typ, desc))
    if not errs and r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip()
        errs.append(("", "erc_failed", (msg.split("\n")[-1][:300] if msg else f"ERC exit {r.returncode}")))
    return errs


def waived(path: str, typ: str, desc: str, psu: bool = False) -> str | None:
    """Return waiver reason, or None if the error must fail the gate."""
    if psu and typ in PLACEHOLDER_TYPES:
        return "PSU sheet has no pin-accurate netlist yet"
    if path in PLACEHOLDER_SHEETS and typ in PLACEHOLDER_TYPES:
        return f"{path} is a BoM placeholder sheet"
    # KiCad reports dangling labels from child placeholder sheets on the root.
    if path == "/" and typ == "label_dangling":
        return "placeholder-sheet labels attributed to root"
    fet = MUTE_FET.get(path)
    if fet and typ == "pin_not_driven" and fet in desc:
        return f"{fet} gate is MUTE_CTL, driven from protection (placeholder)"
    return None


def main() -> int:
    setup_cache()
    print("channel_netlist.py --check")
    if check_netlist() != 0:
        return 1

    sch = AMP / f"{PROJECT_AMP}.kicad_sch"
    if not sch.exists():
        print("run tools/gen_schematic.py first", file=sys.stderr)
        return 2

    net_path = AMP / f"{PROJECT_AMP}.net"
    print(f"export netlist → {net_path}")
    try:
        export_netlist(sch, net_path)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 3

    print("compare CH1 against channel_netlist")
    gold = golden_channel(1)
    parsed = parse_kicad_netlist(net_path)
    ch1 = filter_channel(parsed, 1)
    # KiCad names hierarchical nets without a sheet prefix when unique, or with
    # /CH1_TWEETER/NAME. parse_kicad_netlist already takes the last path component,
    # so CH1 and CH2 both contribute to the same net key. filter_channel keeps
    # only R1xx nodes, which is what we want.
    errs = compare(gold, ch1)
    for e in errs:
        print(f"  FAIL  {e}")
    if errs:
        print(f"{len(errs)} netlist mismatches")
        return 4
    print(f"  {len(gold)} nets match for channel 1")

    erc_path = AMP / "erc-amp.json"
    print(f"ERC {sch}")
    erc_all = [(p, t, d, False) for p, t, d in run_erc(sch, erc_path)]
    psu_sch = PSU / "fs3w-psu.kicad_sch"
    if psu_sch.exists():
        print(f"ERC {psu_sch}")
        erc_all += [(p, t, d, True) for p, t, d in run_erc(psu_sch, PSU / "erc-psu.json")]

    hard: list[str] = []
    n_waive = 0
    for path, typ, desc, is_psu in erc_all:
        reason = waived(path, typ, desc, psu=is_psu)
        loc = "psu:" + path if is_psu else path
        if reason:
            n_waive += 1
            continue
        hard.append(f"{loc} {typ}: {desc}")
    print(f"  {n_waive} ERC errors waived (DEVIATIONS.md item 9)")
    for e in hard:
        print(f"  ERC   {e}")
    if hard:
        print(f"{len(hard)} ERC errors")
        return 5
    print("ERC clean (errors)")

    pdf = ROOT / "docs" / "schematic-amp.pdf"
    print(f"export PDF → {pdf}")
    r = run_cli(
        ["kicad-cli", "sch", "export", "pdf", "--output", str(pdf), str(sch)],
        sch.parent,
    )
    if r.returncode != 0:
        sys.stderr.write(r.stderr or r.stdout)
        print("PDF export failed", file=sys.stderr)
        return 6
    print("Phase 2 gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
