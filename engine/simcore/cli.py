"""Command-line entry point: `simcore run <scenario.yaml>`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from simcore import __version__, simulation
from simcore.scenario import load_scenario


def _format_passes(result: simulation.SimulationResult) -> str:
    lines = []
    sc = result.scenario
    lines.append(f"Scenario: {sc.name}")
    lines.append(f"Spacecraft: {sc.spacecraft.name} ({sc.spacecraft.form_factor})  "
                 f"Propagator: {sc.propagator}")
    lines.append(f"Window: {sc.simulation.start:%Y-%m-%d %H:%M:%S} UTC "
                 f"+ {sc.simulation.duration_hours:g} h")
    for gs in sc.ground_stations:
        passes = result.passes[gs.name]
        total = sum(p.duration_s for p in passes)
        lines.append("")
        lines.append(f"{gs.name}  ({gs.latitude_deg:.3f}, {gs.longitude_deg:.3f}), "
                     f"mask {gs.min_elevation_deg:g} deg - {len(passes)} passes, "
                     f"{total / 60:.1f} min total contact")
        if not passes:
            continue
        lines.append(f"  {'#':>3}  {'AOS (UTC)':<19}  {'TCA (UTC)':<19}  {'LOS (UTC)':<19}"
                     f"  {'Dur':>6}  {'MaxEl':>6}  {'AzAOS':>6}  {'AzLOS':>6}")
        for n, p in enumerate(passes, 1):
            flag = (" <" if p.truncated_start else "") + (" >" if p.truncated_end else "")
            lines.append(
                f"  {n:>3}  {p.aos:%Y-%m-%d %H:%M:%S}  {p.tca:%Y-%m-%d %H:%M:%S}  "
                f"{p.los:%Y-%m-%d %H:%M:%S}  {p.duration_s / 60:5.1f}m  "
                f"{p.max_elevation_deg:6.1f}  {p.aos_azimuth_deg:6.1f}  {p.los_azimuth_deg:6.1f}{flag}"
            )
    if any(p.truncated_start or p.truncated_end for ps in result.passes.values() for p in ps):
        lines.append("")
        lines.append("  < pass already in progress at start, > still in progress at end")
    return "\n".join(lines)


def _cmd_run(args) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except ValidationError as e:
        print(f"Invalid scenario {args.scenario}:\n{e}", file=sys.stderr)
        return 2
    result = simulation.run(scenario)
    print(_format_passes(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result.to_dict(args.ephemeris), indent=2))
        print(f"\nWrote {args.json}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simcore", description="CubeSat simulation engine")
    parser.add_argument("--version", action="version", version=f"simcore {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a scenario and print predicted passes")
    run.add_argument("scenario", type=Path, help="scenario YAML file")
    run.add_argument("--json", type=Path, help="also write results to this JSON file")
    run.add_argument("--ephemeris", action="store_true",
                     help="include the sampled ephemeris in the JSON output")
    run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
