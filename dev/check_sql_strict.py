"""Strict SQL check for nl-conservancy-management-report.

Runs the spec's apply_sql_query tasks the way Ecoscope Desktop does: the
task's own validator and deny-by-default SQLite authorizer (copied verbatim
from ecoscope/platform/tasks/transformation/_sql_query.py), on events that
reproduce what process_events_details hands over, split by month.

Data: the HWC report's real 2026 events (if ../nl-hwc-report/.scratch/
live-events.json exists) plus synthetic rows for every case the event
queries special-case -- bilingual species, sighting types, Silent Source,
Patrol Info linked to a patrol, test forms, a legacy event and its
migrated copy, an empty theft at 0,0, both Illegal Activity types.

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
        ),
        ev(
            "wildlife_sighting",
            T.format(1),
            {"Sighting type": "Spoor", "Species": "Hyena - Spotted / Fisi (madoa)"},
        ),
        ev(
            "wildlife_sighting",
            T.format(2),
            {"Sighting type": "Dung/Pellets", "Species": "Elephant / Ndovu (Tembo)"},
        ),
        ev("silence_source_rep", T.format(2), {}, "Silent Source", "analyzer_event"),
        ev(
            "test_patrol_info",
            T.format(3),
            {
                "Mandate": ["Routine", "Security"],
                "Transport Type": "Foot",
                "Team Leader": "Leader A",
                "Team members": ["Ranger B", "Ranger C"],
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
        ),
        ev(
            "theft",
            T.format(5),
            {"additional": {"stolen_array": []}},
            "Theft",
            geom="POINT (0 0)",
        ),
        ev(
            "illegal_activity_rep",
            T.format(5),
            {"Activity": "Charcoal Production", "Number of Suspect(s)": 2},
            "Illegal Activity",
        ),
        ev(
            "illegal_activity_rep_ranger",
            T.format(6),
            {"Activity": "Logging"},
            "Illegal Activity",
            "ranger_basic",
        ),
    ]


def load():
    rows = synthetic()
    live = ROOT.parent / "nl-hwc-report" / ".scratch" / "live-events.json"
    if live.exists():
        rows += json.load(open(live))
    df = pd.DataFrame(rows)
    df["patrols"] = df["patrols"].map(lambda v: v if isinstance(v, list) else [])
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    return df, live.exists()


def main():
    fails = 0

    def report(name, ok, msg=""):
        nonlocal fails
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name:20s} {msg}")

    evs, has_live = load()
    print(
        f"input: {len(evs)} events ({'real HWC events + ' if has_live else ''}synthetic cases)\n"
    )
    prep = apply_sql_query(evs, query("events_prepared"))
    report(
        "events_prepared",
        True,
        f"{len(prep)} rows, counted {int(prep.counted.sum())}, conflict {int(prep.is_conflict.sum())}",
    )
    prep["report_time"] = pd.to_datetime(
        prep["report_time"], utc=True, format="mixed"
    ).dt.tz_convert(TZ)
    prep["_m"] = prep["report_time"].dt.strftime("%Y-%m")
    months = {m: g.drop(columns="_m") for m, g in prep.groupby("_m")}
    indexed = prep.drop(columns="_m")
    outs = {}
    for tid, t in TASKS.items():
        if t["task"] != "apply_sql_query" or tid in ("events_prepared", "patrol_info"):
            continue
        src = json.dumps(t)
        if "events_grouped.return" in src:
            frames = months
        elif "events_indexed.return" in src:
            frames = {"(all)": indexed}
        else:
            continue
        try:
            for m, g in frames.items():
                o = apply_sql_query(g, query(tid))
            outs[tid] = apply_sql_query(indexed, query(tid))
            report(tid, True, f"{len(frames)} frame(s)")
        except Exception as e:
            report(tid, False, f"{m}: {e}")
    try:
        pi = apply_sql_query(prep, query("patrol_info"))
        report(
            "patrol_info",
            len(pi) == 1 and pi.iloc[0]["mandate"] == "Routine, Security",
            pi.to_dict("records").__repr__()[:110],
        )
    except Exception as e:
        report("patrol_info", False, str(e))

    def expect(name, cond, detail):
        report(name, bool(cond), detail)

    print("\nbehaviour on the cases this fix targets:")
    c = prep.set_index("id")
    expect("silent source", c.loc["ev-4", "counted"] == 0, "Silent Source not counted")
    expect("patrol info", c.loc["ev-5", "counted"] == 0, "Patrol Info not counted")
    expect("test form", c.loc["ev-6", "counted"] == 0, "TEST form not counted")
    expect(
        "legacy duplicate",
        c.loc["legacy-1", "counted"] == 0 and c.loc["ev-8", "counted"] == 1,
        "original dropped, migrated copy kept",
    )
    ws = outs.get("wildlife_summary")
    if ws is not None:
        el = ws[ws["Species"] == "Elephant"]
        expect(
            "bilingual species",
            len(el) == 1 and "Elephant / Ndovu (Tembo)" not in set(ws["Species"]),
            f"Elephant rows: {len(el)}",
        )
        expect(
            "dung counted as sign",
            int(el["Signs (spoor or dung)"].iloc[0]) >= 1
            and int(el["Sightings (visual)"].iloc[0]) >= 1,
            el.to_dict("records").__repr__()[:110],
        )
    mk = outs.get("mike_kpis")
    if mk is not None and has_live:
        expect(
            "MIKE elephants",
            int(mk["Elephant carcasses"].iloc[0]) == 5,
            f"{int(mk['Elephant carcasses'].iloc[0])} elephant carcasses (ER has 5 in 2026)",
        )
    hk = outs.get("hwc_kpis")
    if hk is not None and has_live:
        r = hk.iloc[0]
        expect(
            "HWC totals",
            (
                r["HWC incidents"],
                r["People injured"],
                r["People killed"],
                r["Livestock killed"],
            )
            == (24, 3, 1, 16),
            f"incidents {r['HWC incidents']}, injured {r['People injured']}, killed {r['People killed']}, livestock killed {r['Livestock killed']} (ER: 24, 3, 1, 16)",
        )
    sec = outs.get("security_counts")
    if sec is not None:
        expect(
            "illegal activity",
            int(sec.loc[sec["Event type"] == "Illegal Activity", "Incidents"].sum())
            == 2,
            sec.to_dict("records").__repr__()[:110],
        )
    se = outs.get("security_events")
    if se is not None:
        th = se[se["Event type"] == "Theft"]
        expect(
            "theft row",
            len(th) == 1
            and th.iloc[0]["Details"] == "No details recorded"
            and th.iloc[0]["Coordinates (lat, lon)"] == "Not recorded",
            th.iloc[0][["Coordinates (lat, lon)", "Details"]].to_dict().__repr__()
            if len(th)
            else "missing",
        )
    abc = outs.get("ah_by_cause")
    if abc is not None and has_live:
        expect(
            "carcass causes",
            int(abc["Carcasses"].sum()) == 7,
            f"{int(abc['Carcasses'].sum())} of 7 carcasses placed in a cause row",
        )
    print(f"\n{'ALL CLEAR' if not fails else f'{fails} FAILURE(S)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
