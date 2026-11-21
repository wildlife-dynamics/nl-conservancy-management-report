"""Build the Word template for the Naibunga Lower Conservancy Management Report.

Writes resources/templates/naibunga_lower_management_report_template.docx, a
docxtpl (Jinja2) template rendered by ext-custom's `create_docx` task. Values
are XML-escaped with |e because create_docx renders without autoescape (a bare
"&" or "<" would be dropped). Re-run this script (instead of hand-editing the
.docx) whenever the report layout or the context keys in spec.yaml's
`create_report` task change.

Context contract (keys must match `create_report.context.items` in spec.yaml):
  report_date    timerange -> "{{ report_date }}"
  prepared_by    text      -> "{{ prepared_by }}"
  period_*       table, one row     -> stat cards (label over a large number)
  *_months       table, row/month   -> shown only when the period spans more
                                       than one month
  <other tables> table -> {key}.col_labels / {key}.tbl_contents; grouped
                 (merge_groups=True) tables carry a first "Group" column
  <image keys>   grouped image -> list of {title, image}
  patrol_trend   direct image  -> "{{ patrol_trend }}" (NOT a list)

NUMBERING. Tables and figures are numbered in a single sequence each (Table 1,
2, 3...; Fig. 1, 2, 3...) by a Jinja namespace counter that runs at render
time, so a figure repeated once per month gets its own number each time and a
table hidden because the period is one month long does not leave a gap. The
review asked for one convention throughout; the old builder mixed "Fig. 5.1"
for grouped figures with "Fig. 11." for single ones.

Logos are embedded from resources/images/: the Naibunga Lower logo on the
cover and on the right of the footer, the Ecoscope logo on the left.

spec.yaml pins `template_path` to a Google Drive URL (it is not a form field),
so the built .docx has to be uploaded there as a NEW VERSION of the same Drive
file, keeping the file id. Rebuild and re-upload together, then run
dev/check_template_sync.py.

Run with any Python that has python-docx, e.g. from the inner workflow env:
    cd ecoscope-workflows-nl-management-report-workflow
    pixi run python ../dev/build_report_template.py
"""

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = (
    ROOT / "resources" / "templates" / "naibunga_lower_management_report_template.docx"
)
LOGO_NL = ROOT / "resources" / "images" / "naibunga_lower_logo.jpg"
LOGO_ECO = ROOT / "resources" / "images" / "ecoscope_logo.png"

BLACK = RGBColor(0x00, 0x00, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREY = RGBColor(0x40, 0x40, 0x40)
HEADER_FILL = "5B9BD5"  # light blue; dark enough for white bold text to read
CARD_LABEL_FILL = "DEEAF6"  # pale blue card label strip
CARD_VALUE_FILL = "F7FAFD"

doc = Document()
section = doc.sections[0]
section.orientation = WD_ORIENT.PORTRAIT
section.page_width, section.page_height = Cm(21.0), Cm(29.7)
for side in ("left_margin", "right_margin"):
    setattr(section, side, Cm(1.8))
section.top_margin = section.bottom_margin = Cm(1.8)
TEXT_WIDTH = section.page_width - section.left_margin - section.right_margin

normal = doc.styles["Normal"]
normal.font.name = "Calibri"
normal.font.size = Pt(10)
normal.paragraph_format.space_after = Pt(4)
for level, size in ((1, 15), (2, 12), (3, 11)):
    style = doc.styles[f"Heading {level}"]
    style.font.size = Pt(size)
    style.font.color.rgb = BLACK
    style.paragraph_format.space_before = Pt(14 if level == 1 else 8)
    style.paragraph_format.space_after = Pt(4)
    style.paragraph_format.keep_with_next = True


def para(
    text: str,
    style: str | None = None,
    *,
    center: bool = False,
    size: int | None = None,
    italic: bool = False,
    bold: bool = False,
    color: RGBColor | None = None,
):
    p = doc.add_paragraph(text, style=style)
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in p.runs:
        if size:
            run.font.size = Pt(size)
        run.italic = italic
        run.bold = bold
        if color is not None:
            run.font.color.rgb = color
    return p


def tag(text: str):
    """A paragraph holding only a {%p ... %} tag (docxtpl removes it)."""
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(0)
    return p


def about(text: str) -> None:
    """A short note for the reader on how to read what follows.

    keep_with_next: an intro left alone at the foot of a page, with its
    section's figures on the next, was one source of the whitespace the review
    flagged.
    """
    para(text, size=9, color=GREY).paragraph_format.keep_with_next = True


def note(text: str) -> None:
    """A footnote under a table or figure."""
    p = para(text, size=8, italic=True, color=GREY)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(8)


def bullets(items: list[str]) -> None:
    for text in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        head, _, rest = text.partition(":")
        if rest:
            r = p.add_run(head + ":")
            r.bold = True
            r.font.size = Pt(9)
            r2 = p.add_run(rest)
            r2.font.size = Pt(9)
        else:
            p.add_run(text).font.size = Pt(9)


def caption(kind: str, title: str, *, center: bool = False, below: bool = False):
    """'Table 3. Title' / 'Fig. 2. Title' -- the number comes from the render-time
    counter `ns`, so it is sequential across repeated (per-month) figures.

    `below=True` is for figure captions, which sit UNDER their figure. Table
    captions keep_with_next (caption stays with its table); figure captions do
    not -- the figure above carries keep_with_next instead, which is what keeps
    a figure and its caption on one page.
    """
    counter = "t" if kind == "Table" else "f"
    label = "Table" if kind == "Table" else "Fig."
    p = doc.add_paragraph()
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    lab = p.add_run(
        f"{{% set ns.{counter} = ns.{counter} + 1 %}}{label} {{{{ ns.{counter} }}}}. "
    )
    lab.bold = True
    lab.font.size = Pt(9)
    t = p.add_run(title)
    t.italic = True
    t.font.size = Pt(9)
    p.paragraph_format.space_before = Pt(2 if below else 8)
    p.paragraph_format.space_after = Pt(10 if below else 3)
    p.paragraph_format.keep_with_next = not below
    return p


def shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def repeat_header(row) -> None:
    """Repeat this row at the top of each page the table runs onto, and never
    split a row across pages."""
    tr_pr = row._tr.get_or_add_trPr()
    for name in ("w:tblHeader", "w:cantSplit"):
        el = OxmlElement(name)
        el.set(qn("w:val"), "true")
        tr_pr.append(el)


def header_style(cell, fill: str = HEADER_FILL, color: RGBColor = WHITE) -> None:
    shade(cell, fill)
    for p in cell.paragraphs:
        for run in p.runs:
            run.bold = True
            run.font.color.rgb = color
            run.font.size = Pt(9)


def body_size(row, size: int = 9) -> None:
    for cell in row.cells:
        for p in cell.paragraphs:
            for run in p.runs:
                run.font.size = Pt(size)


def month_label(var: str) -> str:
    """Jinja that prints a "2026-01" group value as "Jan 2026", anything else as is.

    The month grouper's values are "%Y-%m" (the only Year-and-Month grouper
    ecoscope offers), and create_docx sorts the groups by that text, which is
    already chronological. Only the DISPLAY changes here, so figure captions and
    the Group column read "Jan 2026" while staying in Jan -> Dec order.
    """
    m = "'JanFebMarAprMayJunJulAugSepOctNovDec'"
    return (
        f"{{% if {var} is string and {var}|length == 7 and {var}[4:5] == '-' %}}"
        f"{{{{ {m}[({var}[5:7]|int - 1) * 3:({var}[5:7]|int) * 3] }}}} {{{{ {var}[:4] }}}}"
        f"{{% else %}}{{{{ {var}|e }}}}{{% endif %}}"
    )


def dyn_table(key: str) -> None:
    """A dynamic-column table bound to one table context item (no caption)."""
    t = doc.add_table(rows=4, cols=3)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    header, open_row, body, close_row = t.rows
    header.cells[0].text = f"{{%tc for col in {key}.col_labels %}}"
    header.cells[1].text = "{{ col|e }}"
    header.cells[2].text = "{%tc endfor %}"
    for cell in header.cells:  # the middle cell is the one repeated
        header_style(cell)
    repeat_header(header)
    open_row.cells[0].text = f"{{%tr for row in {key}.tbl_contents %}}"
    body.cells[0].text = "{%tc for col in row.cols %}"
    body.cells[1].text = month_label("col")
    body.cells[2].text = "{%tc endfor %}"
    body_size(body)
    close_row.cells[0].text = "{%tr endfor %}"


def table(key: str, title: str, *, footnote: str | None = None) -> None:
    """A captioned table; 'No records' when the item is empty."""
    tag(f"{{%p if {key}.tbl_contents %}}")
    caption("Table", title)
    dyn_table(key)
    if footnote:
        note(footnote)
    tag("{%p else %}")
    para(f"{title}: no records for this period.", italic=True, size=9)
    tag("{%p endif %}")


MONTH_NOTE = (
    "* The period covers only part of this month, so its totals are not "
    "comparable with a full month's."
)


def monthly(key: str, title: str) -> None:
    """A month-by-month table, shown only when the period spans > 1 month.

    Review: "Only display this table when the selected reporting period
    exceeds one month." The spec always builds one row per month, so the row
    count IS the number of months.
    """
    tag(f"{{%p if {key}.tbl_contents and {key}.tbl_contents|length > 1 %}}")
    caption("Table", title)
    dyn_table(key)
    note(MONTH_NOTE)
    tag("{%p endif %}")


def cards(key: str) -> None:
    """Stat cards, LATAM patrol-summary style: a small shaded label over a
    large number, one column per figure, for the whole period. Not captioned
    or numbered -- they are a headline, not a table to look things up in.
    """
    tag(f"{{%p if {key}.tbl_contents %}}")
    t = doc.add_table(rows=2, cols=3)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.style = "Table Grid"
    labels, values = t.rows
    labels.cells[0].text = f"{{%tc for col in {key}.col_labels %}}"
    labels.cells[1].text = "{{ col|e }}"
    labels.cells[2].text = "{%tc endfor %}"
    repeat_header(labels)
    for cell in labels.cells:
        header_style(cell, CARD_LABEL_FILL, GREY)
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.keep_with_next = True
            for r in p.runs:
                r.font.size = Pt(8)
    values.cells[0].text = f"{{%tc for col in {key}.tbl_contents[0].cols %}}"
    values.cells[1].text = "{{ col|e }}"
    values.cells[2].text = "{%tc endfor %}"
    for cell in values.cells:
        shade(cell, CARD_VALUE_FILL)
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(18)
    tag("{%p endif %}")


def images(key: str, title: str, *, footnote: str | None = None) -> None:
    """A grouped image item: one figure per group, each numbered and captioned.

    The group's label (the month, under the month grouper) goes in brackets
    after the title, and only when there is one -- an ungrouped run used to
    print "Patrol tracks by patrol type, " with a trailing comma.
    """
    tag(f"{{%p for item in {key} %}}")
    img = para("{{ item.image }}", center=True)
    img.paragraph_format.keep_with_next = True
    img.paragraph_format.space_after = Pt(0)
    caption(
        "Fig",
        f"{title}{{% if item.title %}} ({month_label('item.title')}){{% endif %}}",
        center=True,
        below=True,
    )
    tag("{%p endfor %}")
    if footnote:
        note(footnote)


def single_image(key: str, title: str, *, condition: str | None = None) -> None:
    """An UNGROUPED image item: create_docx passes one InlineImage, not a list."""
    if condition:
        tag(f"{{%p if {condition} %}}")
    img = para(f"{{{{ {key} }}}}", center=True)
    img.paragraph_format.keep_with_next = True
    img.paragraph_format.space_after = Pt(0)
    caption("Fig", title, center=True, below=True)
    if condition:
        tag("{%p endif %}")


def security_log() -> None:
    """The incident log with FIXED column widths.

    Review: "Reduce the width of the date and coordinates columns to provide
    more space for event details." A dynamic-column table gives every column
    the same width, so this one names its four columns. Under the month
    grouper create_docx prepends a "Group" column; the cells index from the
    END of each row (cols[-4] .. cols[-1]) so they land on the right values
    either way.
    """
    key = "security_events"
    tag(f"{{%p if {key}.tbl_contents %}}")
    caption("Table", "Security incident log")
    widths = (Cm(2.4), Cm(2.6), Cm(3.0), TEXT_WIDTH - Cm(8.0))
    t = doc.add_table(rows=4, cols=4)
    t.style = "Table Grid"
    t.autofit = False
    head, open_row, body, close_row = t.rows
    for cell, text in zip(
        head.cells, ("Date & time", "Location (lat, lon)", "Event type", "Details")
    ):
        cell.text = text
        header_style(cell)
    repeat_header(head)
    open_row.cells[0].text = f"{{%tr for row in {key}.tbl_contents %}}"
    for i, cell in enumerate(body.cells):
        cell.text = f"{{{{ row.cols[{i - 4}]|e }}}}"
    body_size(body, 8)
    close_row.cells[0].text = "{%tr endfor %}"
    for row in t.rows:
        for cell, w in zip(row.cells, widths):
            cell.width = w
    tag("{%p else %}")
    para("Security incident log: no incidents in this period.", italic=True, size=9)
    tag("{%p endif %}")


# ---------------------------------------------------------------- footer
footer = section.footer.paragraphs[0]
footer.style = doc.styles["Normal"]  # the Footer style's centre tab would catch the tab
footer.paragraph_format.tab_stops.add_tab_stop(TEXT_WIDTH, WD_TAB_ALIGNMENT.RIGHT)
footer.add_run().add_picture(str(LOGO_ECO), height=Cm(0.8))
footer.add_run("\t")
footer.add_run().add_picture(str(LOGO_NL), height=Cm(1.3))

# ---------------------------------------------------------------- counters
tag("{%p set ns = namespace(t=0, f=0) %}")

# ---------------------------------------------------------------- cover
logo = doc.add_paragraph()
logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
logo.paragraph_format.space_before = Cm(3)
logo.add_run().add_picture(str(LOGO_NL), width=Cm(6))
para(
    "Naibunga Lower Conservancy", center=True, size=24
).paragraph_format.space_before = Cm(1.5)
para("Conservancy Management Report", center=True, size=18, bold=True)
para("{{ report_date }}", center=True, size=14)
para("Prepared by: {{ prepared_by|e }}", center=True, size=11)
doc.add_page_break()

# ---------------------------------------------------------------- about
doc.add_heading("About this report", level=1)
bullets(
    [
        "Source: patrols and field reports recorded by Naibunga Lower "
        "Conservancy in EarthRanger, for the dates on the cover. Each section "
        "opens with headline figures for the whole period, then a month-by-month "
        "table when the period spans more than one month.",
        "Which month: a report counts in the month the incident happened, "
        "using the form's own incident date where it has one (Human Injury, "
        "Crop and Infrastructure Damage, Poisoning, Arrest, Contact) and the "
        "EarthRanger time otherwise. A patrol counts in the month it started; "
        "one that started before the period counts from the first day.",
        "Patrol time: each patrol counts for at most its first 14 hours -- "
        "its time, its distance and its track alike -- because patrols left "
        "open in EarthRanger keep running for days. GPS errors and gaps in a "
        "track are left out by the trajectory filter set when the report is "
        "run. See Section 1.",
        "Not counted: device check-ins (Silent Source), patrol details "
        "reports, meeting and test forms, the Livestock Household Survey, and old records that "
        "were copied onto the current forms (the copy is counted, once). "
        "Reports and patrols whose title marks them for deletion are left out "
        "entirely; Section 9 gives the number.",
        "Old forms: reports made on the earlier Ranger Basic forms are shown "
        "under the current form's name. Some were never copied across because "
        "they were empty; they are counted and flagged in Section 9.",
        "Blanks: 'Not recorded' means the field was left empty on the form. "
        "'No patrol details' means none were recorded for the patrol: they "
        "were first recorded on 25 April 2026, and since 18 November 2026 are "
        "entered on the patrol itself.",
        "Maps: every map shows the whole conservancy, outlined, and the area "
        "around it at the same scale, so maps can be compared month to month. "
        "Points recorded at 0,0 or outside East Africa are left off the maps "
        "and counted in Section 9.",
        "Personal data: no names, ID or telephone numbers, dates of birth, "
        "ethnicity or tribe appear, except ranger names in the patrol effort "
        "table. Treat this report as internal.",
    ]
)

# ---------------------------------------------------------------- 1. patrols
doc.add_heading("1. Patrol effort", level=1)
cards("period_patrol_kpis")
note(
    "Each patrol counts for at most its first 14 hours. A patrol that is not "
    "ended in EarthRanger keeps running, and without the cap a handful of "
    "patrols left open for days would outweigh every other patrol in the "
    "period. Time, distance and the track on the maps are all cut at the same "
    "point, so average speed is distance over time for the same stretch of "
    "patrol. 'Patrols capped at 14h' counts the patrols this affected. Track "
    "segments faster than 80 km/h, longer than 10 km or spanning a gap of more "
    "than an hour are treated as GPS errors and left out (these limits are set "
    "when the report is run)."
)
monthly("patrol_months", "Patrol effort by month")
single_image(
    "patrol_trend",
    "Patrol distance per month by patrol type",
    condition="patrol_months.tbl_contents and patrol_months.tbl_contents|length > 1",
)
images("patrol_maps", "Patrol tracks by patrol type")
doc.add_heading("Effort by transport, mandate and ranger", level=2)
about(
    "Transport, mandate and team are the patrol's details. Rangers first "
    "recorded them on 25 April 2026, in a report linked to the patrol, and "
    "since 18 November 2026 enter them on the patrol itself; the report reads "
    "both. Patrols before 25 April have none, which is why many show 'No "
    "patrol details'; 'Not recorded' means details were recorded but that "
    "field was left blank. Earlier records could hold several mandates, listed "
    "under the combination (e.g. 'Routine, Security')."
)
table("transport_summary", "Effort by transport type")
table("mandate_summary", "Effort by mandate")
table(
    "ranger_summary",
    "Effort by ranger (team leaders and team members)",
    footnote=(
        "Covers only patrols with patrol details, which were first recorded on "
        "25 April 2026. A patrol's distance and time are credited in full to "
        "every member of its team, so this table does not add up to the patrol "
        "totals above. Names are harmonised where the Team Leader and Team "
        "members lists in EarthRanger spell the same person differently. "
        "'Other (not on the list)' is a team leader who is not one of the three "
        "names on EarthRanger's Team Leader list (Edung Mosienye, Mika Yiangere, "
        "Henet Manyaas); the form has no field for who it was, so those patrols "
        "cannot be credited to a person."
    ),
)

doc.add_heading("Patrol coverage and encounter rates", level=2)
about(
    "Where patrols went over the whole period, on a 1 km grid, using the "
    "methods of the Ecoscope patrol-field-effort (coverage) and "
    "patrol-encounter-rate-map (encounter rates) workflows. A cell counts as "
    "patrolled when a patrol track crosses it; encounter rates divide what was "
    "recorded in each cell by the kilometres patrolled there. Both use the "
    "capped, filtered tracks described above, so a patrol left open or a GPS "
    "jump cannot add effort."
)
cards("coverage_cards")
single_image(
    "coverage_map", "Days since each 1 km cell was last patrolled (whole period)"
)
note(
    "The grid is 1 km cells cut to the conservancy boundary, so cells along "
    "the edge are smaller. Days are counted from each cell's most recent "
    "patrol to the end of the report period and grouped into five natural "
    "breaks. Grey cells were not patrolled in the period."
)
single_image(
    "wl_encounter_map",
    "Wildlife encounter rate: animals counted per km patrolled (whole period)",
)
single_image(
    "ia_encounter_map",
    "Illegal activity encounter rate: reports per km patrolled (whole period)",
)
note(
    "Only reports recorded on a patrol are counted. Wildlife sums the animals "
    "counted on visual sightings (spoor and dung add none); illegal activity "
    "counts reports. The grid covers the area patrolled, in 1 km cells. Grey "
    "cells had under 200 m of patrol effort, too little for a rate; cells "
    "with no patrol and no report are left blank."
)

# ---------------------------------------------------------------- 2. events
doc.add_heading("2. Event summary", level=1)
cards("period_event_kpis")
monthly("event_months", "Field reports by month")
images("event_type_pies", "Field reports by type")

# ---------------------------------------------------------------- 3. wildlife
doc.add_heading("3. Wildlife monitoring", level=1)
about(
    "Wildlife recorded by rangers. A visual sighting counts the animals seen; "
    "signs (spoor or dung) show a species was present without a count. "
    "Sightings filed without a sighting type are shown separately."
)
table(
    "wildlife_summary",
    "Wildlife sightings by species",
    footnote=(
        "'Unknown' is a sighting whose species was recorded as unknown. "
        "'Not recorded' is a report with no species at all -- almost all are "
        "empty legacy Ranger Basic forms that were never copied to the current "
        "form (Section 9)."
    ),
)
images("wildlife_maps", "Wildlife sightings by species")
about(
    "Priority species: one map for each species chosen when the report is run "
    "(default: Elephant, Lion, Wild Dog, Leopard). Visual sightings only; "
    "point size shows the number of animals counted, as in the legend."
)
for n in range(1, 6):
    tag(f"{{%p if ps{n}_maps and ps{n}_maps is not string %}}")
    images(f"ps{n}_maps", f"{{{{ ps{n}_name|e }}}} sightings")
    tag("{%p endif %}")

# ---------------------------------------------------------------- 4. animal health
doc.add_heading("4. Animal health", level=1)
about(
    "Wild animals found dead or reported sick or injured (the Animal Health "
    "category), and the type of death or injury recorded: poached, conflict "
    "with people, natural, problem animal control, or unknown."
)
cards("period_ah_kpis")
monthly("ah_months", "Carcasses and sick or injured animals by month")
table("ah_by_cause", "Carcasses and sick or injured animals by type of death or injury")
images(
    "ah_maps",
    "Carcass and sick or injured animal reports",
    footnote=(
        "Reports at exactly the same place are drawn as one point: the two "
        "speared giraffe reports of 27 August and 3 September 2026 share one "
        "location, so six sick or injured reports show as five points."
    ),
)

# ---------------------------------------------------------------- 5. MIKE
doc.add_heading("5. MIKE (elephant mortality)", level=1)
about(
    "Elephant carcasses, in the format of the CITES MIKE programme (Monitoring "
    "the Illegal Killing of Elephants). PIKE is the share of elephant "
    "carcasses that were illegally killed; '-' means no carcasses."
)
cards("period_mike_kpis")
monthly("mike_months", "Elephant carcasses and PIKE by month")
images(
    "mike_charts",
    "Elephant carcasses by type of death and cause",
    footnote=(
        "Inner ring: type of death. Outer ring: the cause recorded for each "
        "type, in shades of that type's colour on the carcass map. Numbers in "
        "brackets and slice sizes are carcasses."
    ),
)
table("mike_demographics", "Elephant carcasses by sex, age and condition")
images("mike_maps", "Elephant carcass locations")

# ---------------------------------------------------------------- 6. security
doc.add_heading("6. Security and illegal activity", level=1)
about(
    "Illegal activity, theft and other security incidents. Reports on the "
    "old and current Illegal Activity forms are combined. 'No details "
    "recorded' means the form was submitted empty -- the original theft "
    "reports had no theft details either, so nothing was lost in migration."
)
cards("period_sec_kpis")
images("security_pies", "Share of security incidents by type")
images("security_maps", "Security and illegal activity locations")
security_log()
note(
    "Several reports minutes apart at the same place may be one incident "
    "reported more than once; Section 9 counts these as possible duplicates "
    "to check in EarthRanger. They are not removed here."
)

# ---------------------------------------------------------------- 7. HWC
doc.add_heading("7. Human-wildlife conflict", level=1)
about(
    "Incidents where wildlife caused harm or loss, counted exactly as in the "
    "Naibunga Lower HWC report: every livestock predation report; human "
    "injuries and deaths whose cause is human-wildlife conflict; crop and "
    "infrastructure damage caused by wildlife; wildlife deaths or injuries "
    "recorded as conflict; and poisoning with the motive 'HWC retaliation'. "
    "Each qualifying report is one incident -- reports are not grouped, as "
    "none are linked into incident collections in EarthRanger."
)
cards("period_hwc_kpis")
monthly("hwc_months", "Human-wildlife conflict by month")
images("hwc_charts", "Conflict incidents by species responsible")
table("crop_damage", "Crop damage by crop and extent")
images(
    "hwc_maps",
    "Conflict incident locations",
    footnote="One point per qualifying report, every conflict type included; reports are not grouped into incidents.",
)

# ---------------------------------------------------------------- 8. human injury / death
doc.add_heading("8. Human injury and death (all causes)", level=1)
about(
    "Everyone injured or killed, whatever the cause -- accidents, security "
    "incidents and human-wildlife conflict. Section 7 counts only those "
    "caused by wildlife. Each report is one person: two reports on the same "
    "day name different victims and are two people, not a duplicate."
)
cards("period_hid_kpis")
monthly("hid_months", "People injured and killed by month")
table("hid_table", "Human injury and death incidents")
images("hid_maps", "Human injury and death locations")

# ---------------------------------------------------------------- 9. data completeness
doc.add_heading("9. Data completeness", level=1)
about(
    "Checks on how fully the data was recorded, for the whole reporting "
    "period. 'Review' marks a check with at least one record to follow up in "
    "EarthRanger; 'OK' means none were found. '% of total' is the share of "
    "the records each check looks at (patrols, field reports or sightings)."
)
table(
    "completeness",
    "Data completeness checks for the reporting period",
    footnote=(
        "Patrol details were first recorded on 25 April 2026, so patrols "
        "before then cannot have them; the second row counts only patrols "
        "since. 'Possible "
        "duplicate reports' are reports of the same type with identical form "
        "contents, less than 30 minutes and about 1 km apart. The three "
        "Wildlife Sighting rows all take their % of all Wildlife Sighting "
        "reports, current and legacy. Only visual sightings are checked for "
        "0 individuals, since spoor and dung carry no count. 'Marked for deletion' takes its "
        "% of the field reports this report would count had none been marked; "
        "an old report and its migrated copy count once."
    ),
)

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print(f"wrote {OUT}")
