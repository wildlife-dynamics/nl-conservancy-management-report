"""Build SYNTHETIC mock-io fixtures for the Naibunga Lower management report.

Every row is generated: seeded RNG, uuid5-derived ids, random-walk tracks and
jittered points inside a Naibunga Lower (Laikipia) bounding box, made-up
ranger/team names. Nothing is copied from a real EarthRanger instance.

The *model* (event-type slugs, categories, event_details titles) follows the
PRD ("Naibunga Lower - Conservancy Management Report MRD"). The slugs are
derived from the PRD titles and MUST be confirmed against the Naibunga ER
instance before the first live run -- they are collected in the spec's
`Event Types` card defaults so they can be corrected without code changes.

Outputs (all consumed via `mock_io_overrides` in test-cases.yaml):

  events.example-return.parquet
      Mock for get_events AND process_events_details (both io-tagged; the
      downstream one clobbers the upstream, so one fixture serves both).
      `event_details` uses title-mapped keys (process_events_details with
      map_to_titles=True) and, like `patrols`, is stored as a JSON string:
      that is exactly what apply_sql_query's sanitize step produces from the
      live list/dict values, and a parquet round-trip would otherwise turn
      top-level lists into numpy arrays that sanitize does not JSON-encode.
  patrols.example-return.parquet
      Mock for get_patrols_from_combined_params (`patrol_segments` as JSON).
  patrol-obs.example-return.parquet
      Mock for get_patrol_observations_from_patrols_df_and_combined_params.
  *-empty.example-return.parquet
      Zero-row variants (same schema) for the empty-fixture regression case.

Planted rows (each exercised by the data-completeness table and the cases):
  - patrol serial 2005 has NO observations ("no or short track")
  - patrol serial 2011 has a 6-point track under 0.5 km ("short track")
  - patrol serial 2017 lasts 15 h ("duration over 14h")
  - patrol serials 2003 and 2013 have NO Patrol Info event
  - two events have no geometry ("events with no location")
  - several events have an empty `patrols` list ("recorded off-patrol")
  - one Snares & Traps event picks "Other" with no notes
  - one Wildlife Sighting reports 0 individuals
  - one Arrest carries an Arrest time in the previous month (incident-date
    rule: it must be bucketed into September, not October)
  - Patrol Info, Meeting Report and Livestock Household Survey rows exist so
    the event totals can be checked to exclude them

Run from the inner workflow env (needs geopandas + pyarrow):
    cd ecoscope-workflows-nl-conservancy-management-report-workflow
    pixi run python ../dev/fixtures/build_naibunga_fixtures.py
"""

import json
import uuid
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

OUT_DIR = Path(__file__).resolve().parent
RNG = np.random.default_rng(20261001)
NS = uuid.UUID("6e1b0a39-5c1d-4f7a-9a51-000000000001")

# Naibunga Lower (Laikipia, Kenya) -- rough bounding box
LON0, LON1, LAT0, LAT1 = 36.95, 37.25, 0.40, 0.65

# Report window used by the test cases: Oct + Nov 2026 (UTC)
MONTHS = [pd.Timestamp("2026-10-01T00:00:00Z"), pd.Timestamp("2026-11-01T00:00:00Z")]

PATROL_TYPES = [
    ("routine_patrol", "Routine"),
    ("motorbike_patrol", "Motorbike"),
    ("joint_operation", "Joint Operations"),
]
STATIONS = ["Il Motiok", "Kijabe", "Nkiloriti"]
MANDATES = ["Anti-poaching", "Wildlife monitoring", "Community security"]
TRANSPORTS = {
    "routine_patrol": "Foot",
    "motorbike_patrol": "Motorbike",
    "joint_operation": "Vehicle",
}
RANGERS = [f"Ranger {c}" for c in "ABCDEFGHIJ"]


def fid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def rand_point() -> Point:
    return Point(
        round(float(RNG.uniform(LON0, LON1)), 6),
        round(float(RNG.uniform(LAT0, LAT1)), 6),
    )


def iso(ts: pd.Timestamp) -> str:
    return ts.tz_convert("Africa/Nairobi").isoformat()


# --------------------------------------------------------------------------
# Patrols, observations
# --------------------------------------------------------------------------
patrol_rows, obs_frames, patrol_ids = [], [], {}
for i in range(20):
    serial = 2001 + i
    month = MONTHS[i % 2]
    slug, display = PATROL_TYPES[i % 3]
    pid = fid(f"patrol/{serial}")
    patrol_ids[serial] = pid
    start = month + pd.Timedelta(days=int(1 + (i * 3) % 27), hours=4)  # 07:00 EAT
    hours = 15.0 if serial == 2017 else float(RNG.uniform(3, 8))
    end = start + pd.Timedelta(hours=hours)
    leader = RANGERS[i % len(RANGERS)]
    patrol_rows.append(
        {
            "id": pid,
            "priority": 0,
            "state": "done",
            "objective": None,
            "serial_number": serial,
            "title": f"{display} patrol {serial}",
            "files": "[]",
            "notes": "[]",
            "patrol_segments": json.dumps(
                [
                    {
                        "patrol_type": slug,
                        "leader": {"name": leader},
                        "time_range": {"start_time": iso(start), "end_time": iso(end)},
                    }
                ]
            ),
            "updates": "[]",
        }
    )
    if serial == 2005:  # planted: no track at all
        continue
    n_pts = 6 if serial == 2011 else int(hours * 12)  # one fix per 5 min
    step = 0.00005 if serial == 2011 else 0.0012
    lon, lat = (
        RNG.uniform(LON0 + 0.03, LON1 - 0.03),
        RNG.uniform(LAT0 + 0.03, LAT1 - 0.03),
    )
    walk = RNG.normal(0, step, size=(n_pts, 2)).cumsum(axis=0)
    lons = np.clip(lon + walk[:, 0], LON0, LON1)
    lats = np.clip(lat + walk[:, 1], LAT0, LAT1)
    times = pd.date_range(start, end, periods=n_pts)
    obs_frames.append(
        gpd.GeoDataFrame(
            {
                "extra__id": [fid(f"obs/{serial}/{k}") for k in range(n_pts)],
                "extra__created_at": times,
                "extra__recorded_at": times,
                "extra__subject_id": fid(f"subject/{leader}"),
                "groupby_col": pid,
                "fixtime": times,
                "junk_status": False,
                "patrol_id": pid,
                "patrol_title": f"{display} patrol {serial}",
                "patrol_serial_number": serial,
                "patrol_start_time": iso(start),
                "patrol_end_time": iso(end),
                "patrol_type": fid(f"patrol-type/{slug}"),
                "patrol_type__value": slug,
                "patrol_type__display": display,
                "patrol_status": "done",
                "patrol_subject": leader,
            },
            geometry=[Point(x, y) for x, y in zip(lons, lats)],
            crs=4326,
        )
    )

patrols_df = pd.DataFrame(patrol_rows)
obs = gpd.GeoDataFrame(pd.concat(obs_frames, ignore_index=True), crs=4326)
patrol_starts = {
    r["serial_number"]: pd.Timestamp(
        json.loads(r["patrol_segments"])[0]["time_range"]["start_time"]
    )
    for r in patrol_rows
}

# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------
event_rows = []


def add_event(
    slug,
    display,
    category,
    details,
    *,
    when,
    serial=None,
    geometry="random",
    on_patrol=True,
):
    k = len(event_rows)
    patrols = [patrol_ids[serial]] if (on_patrol and serial) else []
    event_rows.append(
        {
            "id": fid(f"event/{k}"),
            "time": when,
            "event_type": slug,
            "event_category": category,
            "title": display,
            "priority": 0,
            "state": "resolved",
            "serial_number": str(50000 + k),
            "event_type_display": display,
            "reported_by_name": RANGERS[k % len(RANGERS)],
            "event_details": json.dumps(details),
            "patrols": json.dumps(patrols),
            "geometry": rand_point() if geometry == "random" else geometry,
        }
    )


def t(month_idx, day, hour=9):
    return MONTHS[month_idx] + pd.Timedelta(
        days=day - 1, hours=hour - 3
    )  # local hour -> UTC


FM, AH, RM, LG = (
    "field_monitoring",
    "animal_health",
    "rangeland_management",
    "logistics",
)

# Patrol Info (logistics) -- one per patrol except the planted gaps
for serial, pid in patrol_ids.items():
    if serial in (2003, 2013):
        continue
    i = serial - 2001
    slug = PATROL_TYPES[i % 3][0]
    members = [RANGERS[(i + j + 1) % len(RANGERS)] for j in range(1 + i % 3)]
    add_event(
        "patrol_info",
        "Patrol Info",
        LG,
        {
            "Mandate": MANDATES[i % 3],
            "Station": STATIONS[i % 3],
            "Transport Type": TRANSPORTS[slug],
            "Team Leader": RANGERS[i % len(RANGERS)],
            "Team members": members,
            "Armed": "Yes" if i % 2 else "No",
        },
        when=patrol_starts[serial] + pd.Timedelta(minutes=10),
        serial=serial,
    )

# Wildlife sightings
SPECIES = [
    ("Elephant", (1, 40)),
    ("Reticulated Giraffe", (1, 12)),
    ("Grevy's Zebra", (2, 30)),
    ("Lion", (1, 6)),
    ("Lesser Kudu", (1, 5)),
    ("Gerenuk", (1, 4)),
]
for m in (0, 1):
    for k in range(14):
        sp, (lo, hi) = SPECIES[(k + m) % len(SPECIES)]
        visual = k % 4 != 3
        n = (
            0 if (m == 0 and k == 5) else int(RNG.integers(lo, hi + 1))
        )  # planted 0-individual sighting
        add_event(
            "wildlife_sighting",
            "Wildlife Sighting",
            FM,
            {
                "Sighting type": "Visual" if visual else "Spoor",
                "Species": sp,
                "Total Individuals": n,
            },
            when=t(m, 2 + k * 2, 8 + k % 6),
            serial=2001 + m + 2 * (k % 10),
            on_patrol=k % 5 != 4,  # some recorded off-patrol
        )

# Animal health: carcasses and sick/injured animals
DEATH_TYPES = [
    ("Poached", "Snare"),
    ("Conflict", "Spearing"),
    ("Natural", "Drought"),
    ("PAC/Management", "Problem animal control"),
    ("Unknown", "Unknown"),
]
carcass_specs = [
    (
        0,
        "Elephant",
        0,
        "Male",
        "Adult",
        "Fresh",
        "Less than 1 week",
        "Both tusks recovered",
    ),
    (
        0,
        "Elephant",
        2,
        "Female",
        "Sub-adult",
        "Decomposed",
        "1-4 weeks",
        "Tusks missing",
    ),
    (0, "Reticulated Giraffe", 1, "Male", "Adult", "Fresh", None, None),
    (1, "Elephant", 0, "Male", "Adult", "Fresh", "Less than 1 week", "Tusks missing"),
    (
        1,
        "Elephant",
        1,
        "Female",
        "Juvenile",
        "Old",
        "Over 1 month",
        "Both tusks recovered",
    ),
    (1, "Elephant", 4, "Unknown", "Adult", "Skeleton", "Over 1 month", "Tusks missing"),
    (1, "Grevy's Zebra", 2, "Female", "Adult", "Fresh", None, None),
    (1, "Lion", 3, "Male", "Adult", "Fresh", None, None),
]
for k, (m, sp, d, sex, age, state, carcass_age, tusks) in enumerate(carcass_specs):
    death, cause = DEATH_TYPES[d]
    details = {
        "Species": sp,
        "Sex": sex,
        "Animal Age": age,
        "State of carcass": state,
        "Type of Death": death,
        "Cause of Death": cause,
        "Trophy Status": "Intact"
        if "recovered" in (tusks or "recovered")
        else "Removed",
        "Information source": "Ranger patrol",
    }
    if sp == "Elephant":
        details.update({"Age of Carcass": carcass_age, "Tusk Status": tusks})
    add_event(
        "animal_carcass",
        "Animal Carcass",
        AH,
        details,
        when=t(m, 4 + 3 * k, 10),
        serial=2001 + m + 2 * k,
    )
for k, (m, sp, d) in enumerate(
    [
        (0, "Elephant", 1),
        (0, "Lion", 0),
        (1, "Reticulated Giraffe", 2),
        (1, "Elephant", 0),
    ]
):
    add_event(
        "sick_injured_animal",
        "Sick / Injured Animal",
        AH,
        {
            "Species": sp,
            "Type of Injury": DEATH_TYPES[d][0],
            "Cause of Injury": DEATH_TYPES[d][1],
        },
        when=t(m, 6 + 5 * k, 11),
        serial=2002 + m + 2 * k,
    )

# Security / illegal activity
SECURITY = [
    (
        "illegal_activity",
        "Illegal Activity",
        {"Activity": "Charcoal burning", "Number of suspects": 3},
    ),
    (
        "snares_traps",
        "Snares & Traps",
        {
            "Type": "Wire snare",
            "Status": "Removed",
            "Total number of snares/traps": 6,
            "Species caught": "None",
        },
    ),
    (
        "poacher_camp",
        "Poacher Camp",
        {
            "Size of camp": "Small",
            "Camp status": "Abandoned",
            "Camp age": "1-2 weeks",
            "Estimated number of people": 4,
        },
    ),
    (
        "poacher_spoor",
        "Poacher spoor",
        {
            "Type of footwear or Vehicle source": "Sandals",
            "Age (hours)": 12,
            "Direction of travel": "North",
        },
    ),
    (
        "gunshot",
        "Gunshot",
        {
            "Number of shots": 2,
            "Type of shot": "Single",
            "Estimated distance": "1-2 km",
            "Suspected activity": "Poaching",
        },
    ),
    (
        "arrest",
        "Arrest",
        {
            "Reason for arrest": "Bushmeat possession",
            "Total number of people arrested": 2,
            "Receiving police station": "Il Ng'wesi",
        },
    ),
    (
        "contact",
        "Contact",
        {
            "Number of suspects": 5,
            "Targeted Group(s)": "Livestock raiders",
            "Rangers injured": 1,
            "Rangers killed": 0,
            "Suspects injured": 2,
            "Suspects killed": 0,
            "Civilians injured": 0,
            "Civilians killed": 0,
            "Police injured": 0,
            "Police killed": 0,
        },
    ),
    (
        "recovered_trophy",
        "Recovered trophy",
        {"Trophy type": "Ivory", "Trophy weight (kg)": 7.5},
    ),
    (
        "theft",
        "Theft",
        {
            "Item type": "Livestock",
            "Number of animals or items": 12,
            "Number of recoveries": 9,
        },
    ),
    (
        "poisoning",
        "Poisoning",
        {
            "Suspected motive": "Retaliation",
            "Species affected": "Lion",
            "Total count": 2,
            "Arrest made?": "No",
        },
    ),
]
for m in (0, 1):
    for k, (slug, display, details) in enumerate(SECURITY):
        d = dict(details)
        when = t(m, 3 + 2 * k, 14)
        if slug == "arrest":
            d["Arrest time"] = iso(when - pd.Timedelta(hours=6))
            if m == 0:  # planted: reported 1 Oct, arrested 30 Sep -> September bucket
                when = t(0, 1, 7)
                d["Arrest time"] = iso(pd.Timestamp("2026-09-30T18:00:00Z"))
        if slug == "contact":
            d["Contact time"] = iso(when - pd.Timedelta(hours=2))
        if slug == "poisoning":
            d["Date & time"] = iso(when - pd.Timedelta(days=1))
        if slug == "snares_traps" and m == 1:
            d["Type"] = "Other"  # planted: "Other" with no notes
        add_event(
            slug,
            display,
            FM,
            d,
            when=when,
            serial=2001 + m + 2 * k,
            on_patrol=k % 4 != 0,
        )

# HWC and human injury / death
HWC = [
    (
        0,
        "hwc_livestock_predation",
        "HWC Livestock Predation",
        {
            "Species responsible": "Lion",
            "Livestock type": "Cattle",
            "Number of livestock injured": 1,
            "Number of livestock killed": 2,
            "Retaliation": "Yes",
        },
    ),
    (
        0,
        "crop_damage",
        "Crop damage",
        {
            "Cause": "Wildlife",
            "Species responsible": "Elephant",
            "Crop type": "Maize",
            "Extent of damage": "Large (> 1 acre)",
            "Retaliation": "No",
        },
    ),
    (
        0,
        "human_injury",
        "Human Injury",
        {
            "Cause": "Human-wildlife conflict",
            "Species responsible": "Elephant",
            "Number of people injured": 1,
        },
    ),
    (
        0,
        "human_injury",
        "Human Injury",
        {
            "Cause": "Accident",
            "Species responsible": None,
            "Number of people injured": 2,
        },
    ),
    (
        1,
        "hwc_livestock_predation",
        "HWC Livestock Predation",
        {
            "Species responsible": "Hyena",
            "Livestock type": "Goats",
            "Number of livestock injured": 0,
            "Number of livestock killed": 5,
            "Retaliation": "No",
        },
    ),
    (
        1,
        "crop_damage",
        "Crop damage",
        {
            "Cause": "Wildlife",
            "Species responsible": "Elephant",
            "Crop type": "Beans",
            "Extent of damage": "Small (< 1/4 acre)",
            "Retaliation": "No",
        },
    ),
    (
        1,
        "crop_damage",
        "Crop damage",
        {
            "Cause": "Livestock",
            "Species responsible": None,
            "Crop type": "Maize",
            "Extent of damage": "Medium",
            "Retaliation": "No",
        },
    ),
    (
        1,
        "infrastructure_damage",
        "Infrastructure damage",
        {
            "Cause": "Wildlife",
            "Species responsible": "Elephant",
            "Infrastructure type": "Water tank",
        },
    ),
    (
        1,
        "human_death",
        "Human Death",
        {
            "Cause": "Human-wildlife conflict",
            "Species responsible": "Buffalo",
            "Number of people killed": 1,
        },
    ),
    (
        1,
        "human_death",
        "Human Death",
        {
            "Cause": "Security incident",
            "Species responsible": None,
            "Number of people killed": 1,
        },
    ),
]
for k, (m, slug, display, details) in enumerate(HWC):
    d = dict(details)
    when = t(m, 5 + 2 * k, 16)
    if slug in ("human_injury", "crop_damage", "infrastructure_damage"):
        d["Incident date & time"] = iso(when - pd.Timedelta(hours=10))
    add_event(slug, display, FM, d, when=when, on_patrol=False)

# Rangeland + logistics events that must NOT count in event totals
for m in (0, 1):
    add_event(
        "rangelands_meeting",
        "Rangelands Meeting",
        RM,
        {
            "Number Attended Male": 14,
            "Number Attended Female": 9,
            "Meeting Topics": "Dry-season grazing",
        },
        when=t(m, 12, 10),
        on_patrol=False,
    )
    add_event(
        "rangeland_rehabilitation",
        "Rangeland Rehabilitation",
        RM,
        {"Area(ha)": 3.5, "Intervention Type": "Reseeding"},
        when=t(m, 18, 10),
        on_patrol=False,
    )
    add_event(
        "livestock_household_survey",
        "Livestock Household Survey Questionnaire",
        RM,
        {"Household size": 6},
        when=t(m, 20, 10),
        on_patrol=False,
    )
    add_event(
        "meeting_report",
        "Meeting Report",
        LG,
        {"Meeting type": "Staff"},
        when=t(m, 22, 10),
        on_patrol=False,
    )

# Planted: two events without a location
event_rows[3]["geometry"] = None
event_rows[-9]["geometry"] = None

events = gpd.GeoDataFrame(pd.DataFrame(event_rows), geometry="geometry", crs=4326)
events["time"] = pd.to_datetime(events["time"], utc=True)
events = events.sort_values("time", ignore_index=True)

# --------------------------------------------------------------------------
# Write
# --------------------------------------------------------------------------
outputs = {
    "events": events,
    "patrols": patrols_df,
    "patrol-obs": obs,
}
for name, df in outputs.items():
    df.to_parquet(OUT_DIR / f"{name}.example-return.parquet", index=False)
    df.iloc[0:0].to_parquet(
        OUT_DIR / f"{name}-empty.example-return.parquet", index=False
    )

print(f"patrols: {len(patrols_df)}, obs: {len(obs)}, events: {len(events)}")
print(events.groupby(["event_category", "event_type"]).size().to_string())
print(f"wrote fixtures to {OUT_DIR}")
