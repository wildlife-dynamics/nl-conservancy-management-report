"""Build the Word template for the Naibunga Lower monthly management report.

Writes resources/templates/naibunga_lower_management_report_template.docx, a
docxtpl (Jinja2) template rendered by ext-custom's `create_docx` task. Values
are XML-escaped with |e because create_docx renders without autoescape (a bare
"&" or "<" would be dropped). Re-run this script (instead of hand-editing the
.docx) whenever the report layout or the context keys in spec.yaml's
`create_report` task change.

Context contract (keys must match `create_report.context.items` in spec.yaml):
  report_date   timerange  -> "{{ report_date }}"
  prepared_by   text       -> "{{ prepared_by }}"
  <table keys>  table -> {key}.col_labels / {key}.tbl_contents
                monthly tables (merge_groups=True) carry a first "Group"
                column with the month; period_* tables are ungrouped
  <image keys>  grouped image -> list of {title, image}
  <trend keys>  direct image  -> "{{ key }}" (NOT a list)

Logos are embedded from resources/images/: the Naibunga Lower logo on the
cover and on the right of the footer, the Ecoscope logo on the left.

spec.yaml pins `template_path` to a Google Drive URL (it is not a form field),
so the built .docx has to be uploaded there as a NEW VERSION of the same Drive
file, keeping the file id. Rebuild and re-upload together.

Run with any Python that has python-docx, e.g. from the inner workflow env:
    cd ecoscope-workflows-nl-conservancy-management-report-workflow
    pixi run python ../dev/build_report_template.py
"""

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
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
for level, size in ((1, 16), (2, 13), (3, 11)):
    style = doc.styles[f"Heading {level}"]
    style.font.size = Pt(size)
    style.font.color.rgb = BLACK

_table_no = 0
_fig_no = 0


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


def about(text: str) -> None:
    """A short note for the reader on what a section shows and how to read it."""
    para(text, size=9, color=GREY)


def caption(label: str, title: str, *, center: bool = False, below: bool = False):
    """'Table 3. Title' / 'Fig. 2. Title' -- bold label, plain title.

    `below=True` is for figure captions, which sit UNDER their figure.

    THE ANCHORING BUG, carried over from the HWC report's review: every caption
    used to set keep_with_next, which binds a paragraph to the one that FOLLOWS
    it. On a table caption that is right -- it keeps the caption with its
    table. On a figure caption it is exactly wrong: it bound the caption to the
    next heading and let Word break the page between the figure and its own
    caption. A figure caption needs no keep_with_next of its own, and the
    figure above it carries one instead.
    """
    p = doc.add_paragraph()
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    lab = p.add_run(label + " ")
    lab.bold = True
    lab.font.size = Pt(9)
    t = p.add_run(title)
    t.italic = True
    t.font.size = Pt(9)
    p.paragraph_format.space_before = Pt(2 if below else 8)
    p.paragraph_format.space_after = Pt(12 if below else 4)
    p.paragraph_format.keep_with_next = not below
    return p


def shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def table(key: str, title: str) -> None:
    """A captioned, dynamic-column table bound to one table context item."""
    global _table_no
    _table_no += 1
    caption(f"Table {_table_no}.", title)
    para(f"{{%p if {key}.tbl_contents %}}")
    t = doc.add_table(rows=4, cols=3)
    t.style = "Table Grid"
    header, open_row, body, close_row = t.rows
    header.cells[0].text = f"{{%tc for col in {key}.col_labels %}}"
    header.cells[1].text = "{{ col|e }}"
    header.cells[2].text = "{%tc endfor %}"
    for cell in header.cells:  # the middle cell is the one repeated
        shade(cell, HEADER_FILL)
        for p in cell.paragraphs:
            for run in p.runs:
                run.bold = True
                run.font.color.rgb = WHITE
    open_row.cells[0].text = f"{{%tr for row in {key}.tbl_contents %}}"
    body.cells[0].text = "{%tc for col in row.cols %}"
    body.cells[1].text = "{{ col|e }}"
    body.cells[2].text = "{%tc endfor %}"
    close_row.cells[0].text = "{%tr endfor %}"
    para("{%p else %}")
    para("No records for this period.", italic=True, size=9)
    para("{%p endif %}")


def images(key: str, title: str) -> None:
    """A grouped image item: one figure per group, each with its own caption.

    SUB-NUMBERED, and it has to be. This renders once per group, so a single
    'Fig. 5.' would be printed on every month's copy of the same chart and the
    numbering would not identify anything. `{slot}.{{ loop.index }}` gives
    Fig. 5.1, Fig. 5.2 and so on, with the group's own label (the month) in the
    caption text beside it.

    The slot number is fixed at build time and the sub-number comes from
    docxtpl's loop, so the numbering survives the grouping being a form field
    now: one view gives 5.1, twelve views give 5.1 to 5.12.
    """
    global _fig_no
    _fig_no += 1
    para(f"{{%p for item in {key} %}}")
    img = para("{{ item.image }}", center=True)
    img.paragraph_format.keep_with_next = True
    img.paragraph_format.space_after = Pt(0)
    caption(
        f"Fig. {_fig_no}.{{{{ loop.index }}}}",
        f"{title}, {{{{ item.title|e }}}}",
        center=True,
        below=True,
    )
    para("{%p endfor %}")


def single_image(key: str, title: str) -> None:
    """An UNGROUPED image item: create_docx passes one InlineImage, not a list.

    Only the month-on-month charts qualify -- they span the whole range by
    design and are built from the indexed frame, not the grouped one.
    """
    global _fig_no
    _fig_no += 1
    img = para(f"{{{{ {key} }}}}", center=True)
    img.paragraph_format.keep_with_next = True
    img.paragraph_format.space_after = Pt(0)
    caption(f"Fig. {_fig_no}.", title, center=True, below=True)


# ---------------------------------------------------------------- footer
footer = section.footer.paragraphs[0]
footer.style = doc.styles["Normal"]  # the Footer style's centre tab would catch the tab
footer.paragraph_format.tab_stops.add_tab_stop(TEXT_WIDTH, WD_TAB_ALIGNMENT.RIGHT)
footer.add_run().add_picture(str(LOGO_ECO), height=Cm(0.8))
footer.add_run("\t")
footer.add_run().add_picture(str(LOGO_NL), height=Cm(1.3))

# ---------------------------------------------------------------- cover
logo = doc.add_paragraph()
logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
logo.paragraph_format.space_before = Cm(3)
logo.add_run().add_picture(str(LOGO_NL), width=Cm(6))
para(
    "Naibunga Lower Conservancy", center=True, size=26
).paragraph_format.space_before = Cm(1.5)
para("Monthly Management Report", center=True, size=18)
para("{{ report_date }}", center=True, size=14)
para("Prepared by: {{ prepared_by|e }}", center=True, size=11)
doc.add_page_break()

# ---------------------------------------------------------------- about
# The MRD's report-wide rules, stated once so a reader can interpret every
# figure that follows without having to ask how it was counted.
doc.add_heading("About this report", level=1)
about(
    "Patrol effort and field reports recorded by Naibunga Lower Conservancy in "
    "EarthRanger. Each section gives the figures for the whole period first, "
    "then month by month."
)
about(
    "Which month a record falls in. Where a form asks when something actually "
    "happened, that date is used rather than the date it was typed in: Human "
    "Injury, Crop damage and Infrastructure damage use Incident date & time, "
    "Poisoning uses Date & time, Arrest uses Arrest time, and Contact uses "
    "Contact time. Everything else uses the EarthRanger event time. A patrol "
    "counts in the month it started."
)
about(
    "What is left out. Patrol logistics forms (Patrol Info, Meeting Report) and "
    "the Livestock Household Survey are excluded from every event total and "
    "chart, so each field observation is counted once and paperwork is not "
    "counted as activity."
)
about(
    "Personal data. Names, ID numbers, telephone numbers, dates of birth, "
    "ethnicity and tribe do not appear anywhere in this report. Each detail "
    "table uses a fixed list of fields for its event type. Ranger names appear "
    "in the patrol effort table, which is the purpose of that table -- treat "
    "this report as internal."
)
about(
    "Blanks. 'Not recorded' and 'Unknown' mean the field was left empty on the "
    "form, not that something was investigated and came back unknown. Section "
    "10 counts how often that happened, and is worth reading before the rest."
)
doc.add_page_break()

# ---------------------------------------------------------------- 1. patrols
doc.add_heading("1. Patrol effort", level=1)
about(
    "How much patrolling was done: the number of patrols, time spent and "
    "distance covered, first for the whole period and then month by month. "
    "A patrol is counted in the month it started, so a patrol begun just before "
    "the period appears under that earlier month. Patrols left open for days "
    "raise the time on patrol and lower the average speed; Section 10 counts them."
)
table("period_patrol_kpis", "Patrol effort for the whole period")
table("patrol_kpis", "Patrol effort by month")
images("patrol_maps", "Patrol tracks by patrol type")
about(
    "The tables below split the same effort by how rangers travelled, by the "
    "purpose of the patrol, and by ranger. A patrol with more than one mandate "
    "is listed under the combination. 'No Patrol Info' means no Patrol Info "
    "form was filled in for the patrol; 'Not recorded' means the form was filled "
    "in but that field was left blank."
)
table("transport_summary", "Effort by transport type")
table("mandate_summary", "Effort by mandate")
table("ranger_summary", "Effort by ranger (team leaders and team members)")

# ---------------------------------------------------------------- 2. events
doc.add_heading("2. Event summary", level=1)
about(
    "Field reports submitted by rangers, in total and by type. Device check-ins "
    "(Silent Source), patrol logistics (Patrol Info, Meeting Report), test forms "
    "and old records that were copied onto new forms are not counted, so each "
    "observation is counted once."
)
table("period_event_kpis", "Field reports for the whole period")
table("event_kpis", "Field reports by month")
images("event_type_pies", "Share of field reports by type")

# ---------------------------------------------------------------- 3. wildlife
doc.add_heading("3. Wildlife monitoring", level=1)
about(
    "Wildlife recorded by rangers, by species. A visual sighting records how "
    "many animals were seen; signs (spoor or dung) show that a species was "
    "present without a count. On the maps, larger symbols mean more individuals."
)
table("wildlife_summary", "Wildlife sightings by species, by month")
images("wildlife_maps", "Wildlife sightings")

# ---------------------------------------------------------------- 4. animal health
doc.add_heading("4. Animal health", level=1)
about(
    "Wild animals found dead or reported sick or injured, and the type of death "
    "or injury recorded: poached, conflict with people, natural, problem animal "
    "control, or unknown."
)
table("period_ah_kpis", "Carcasses and sick or injured animals for the whole period")
table("ah_kpis", "Carcasses and sick or injured animals by month")
table("ah_by_cause", "Carcasses and sick or injured animals by type, by month")
images("ah_maps", "Carcass and sick or injured animal reports")

# ---------------------------------------------------------------- 5. MIKE
doc.add_heading("5. MIKE (elephant mortality)", level=1)
about(
    "Elephant carcasses, reported in the format of the CITES MIKE programme "
    "(Monitoring the Illegal Killing of Elephants). PIKE is the share of "
    "elephant carcasses that were illegally killed; it is left blank in a month "
    "with no carcasses."
)
table("period_mike_kpis", "Elephant carcasses and PIKE for the whole period")
table("mike_kpis", "Elephant carcasses and PIKE by month")
images("mike_charts", "Elephant carcasses by cause and type of death")
table("mike_demographics", "Elephant carcasses by sex, age and condition")
images("mike_maps", "Elephant carcass locations")

# ---------------------------------------------------------------- 6. security
doc.add_heading("6. Security and illegal activity", level=1)
about(
    "Illegal activity, theft and other security incidents, with a log of each "
    "incident. 'Not recorded' in the log means no location or no details were "
    "captured for that incident."
)
images("security_pies", "Share of security incidents by type")
table("security_events", "Security incident log")

# ---------------------------------------------------------------- 7. HWC
doc.add_heading("7. Human-wildlife conflict", level=1)
about(
    "Incidents where wildlife caused harm or loss to people, livestock, crops or "
    "property, counted the same way as in the Naibunga Lower HWC report: every "
    "livestock predation report, human injuries and deaths caused by wildlife, "
    "crop and infrastructure damage caused by wildlife, wildlife deaths or "
    "injuries recorded as conflict, and poisoning in retaliation."
)
table("period_hwc_kpis", "Human-wildlife conflict for the whole period")
table("hwc_kpis", "Human-wildlife conflict by month")
images("hwc_charts", "Conflict incidents by species responsible")
table("crop_damage", "Crop damage by crop and extent")
images("hwc_maps", "Conflict incident locations")

# ---------------------------------------------------------------- 8. human injury / death
doc.add_heading("8. Human injury and death (all causes)", level=1)
about(
    "All people injured or killed, whatever the cause, including accidents and "
    "security incidents. Section 7 counts only those caused by wildlife. The "
    "incident list gives the date, cause and, where wildlife was involved, the "
    "species responsible."
)
table("period_hid_kpis", "People injured and killed for the whole period")
table("hid_kpis", "People injured and killed by month")
table("hid_table", "Human injury and death incidents")
images("hid_maps", "Human injury and death locations")

# ---------------------------------------------------------------- 9. trends
doc.add_heading("9. Month-on-month comparison", level=1)
about(
    "How field reporting and patrolling changed from month to month across the "
    "whole period."
)
single_image("events_trend", "Field reports per month by category")
single_image("patrol_trend", "Patrol distance per month by patrol type")

# ---------------------------------------------------------------- 10. data completeness
doc.add_heading("10. Data completeness", level=1)
about(
    "Checks on how fully the data was recorded each month, such as patrols "
    "without Patrol Info, patrols left open for more than 14 hours, or sightings "
    "with no count. 'Review' marks a check with at least one record to follow up; "
    "'OK' means none were found."
)
table("completeness", "Data completeness checks by month")

# ---------------------------------------------------------------- notes
# Carried over from the HWC report's review: "Where values are 'Not recorded'
# - is this due to legacy records not being carried over properly? I think we
# should add a footnote on this." Stated as what the data model shows rather
# than as a diagnosis, because the obvious reading of a column full of
# "Not recorded" is that something was lost on the way in.
doc.add_heading("About the figures in this report", level=2)
about(
    "'Not recorded' means the field was left blank on the report, not that "
    "something was investigated and came back unknown. It appears for two "
    "reasons. Reports made before October 2026 were recorded on earlier forms "
    "that had no equivalent field, so there was nothing to carry across when "
    "they were migrated to the current event types. Reports made since are on "
    "the current forms, where these fields are optional and are sometimes "
    "skipped. Neither case means a record was lost: the event itself, its date "
    "and its location are intact, and it is counted in every total."
)
about(
    "'No Patrol Info' in the patrol tables is different again: the patrol was "
    "recorded but no Patrol Info form was filed against it, so its mandate, "
    "transport and station are unknown rather than blank. The data "
    "completeness table counts these."
)
about(
    "Figures are numbered in the order they appear. Where a figure is drawn "
    "once per period in the report's grouping, each one carries a sub-number "
    "(Fig. 5.1, Fig. 5.2) and names its period in the caption. A figure with "
    "no data is shown as an empty panel rather than removed, so the numbering "
    "is stable from one month's report to the next."
)

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print(f"wrote {OUT}  ({_table_no} tables, {_fig_no} figures)")
