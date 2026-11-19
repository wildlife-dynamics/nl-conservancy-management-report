# Naibunga Lower Conservancy Management Report — User Guide

This guide walks you through running the Naibunga Lower Conservancy
Management Report, which reads patrol effort and field monitoring events from EarthRanger
and produces an interactive dashboard and a Word report for a period you
choose.

## Overview

Each run answers, for the chosen period:

- how much patrol effort was delivered, by whom, and where
- what wildlife was seen, in what numbers, and where it concentrates
- how many carcasses and injured animals were found, of which species and cause
- what security and illegal activity was recorded
- what human-wildlife conflict occurred, and what it cost
- how each month compares with the others in the period

and delivers:

- **A dashboard** — 42 widgets across the report sections, with a **month
  selector** at the top so you can step through the period a month at a time
- **A Word report** (`naibunga_lower_management_report_<hash>.docx`) — the same
  material with headings, numbered tables and figures, ready to send or print
- **Downloadable data** in the Files tab

## Prerequisites

- Ecoscope Desktop, or another Ecoscope workflow runner
- An EarthRanger instance with patrols recorded and the Field Monitoring and
  Animal Health event types in use, and a username and password you can use

## Step 1 — Add the workflow template

In the runner, go to **Workflow Templates** → **Add Workflow Template**, and
paste this into the **Github Link** field:

```
https://github.com/wildlife-dynamics/nl-conservancy-management-report.git
```

Click **Add Template**. The card may show *Initializing…* for a minute or two
while the environment is built. This happens once.

## Step 2 — Add an EarthRanger connection

Go to **Data Sources** → **Connect** → **EarthRanger**, and fill in:

| Field | Value |
|---|---|
| Data Source Name | a label you will recognise, e.g. `Naibunga Lower` |
| EarthRanger URL | your instance, e.g. `naibungalower.pamdas.org` |
| EarthRanger Username | your username |
| EarthRanger Password | your password |

Credentials are not checked here — a wrong password shows up as an error when
the workflow runs.

## Step 3 — Select the workflow

The template appears in **Workflow Templates** as
`nl-conservancy-management-report`. Click it to open the run form.

## Step 4 — Fill in the form

Seven fields, none of them long.

| Field | What it does |
|---|---|
| **Workflow Name** | names this run in the runner's list |
| **Workflow Description** | optional; appears on the Word report cover |
| **Prepared by** | the name of the person preparing the analysis, printed on the cover |
| **Data Source** | the EarthRanger connection from Step 2 |
| **Time Range** | timezone, **Since** and **Until**. Everything is drawn from this window, and the month-by-month breakdown comes from splitting it. |
| **Base Maps** | the background for the maps. The defaults are fine. |
| **Group by** | *Year and Month* (the default) gives one dashboard view per month. Leave it empty for one view over the whole period. The Word report's month-by-month tables appear either way. |
| **Priority species** | up to five species for the proportional-symbol map (default Elephant, Lion, Wild Dog, Leopard). Use the English name as the report shows it. |

The report template itself is not in the form — it is fetched automatically
when the workflow runs.

Click **Submit**.

## What the run does

1. Fetches completed patrols and their GPS tracks for the time range
2. Fetches every event in the range and works out which ones count
3. Builds the charts, tables and maps, once per month and once for the period
4. Fills in the Word template
5. Writes everything to the results folder and assembles the dashboard

A full year takes several minutes; most of it is rendering maps.

## Reading the dashboard

The dropdown at the top switches months. Two widgets — *Events per Month by
Category* and *Patrol Distance per Month* — deliberately ignore it and always
show the whole period, because their point is the comparison across months.

| # | Section | What it tells you |
|---|---|---|
| 1 | **Patrol effort** | Four cards: patrols, hours, kilometres, average speed. Your top-line effort numbers. Hours are capped at 14 per patrol (see below). |
| 2 | **Patrol coverage** | Where rangers actually went, one colour per patrol type, plus effort split by transport type and by mandate. |
| 3 | **Patrol by ranger** | The same effort per ranger, counting team leaders and team members. |
| 4 | **Event summary** | How many events were recorded and of what type. Patrol details reports, Meeting Report and the Livestock Household Survey are excluded — they are paperwork, not field observations. |
| 5 | **Wildlife monitoring** | Species seen, split into visual sightings, individuals counted, signs (spoor or dung) and sightings with no type. A second map shows only your priority species, symbol area proportional to the number of animals. |
| 6 | **Animal health** | Carcasses and sick or injured animals, by cause, with a map. |
| 7 | **MIKE** | The elephant mortality panel: carcasses found, PIKE, and a sunburst of type of death (inner ring) and cause (outer ring). |
| 8 | **Security** | Arrests, contacts, gunshots, poacher camps and spoor, snares, theft and recovered trophies — counts by type, a map, and a log of each incident. |
| 9 | **Human-wildlife conflict** | Incidents, people hurt, livestock lost, retaliation, by species and event type, with a map. |
| 10 | **Human injury and death** | All causes, not just conflict: accidents and security incidents too. |
| | **Data completeness** | For the whole period: blank fields, patrols left open, impossible locations and possible duplicate reports. Read this first — it tells you how much to trust everything above. |

## Downloading the results

Open the **Files** tab for the Word report and the data files. Charts and maps
are also written to the results folder and every one is embedded in the Word
report, which is usually what you want to send on.

## How things are counted

Worth knowing before you quote a number.

**Patrol effort counts completed patrols only.** A patrol still running, or
cancelled, is not included. Distance comes from the GPS track, so a patrol with
no track contributes a patrol count but no kilometres — the Data completeness
table counts those.

**Patrol time is capped at 14 hours per patrol.** Patrols that are not ended in
EarthRanger keep running, some for days; uncapped, 61 such patrols made up most
of the 11,563 hours recorded for Jan–Nov 2026. A patrol that overlaps the start
or end of the period counts only the part inside it, and counts in the month it
started (or the first month, if it started before the period).

**Patrol details (team, transport, mandate, station) were first recorded on 25
April 2026**, in a report linked to the patrol; since 18 November 2026 they are
entered on the patrol itself, and the report reads both. Patrols before 25 April
show *No patrol details*. Earlier records could hold several mandates, listed as
a combination such as *Routine, Security*.

**Event totals exclude paperwork.** Patrol details reports, Meeting Report and the
Livestock Household Survey never appear in event counts or charts.

**The report period uses the incident date where the form has one.** Human
Injury, Crop damage and Infrastructure damage use *Incident date & time*;
Poisoning uses *Date & time*; Arrest uses *Arrest time*; Contact uses *Contact
time*. Everything else uses the EarthRanger event time. So an incident reported
days after it happened is counted in the month it happened — unless that date
falls outside the period, in which case the EarthRanger time is used, so nothing
lands in a month the report does not cover.

**Records marked for deletion are left out.** Any report or patrol whose
title contains "delete" is dropped before anything is counted; the Data
completeness table says how many.

**Old Ranger Basic forms are shown under the current form's name** (e.g.
*Wildlife Sighting*, not *Wildlife Sighting (Ranger Basic)*). Old records that
were copied onto the current forms count once, as the copy.

**A month marked * is a partial month** — the period starts or ends inside it,
so its totals are not comparable with a full month's.

**Ranger names are harmonised.** The Team Leader and Team members lists in
EarthRanger spell some rangers differently (*Edung Mosienye* / *Edung Mosieny*,
*Micka* / *Mika Yiangere*); each pair is reported as one person. A patrol's
distance and time are credited to every team member, so the ranger table does
not add up to the patrol totals.

**PIKE** is the proportion of elephant carcasses found that were illegally
killed. It is only meaningful with a reasonable number of carcasses — with two
or three, a single case moves it enormously.

**Wildlife numbers are sightings, not population.** *Individuals counted* adds
up what rangers counted on visual sightings; the same herd seen twice counts twice.

**'Unknown' and 'Not recorded' mean the field was left blank**, not that
something was investigated and came back unknown.

**Species names are standardised before counting.** The forms spell the same
animal several ways, so the workflow maps them onto one name — one elephant is
one bar rather than three.

## Privacy

Names, ID numbers, telephone numbers, dates of birth, ethnicity and tribe are
**never** included — not in a widget, not in the Word report, not in a
downloadable file. Each detail table uses a fixed list of fields per event
type, so a field added to a form later cannot leak into an output.

Ranger names do appear in the patrol effort table, which is the point of that
table. Treat the report as internal.
