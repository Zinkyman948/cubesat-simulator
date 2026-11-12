"""Command-line entry point: `simcore run|budget <scenario.yaml>`, `simcore serve`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from simcore import __version__, simulation
from simcore.link.analysis import budget_table, link_atmosphere
from simcore.link.budget import LinkModel
from simcore.scenario import Scenario, load_scenario


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


def _format_bytes(bits: float) -> str:
    size = bits / 8.0
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1000.0 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1000.0


def _format_links(result: simulation.SimulationResult) -> str:
    lines = []
    for link in result.scenario.links:
        model = LinkModel(link)
        lines.append("")
        lines.append(
            f"Link: {link.name} ({link.direction}, {link.frequency_mhz:g} MHz, "
            f"{link.modulation.upper()} {link.data_rate_bps:g} bps) - "
            f"EIRP {model.eirp_dbw:.1f} dBW, G/T {model.g_over_t_dbk:.1f} dB/K, "
            f"required Eb/N0 {model.required_ebn0_db:.1f} dB"
        )
        for gs in result.scenario.link_stations(link):
            lps = [lp for lp in result.link_passes if lp.link == link.name and lp.station == gs.name]
            volume = sum(lp.data_volume_bits for lp in lps)
            lines.append(f"  {gs.name}: {len(lps)} passes, {_format_bytes(volume)} total")
            if not lps:
                continue
            lines.append(f"    {'#':>3}  {'AOS (UTC)':<19}  {'MaxEl':>6}  {'MaxDop':>9}  {'MaxRate':>9}"
                         f"  {'PeakMarg':>8}  {'Closed':>7}  {'Volume':>9}")
            for lp in lps:
                p = result.passes[gs.name][lp.pass_index]
                lines.append(
                    f"    {lp.pass_index + 1:>3}  {p.aos:%Y-%m-%d %H:%M:%S}  {p.max_elevation_deg:6.1f}"
                    f"  {lp.max_abs_doppler_hz / 1e3:7.2f}kHz  {lp.max_abs_doppler_rate_hz_s:6.1f}Hz/s"
                    f"  {lp.peak_margin_db:6.1f}dB  {lp.link_closed_s / 60:6.1f}m"
                    f"  {_format_bytes(lp.data_volume_bits):>9}"
                )
    return "\n".join(lines)


def _load(path: Path) -> Scenario | None:
    try:
        return load_scenario(path)
    except ValidationError as e:
        print(f"Invalid scenario {path}:\n{e}", file=sys.stderr)
        return None


def _cmd_run(args) -> int:
    scenario = _load(args.scenario)
    if scenario is None:
        return 2
    result = simulation.run(scenario)
    print(_format_passes(result))
    if scenario.links:
        print(_format_links(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result.to_dict(args.ephemeris), indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


def _cmd_budget(args) -> int:
    scenario = _load(args.scenario)
    if scenario is None:
        return 2
    if not scenario.links:
        print("Scenario defines no links.", file=sys.stderr)
        return 1
    # Size the budget for the highest altitude in the window (worst case).
    ephemeris = simulation.compute_ephemeris(scenario, simulation.build_propagator(scenario))
    altitude = float(ephemeris.altitude_km.max())

    for link in scenario.links:
        model = LinkModel(link)
        for gs in scenario.link_stations(link):
            elevations = [gs.min_elevation_deg, 90.0]
            atmosphere = link_atmosphere(scenario.atmosphere, link, gs)
            tables = [
                budget_table(model, altitude, gs.altitude_m / 1000.0, el, atmosphere) for el in elevations
            ]
            atm = scenario.atmosphere
            weather = (
                f"ITU-R atmosphere, {atm.availability_percent:g}% availability"
                if atm.model == "itu-r"
                else "no atmosphere model"
            )
            print(f"\n{link.name} ({link.direction}) - {gs.name}, altitude {altitude:.1f} km, {weather}")
            print(f"  {'':<38}{'At mask':>10}{'Zenith':>10}")
            for (label, low, unit), (_, high, _) in zip(*tables):
                print(f"  {label:<38}{low:10.2f}{high:10.2f}  {unit}")
    return 0


def _cmd_lifetime(args) -> int:
    from datetime import timedelta

    scenario = _load(args.scenario)
    if scenario is None:
        return 2
    sc = scenario.spacecraft
    print(f"{sc.name}: {sc.form_factor}, {sc.mass_kg:g} kg, drag area {sc.effective_drag_area_m2:.4f} m^2, "
          f"Cd {sc.drag_coefficient:g} -> ballistic coefficient {sc.ballistic_coefficient:.4f} m^2/kg")
    print(f"Solar activity: {scenario.drag.solar_activity}")
    result = simulation.run_lifetime(scenario, max_years=args.max_years)
    start = scenario.simulation.start
    print(f"\n  {'Date':<12}{'Perigee':>10}{'Apogee':>10}{'F10.7':>8}")
    shown = set()
    for day, peri, apo, f107 in zip(result.days, result.perigee_km, result.apogee_km, result.f107):
        year = int(day // 365.25)
        if year in shown and day != result.days[-1]:
            continue
        shown.add(year)
        date = start + timedelta(days=float(day))
        print(f"  {date:%Y-%m-%d}  {peri:8.1f}km{apo:8.1f}km{f107:8.0f}")
    years = result.lifetime_days / 365.25
    if result.reentered:
        reentry = start + timedelta(days=result.lifetime_days)
        print(f"\nRe-entry (perigee below {result.reentry_altitude_km:g} km) around {reentry:%Y-%m-%d}: "
              f"{years:.2f} years ({result.lifetime_days:.0f} days) after {start:%Y-%m-%d}")
    else:
        print(f"\nStill in orbit after {years:g} years.")
    return 0


def _cmd_serve(args) -> int:
    from simcore.server import serve

    serve(args.host, args.port, exit_on_stdin_close=args.exit_on_stdin_close)
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

    budget = sub.add_parser("budget", help="print link budget tables at the mask elevation and zenith")
    budget.add_argument("scenario", type=Path, help="scenario YAML file")
    budget.set_defaults(func=_cmd_budget)

    life = sub.add_parser("lifetime", help="estimate orbit lifetime under atmospheric drag")
    life.add_argument("scenario", type=Path, help="scenario YAML file")
    life.add_argument("--max-years", type=float, default=25.0, help="longest span to simulate")
    life.set_defaults(func=_cmd_lifetime)

    srv = sub.add_parser("serve", help="run the local HTTP API used by the desktop app")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8765, help="0 picks a free port")
    srv.add_argument("--exit-on-stdin-close", action="store_true",
                     help="exit when stdin closes (used when launched by the desktop app)")
    srv.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
