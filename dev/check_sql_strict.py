"""Strict SQL check for nl-conservancy-management-report.

Runs EVERY apply_sql_query task in spec.yaml the way Ecoscope Desktop does:
the task's own validator and deny-by-default SQLite authorizer (copied
verbatim from ecoscope/platform/tasks/transformation/_sql_query.py), through
the same chain the DAG runs -- events -> period bounds -> patrols clamped and
capped -> tracks filtered -> split by month -- and then asserts the behaviour
each review point asked for.

Data: the HWC report's real 2026 events (if ../nl-hwc-report/.scratch/
live-events.json exists) plus synthetic rows for every special case: bilingual
species, sighting types, Silent Source, Patrol Info on a patrol, test forms, a
legacy event and its migrated copy, empty thefts at 0,0 minutes apart, both
Illegal Activity forms, a patrol left open from December, both spellings of
two rangers.

    python3 dev/check_sql_strict.py
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC = yaml.safe_load(open(ROOT / "spec.yaml"))
TZ = "Africa/Nairobi"

MAX_QUERY_LENGTH = 10_000
ALLOWED_FUNCTIONS = frozenset(
    {
        "count",
        "sum",
        "total",
        "avg",
        "min",
        "max",
        "group_concat",
        "string_agg",
        "abs",
        "round",
        "coalesce",
        "ifnull",
        "nullif",
        "iif",
        "typeof",
        "lower",
        "upper",
        "length",
        "substr",
        "substring",
        "trim",
        "ltrim",
        "rtrim",
        "replace",
        "instr",
        "like",
        "glob",
        "printf",
        "format",
        "concat",
        "concat_ws",
        "ceil",
        "ceiling",
        "floor",
        "sqrt",
        "pow",
        "power",
        "exp",
        "ln",
        "log",
        "log10",
        "mod",
        "sign",
        "date",
        "time",
        "datetime",
        "julianday",
        "strftime",
        "unixepoch",
        "json",
        "json_extract",
        "json_array_length",
        "json_type",
        "json_valid",
        "json_array",
        "json_object",
        "json_group_array",
        "json_group_object",
        "row_number",
        "rank",
        "dense_rank",
        "percent_rank",
        "cume_dist",
        "ntile",
        "lag",
        "lead",
        "first_value",
        "last_value",
        "nth_value",
    }
)
_READABLE_TABLES = frozenset({"df", "json_each", "json_tree"})
_RECURSIVE = getattr(sqlite3, "SQLITE_RECURSIVE", 33)


def _authorizer(action, arg1, arg2, db_name, trigger):
    if action in (sqlite3.SQLITE_SELECT, _RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        return sqlite3.SQLITE_OK if arg1 in _READABLE_TABLES else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION:
        return (
            sqlite3.SQLITE_OK
            if arg2 and arg2.lower() in ALLOWED_FUNCTIONS
            else sqlite3.SQLITE_DENY
        )
    return sqlite3.SQLITE_DENY


def validate_sql_query(value: str) -> str:
    if not value or not value.strip():
        return value.strip()
    if len(value) > MAX_QUERY_LENGTH:
        raise ValueError(
            f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters"
        )
    q = value.strip()
    p = q.find(";")
    if p != -1 and p < len(q) - 1:
        raise ValueError("Multiple SQL statements are not allowed (no semicolons)")
    if not q.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")
    return q


def _jsonify(v):
    if isinstance(v, (np.ndarray, set, list, dict)):
        return json.dumps(
            list(v) if isinstance(v, set) else v, ensure_ascii=False, default=str
        )
    return v


def apply_sql_query(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """sanitize (complex -> JSON text) + validate + authorized sqlite run."""
    q = validate_sql_query(query)
    d = df.reset_index(drop=True).copy()
    for c in d.columns:
        s = d[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            d[c] = s.astype(str).where(
                s.notna(), None
            )  # how SQLAlchemy writes tz-aware ts
        elif s.dtype == object:
            d[c] = s.map(_jsonify)
    con = sqlite3.connect(":memory:")
    try:
        d.to_sql("df", con, index=False)
        con.set_authorizer(_authorizer)
        return pd.read_sql_query(q, con)
    except Exception as e:  # mirror the task's wrapping
        raise ValueError(f"SQL query failed: {e}") from None
    finally:
        con.close()


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------

TASKS = {}


def _walk(x):
    if isinstance(x, dict):
        if "task" in x and "id" in x:
            TASKS[x["id"]] = x
        for v in x.values():
            _walk(v)
    elif isinstance(x, list):
        for v in x:
            _walk(v)


_walk(SPEC)


def query(tid):
    return TASKS[tid]["partial"]["query"]


def ev(
    t,
    time,
    details,
    disp=None,
    cat="field_monitoring",
    geom="POINT (37.1 0.5)",
    patrols=None,
    eid=None,
    title=None,
):
    ev.n += 1
    return dict(
        id=eid or f"ev-{ev.n}",
        serial_number=str(ev.n),
        event_type=t,
        event_type_display=disp or t,
        event_category=cat,
        event_details=details,
        patrols=patrols or [],
        geometry=geom,
        time=time,
        title=title,
    )


ev.n = 0


def synthetic():
    T = "2026-10-1{}T08:00:00+03:00"
    return [
        ev(
            "wildlife_sighting",
            T.format(1),
            {
                "Sighting type": "Visual",
                "Species": "Elephant / Ndovu (Tembo)",
                "Total Individuals": 12,
            },
            "Wildlife Sighting (Field Monitoring)",
        ),
        ev(
            "wildlife_sighting",
            T.format(1),
            {"Sighting type": "Spoor", "Species": "Hyena - Spotted / Fisi (madoa)"},
            "Wildlife Sighting (Field Monitoring)",
        ),
        ev(
            "wildlife_sighting",
            T.format(2),
            {"Sighting type": "Dung/Pellets", "Species": "Elephant / Ndovu (Tembo)"},
            "Wildlife Sighting (Field Monitoring)",
        ),
        ev("silence_source_rep", T.format(2), {}, "Silent Source", "analyzer_event"),
        ev(
            "test_patrol_info",
            T.format(3),
            {
                "Mandate": ["Routine", "Security"],
                "Transport Type": "Foot",
                "Team Leader": "Micka Yiangere",
                "Team members": ["Mika Yiangere", "Edung Mosieny"],
                "Station": "HQ",
            },
            "Patrol Info",
            patrols=["patrol-1"],
        ),
        ev("test_wildlife_sighting", T.format(3), {}, "TEST Wildlife Sighting", "test"),
        ev(
            "elephant_sighting_rep",
            T.format(4),
            {"Species": "Elephant"},
            "Elephant Sighting",
            "ranger_basic",
            eid="legacy-1",
        ),
        ev(
            "wildlife_sighting",
            T.format(4),
            {
                "Sighting type": "Visual",
                "Species": "Elephant / Ndovu (Tembo)",
                "Total Individuals": 3,
                "additional": {"migrated_from_event_id": "legacy-1"},
            },
            "Wildlife Sighting (Field Monitoring)",
        ),
        ev("theft", "2026-10-15T08:00:00+03:00", {}, "Theft", geom="POINT (0 0)"),
        ev(
            "illegal_activity_rep",
            T.format(5),
            {"Activity": "Charcoal Production", "Number of Suspect(s)": 2},
            "Illegal Activity (Field Monitoring)",
        ),
        ev(
            "illegal_activity_rep_ranger",
            T.format(6),
            {"Activity": "Logging"},
            "Illegal Activity (Ranger Basic)",
            "ranger_basic",
        ),
        # second empty theft 4 minutes after the first, same place: a possible duplicate
        ev("theft", "2026-10-15T08:04:00+03:00", {}, "Theft", geom="POINT (0 0)"),
        # a legacy sighting never migrated: empty form
        ev(
            "wildlife_sighting_rep_ranger",
            T.format(7),
            {},
            "Wildlife Sighting (Ranger Basic)",
            "ranger_basic",
        ),
        # a sighting with no type and no count: not a 'visual with 0' case
        ev(
            "wildlife_sighting",
            T.format(7),
            {"Species": "Lion / Simba"},
            "Wildlife Sighting (Field Monitoring)",
        ),
        # a human injury whose incident date is before the period: must use ER time
        ev(
            "human_injury",
            "2026-01-03T09:00:00+03:00",
            {
                "Cause of injury": "Accident",
                "Incident date & time": "2025-12-20T09:00:00+03:00",
            },
            "Human Injury",
        ),
        # the period bounds: first and last ER time
        ev(
            "silence_source_rep",
            "2026-01-01T00:30:00+03:00",
            {},
            "Silent Source",
            "analyzer_event",
        ),
        ev(
            "silence_source_rep",
            "2026-11-11T20:00:00+03:00",
            {},
            "Silent Source",
            "analyzer_event",
        ),
        # marked for deletion by its title: must vanish from every count
        ev(
            "hwc_threat",
            T.format(8),
            {},
            "HWC Threat (HWC)",
            "lewa_hwc",
            eid="to-delete",
            title="HWC Threat - DELETE",
        ),
        # a legacy original marked for deletion, and its untitled migrated copy
        ev(
            "livestock_theft_ranger",
            T.format(8),
            {},
            "Livestock Theft",
            "ranger_basic",
            eid="lt-delete",
            title="Livestock Theft delete",
        ),
        ev(
            "theft",
            T.format(8),
            {"additional": {"migrated_from_event_id": "lt-delete"}},
            "Theft",
            eid="copy-of-deleted",
        ),
    ]


def patrols():
    seg = lambda pt, a, b, sd=None: json.dumps(
        [
            {
                "patrol_type": pt,
                "time_range": {"start_time": a, "end_time": b},
                "segment_details": sd or {},
            }
        ]
    )
    rows = [
        dict(
            id="patrol-0",
            serial_number=100,
            title="left open",
            patrol_segments=seg(
                "routine_patrol",
                "2025-12-30T07:00:00+00:00",
                "2026-01-02T07:00:00+00:00",
            ),
        ),
        dict(
            id="patrol-1",
            serial_number=101,
            title="normal",
            patrol_segments=seg(
                "bicycle_patrol",
                "2026-10-13T03:00:00+00:00",
                "2026-10-13T09:00:00+00:00",
            ),
        ),
        dict(
            id="patrol-1",
            serial_number=101,
            title="normal",
            patrol_segments=seg(
                "bicycle_patrol",
                "2026-10-13T03:00:00+00:00",
                "2026-10-13T09:00:00+00:00",
            ),
        ),
        # the new on-patrol details (since 18 Nov 2026): raw choice keys, single mandate
        dict(
            id="patrol-7",
            serial_number=107,
            title="Routine Patrol",
            patrol_segments=seg(
                "routine_patrol",
                "2026-11-05T03:00:00+00:00",
                "2026-11-05T08:00:00+00:00",
                {
                    "armed": True,
                    "mandate": "monitoring",
                    "station": "hq",
                    "team_leader": "micka",
                    "team_members": ["daniel_naiptari", "edung_mosieny"],
                    "transport_type": "foot",
                    "number_of_people_armed": 3,
                },
            ),
        ),
        dict(
            id="patrol-8",
            serial_number=108,
            title="please delete",
            patrol_segments=seg(
                "routine_patrol",
                "2026-10-14T03:00:00+00:00",
                "2026-10-14T05:00:00+00:00",
            ),
        ),
        dict(
            id="patrol-9",
            serial_number=109,
            title="test",
            patrol_segments=seg(
                "test_patrol", "2026-10-14T03:00:00+00:00", "2026-10-14T04:00:00+00:00"
            ),
        ),
    ]
    tracks = [
        dict(
            patrol_id="patrol-0",
            patrol_type__display="Routine Patrol",
            patrol_serial_number=100,
            speed_kmhr=3.0,
            dist_meters=5000.0,
            timespan_seconds=3600.0,
            segment_start=pd.Timestamp("2025-12-30T08:00:00Z"),
            segment_end=pd.Timestamp("2025-12-30T09:00:00Z"),
            geometry="LINESTRING (37 0.5, 37.01 0.5)",
        ),
        dict(
            patrol_id="patrol-0",
            patrol_type__display="Routine Patrol",
            patrol_serial_number=100,
            speed_kmhr=3.0,
            dist_meters=3000.0,
            timespan_seconds=3600.0,
            segment_start=pd.Timestamp("2026-01-01T05:00:00Z"),
            segment_end=pd.Timestamp("2026-01-01T06:00:00Z"),
            geometry="LINESTRING (37 0.5, 37.01 0.5)",
        ),
        dict(
            patrol_id="patrol-1",
            patrol_type__display="Motorbike Patrol",
            patrol_serial_number=101,
            speed_kmhr=20.0,
            dist_meters=40000.0,
            timespan_seconds=7200.0,
            segment_start=pd.Timestamp("2026-10-13T04:00:00Z"),
            segment_end=pd.Timestamp("2026-10-13T06:00:00Z"),
            geometry="LINESTRING (37 0.5, 37.2 0.5)",
        ),
    ]
    return pd.DataFrame(rows), pd.DataFrame(tracks)


def load():
    rows = synthetic()
    live = ROOT.parent / "nl-hwc-report" / ".scratch" / "live-events.json"
    if live.exists():
        rows += json.load(open(live))
    df = pd.DataFrame(rows)
    df["patrols"] = df["patrols"].map(lambda v: v if isinstance(v, list) else [])
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    return df, live.exists()


def to_local(df, cols):
    for c in cols:
        df[c] = pd.to_datetime(df[c], utc=True, format="mixed").dt.tz_convert(TZ)
    return df


def split(df, col):
    m = df[col].dt.strftime("%Y-%m")
    return {k: g for k, g in df.assign(_m=m).groupby("_m")}


def main():
    fails = 0

    def report(name, ok, msg=""):
        nonlocal fails
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name:22s} {msg}")

    def run(tid, df):
        try:
            return apply_sql_query(df, query(tid))
        except Exception as e:
            report(tid, False, str(e)[:200])
            return None

    evs, has_live = load()
    print(
        f"input: {len(evs)} events ({'real HWC events + ' if has_live else ''}synthetic cases)\n"
    )

    # ---- events chain
    prep = run("events_prepared", evs)
    prep = to_local(prep, ["report_time", "er_time"])
    report(
        "events_prepared",
        True,
        f"{len(prep)} rows, counted {int(prep.counted.sum())}, conflict {int(prep.is_conflict.sum())}",
    )
    bounds = run("period_bounds", prep)
    report(
        "period_bounds",
        bounds is not None and len(bounds) == 1,
        bounds.to_dict("records").__repr__() if bounds is not None else "",
    )
    ev_months = {k: g.drop(columns="_m") for k, g in split(prep, "report_time").items()}

    # ---- patrol chain
    pr, tr = patrols()
    tr = to_local(tr, ["segment_start", "segment_end"])
    traj_period = pd.merge(tr, bounds, how="cross")
    traj_in = run("traj_in", traj_period)
    master = run("patrols_master", pr)
    tracks = run("patrol_tracks", traj_in)
    pinfo = run("patrol_info", prep)
    j = master.merge(tracks, how="left", on="patrol_id").merge(
        pinfo, how="left", on="patrol_id"
    )
    jp = pd.merge(j, bounds, how="cross")
    ptab = run("patrol_table", jp)
    ptab = to_local(ptab, ["start_time"])
    p_months = {k: g.drop(columns="_m") for k, g in split(ptab, "start_time").items()}

    # ---- boundary
    bd = run("boundary", evs.head(1))
    msg = ""
    ok = bd is not None and len(bd) == 1
    if ok:
        try:  # the embedded outline must parse and be a valid polygon
            from shapely import wkt

            g = wkt.loads(bd.iloc[0]["geometry"])
            ok = g.is_valid and g.geom_type == "Polygon"
            msg = f"valid {g.geom_type}, {len(g.exterior.coords)} vertices, bounds {tuple(round(v, 3) for v in g.bounds)}"
        except ImportError:
            msg = "one row (install shapely to validate the polygon)"
    report("boundary", ok, msg)

    # ---- every other query, on the frames it reads in the DAG
    dchk = run("deleted_checks", evs)
    report(
        "deleted_checks",
        dchk is not None and int(dchk["Count"].iloc[0]) == 3,
        f"{dchk.to_dict('records') if dchk is not None else ''}",
    )
    done = {
        "deleted_checks",
        "events_prepared",
        "period_bounds",
        "traj_in",
        "patrols_master",
        "patrol_tracks",
        "patrol_info",
        "patrol_table",
        "boundary",
        "completeness",
    }
    outs = {}
    for tid, t in TASKS.items():
        if t["task"] != "apply_sql_query" or tid in done:
            continue
        src = json.dumps(t)
        if "events_grouped.return" in src:
            frames, whole = ev_months, prep
        elif "events_indexed.return" in src:
            frames, whole = {"(all)": prep}, prep
        elif "patrols_grouped.return" in src:
            frames, whole = p_months, ptab
        elif "patrols_indexed.return" in src:
            frames, whole = {"(all)": ptab}, ptab
        else:
            report(tid, False, "input frame not simulated by this checker")
            continue
        ok = True
        for m, g in frames.items():
            if run(tid, g) is None:
                ok = False
                break
        if ok:
            outs[tid] = run(tid, whole)
            report(tid, True, f"{len(frames)} frame(s)")
    comb = pd.concat(
        [outs["patrol_checks"], outs["event_checks"], dchk], ignore_index=True
    )
    comp = run("completeness", comb)
    report(
        "completeness",
        comp is not None,
        f"{len(comp)} checks" if comp is not None else "",
    )

    # ---- behaviour
    def expect(name, cond, detail):
        report(name, bool(cond), detail)

    print("\nbehaviour on the cases the review raised:")
    c = prep.set_index("id")
    expect(
        "deleted event left out",
        "to-delete" not in set(prep["id"]),
        "title 'HWC Threat - DELETE' dropped before counting",
    )
    expect(
        "copy of deleted left out",
        "copy-of-deleted" not in set(prep["id"]),
        "untitled migrated copy of a marked original dropped",
    )
    p7 = ptab[ptab.patrol_id == "patrol-7"].iloc[0]
    expect(
        "on-patrol details",
        (
            p7["transport"],
            p7["mandate"],
            p7["station"],
            p7["team_leader"],
            p7["has_patrol_info"],
        )
        == ("Foot", "Wildlife Monitoring", "HQ", "Mika Yiangere", 1),
        f"{p7[['transport', 'mandate', 'station', 'team_leader']].to_dict()}",
    )
    expect(
        "no-details label",
        (
            ptab.loc[ptab.patrol_id == "patrol-0", "transport"] == "No patrol details"
        ).all(),
        "patrol without details",
    )
    expect(
        "deleted patrol left out",
        "patrol-8" not in set(ptab["patrol_id"]),
        "patrol titled 'please delete' dropped",
    )
    expect("silent source", c.loc["ev-4", "counted"] == 0, "Silent Source not counted")
    expect(
        "legacy duplicate",
        c.loc["legacy-1", "counted"] == 0 and c.loc["ev-8", "counted"] == 1,
        "original dropped, migrated copy kept",
    )
    disp = set(prep.loc[prep.counted == 1, "event_type_display"])
    expect(
        "no category suffix",
        not any("(Ranger Basic)" in d or "(Field Monitoring)" in d for d in disp),
        sorted(disp)[:6].__repr__(),
    )
    inj = prep[prep["id"] == "ev-15"].iloc[0]
    expect(
        "incident date clamp",
        inj["report_time"].strftime("%Y-%m") == "2026-01",
        f"incident dated 2025-12-20, reported 2026-01-03 -> {inj['report_time']:%Y-%m-%d}",
    )
    p0 = ptab[ptab.patrol_id == "patrol-0"].iloc[0]
    expect(
        "open patrol clamped",
        p0["start_time"].strftime("%Y-%m") == "2026-01",
        f"started 30 Dec 2025 -> {p0['start_time']:%Y-%m-%d %H:%M}",
    )
    expect(
        "open patrol capped",
        p0["duration_h"] == 14 and p0["open_over_14h"] == 1,
        f"duration {p0['duration_h']} h, uncapped {p0['duration_uncapped_h']}",
    )
    expect(
        "track clamped",
        abs(p0["distance_km"] - 3.0) < 1e-6,
        f"distance {p0['distance_km']} km (December segment dropped)",
    )
    expect(
        "duplicate patrol row",
        (ptab.patrol_id == "patrol-1").sum() == 1,
        "one row per patrol",
    )
    expect("test patrol dropped", (ptab.patrol_id == "patrol-9").sum() == 0, "")
    pm = outs["patrol_months"]
    td = outs["patrol_trend_df"]
    expect(
        "trend month order",
        list(dict.fromkeys(td["Month"])) == sorted(dict.fromkeys(td["Month"])),
        f"{list(dict.fromkeys(td['Month']))[:3]} ... sorts as drawn",
    )
    expect(
        "patrol months",
        list(pm["Month"])[:1] == ["Jan 2026"]
        and pm["Month"].iloc[-1] == "Nov 2026*"
        and len(pm) == 11,
        f"{len(pm)} rows: {pm['Month'].iloc[0]} .. {pm['Month'].iloc[-1]}",
    )
    em = outs["event_months"]
    expect(
        "event months",
        len(em) == 11
        and em["Month"].iloc[-1].endswith("*")
        and "Dec 2025" not in set(em["Month"]),
        f"{len(em)} rows, last {em['Month'].iloc[-1]}",
    )
    rs = outs["ranger_summary"]
    expect(
        "ranger names",
        set(rs["Ranger"]) == {"Mika Yiangere", "Edung Mosienye", "Daniel Naiptari"}
        and int(rs.loc[rs.Ranger == "Mika Yiangere", "Patrols"].iloc[0]) == 2,
        rs.to_dict("records").__repr__()[:150],
    )
    ws = outs["wildlife_summary"]
    el = ws[ws["Species"] == "Elephant"]
    expect(
        "wildlife columns",
        int(el["Visual sightings"].iloc[0]) == 2
        and int(el["Signs (spoor or dung)"].iloc[0]) == 1,
        el.to_dict("records").__repr__()[:160],
    )
    sec = outs["security_counts"]
    expect(
        "illegal activity merged",
        int(sec.loc[sec["Event type"] == "Illegal Activity", "Incidents"].sum()) == 2
        and (sec["Event type"] == "Illegal Activity").sum() == 1,
        sec[["Event type", "Incidents"]].to_dict("records").__repr__()[:150],
    )
    cp = comp.set_index("Check")["Count"]
    expect(
        "visual 0 only",
        cp["Visual sightings with 0 individuals"] == "0",
        "spoor, dung and no-type sightings are not flagged",
    )
    expect(
        "no-type sightings",
        cp["Sightings with no sighting type"] != "0",
        f"{cp['Sightings with no sighting type']}",
    )
    expect(
        "duplicates found",
        int(
            cp[
                "Possible duplicate reports (same form contents, < 30 min and < 1 km apart)"
            ].replace(",", "")
        )
        >= 2,
        f"{cp['Possible duplicate reports (same form contents, < 30 min and < 1 km apart)']} flagged",
    )
    expect(
        "open patrols", cp["Patrols left open over 14h (time capped at 14h)"] == "1", ""
    )
    if has_live:
        hk = outs["period_hwc_kpis"].iloc[0]
        expect(
            "HWC totals",
            (
                hk["HWC incidents"],
                hk["People injured"],
                hk["People killed"],
                hk["Livestock killed"],
            )
            == ("24", "3", "1", "16"),
            f"{hk.to_dict()} (ER: 24, 3, 1, 16)",
        )
        mk = outs["period_mike_kpis"].iloc[0]
        expect("MIKE elephants", mk["Elephant carcasses"] == "5", f"{mk.to_dict()}")
    print(f"\n{'ALL CLEAR' if not fails else f'{fails} FAILURE(S)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
