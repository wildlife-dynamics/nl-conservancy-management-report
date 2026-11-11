"""Fail when the Word template on Google Drive is not the one in this repo.

WHY THIS EXISTS
---------------
`spec.yaml` pins `template_path` to a Google Drive URL, so a workflow run
fetches the template from Drive -- NOT from `resources/templates/`. The repo
copy is only the editable source and what the test cases point at. Nothing
keeps the two in step.

On 9 Nov 2026 that gap produced a report that looked finished and was not.
`dev/build_report_template.py` had been extended with a tree-crop table, the
retaliation-evidence tables, an incident timeline and a data-completeness
section; the repo .docx was rebuilt and had all 22 tables; the Drive copy was
still the previous build with 18. The run used Drive. The dashboard showed 36
widgets, the report stopped at section 11, and nothing anywhere errored --
`create_docx` renders whatever tags the template happens to contain and
silently drops the context it was handed for tags that are absent.

Every check in `lint_spec.py` and `check_sql_strict.py` passed throughout.
They are offline by design and read the spec, so neither can see Drive.

WHAT IT CHECKS
--------------
That the bytes Drive serves for the pinned URL are byte-identical to
`resources/templates/naibunga_lower_management_report_template.docx`.

Credentials are deliberately omitted, which is the state the workflow runner
is in -- so this also re-verifies the `anyoneWithLink` share setting and that
Drive still holds a real .docx blob rather than a converted Google Doc, the
two other ways the pin fails.

    python3 dev/check_template_sync.py

Exit 0 identical, 1 drifted or unreachable. Needs network; it is the one dev
check here that does, so it is not wired into the offline pre-compile pair.
Run it before a release and after any template rebuild.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec.yaml"
LOCAL = (
    ROOT / "resources" / "templates" / "naibunga_lower_management_report_template.docx"
)

# Read the URL out of the spec rather than restating it: the point of the check
# is that the thing the RUN uses matches the repo, so it has to read the same
# pin the run reads. A second copy here could itself drift.
URL_RE = re.compile(r"https://drive\.google\.com/uc\?export=download&id=[A-Za-z0-9_-]+")

DOCX_MAGIC = b"PK\x03\x04"


def _check_keys() -> int:
    """Does the built template only use context keys the spec supplies?

    Runs BEFORE the network check, because this is the failure that costs an
    upload round-trip. `create_docx` renders with Jinja's default undefined, so
    a template key the spec does not supply is not a gap in the document -- it
    aborts the whole task:

        Task instance 'create_report' raised UndefinedError('hwc_kpis' is undefined)

    and the run produces no report at all. That is exactly what happened when
    the context keys were renamed in spec.yaml and the .docx had not been
    rebuilt: the stale template still asked for `hwc_kpis`, `resp_counts` and
    `completeness`, and all three test cases died at the last task.

    The reverse direction is only a warning: a key the spec supplies but the
    template ignores wastes a render and breaks nothing.
    """
    import re
    import zipfile

    with zipfile.ZipFile(LOCAL) as z:
        text = re.sub(r"<[^>]+>", "", z.read("word/document.xml").decode("utf8"))
    used = set(re.findall(r"\{\{\s*([a-z_]+)", text)) | set(
        re.findall(r"\{%\w*\s*if\s+([a-z_]+)", text)
    )
    # loop variables are bound inside the template, not supplied by the spec
    used -= {"item", "col", "row", "loop"}
    supplied = set(re.findall(r"key: ([a-z_]+)", SPEC.read_text()))

    missing = sorted(used - supplied)
    unused = sorted(supplied - used)
    if missing:
        print("FAIL  the built template uses context keys spec.yaml does not supply:")
        for k in missing:
            print(f"        {k}")
        print(
            "\n      create_docx would abort with UndefinedError and write no report."
        )
        print("      Rebuild the template, which is almost always the cause:")
        print(
            "        cd <workflow dir> && pixi run python ../dev/build_report_template.py"
        )
        return 1
    if unused:
        print(
            f"warn  spec supplies {len(unused)} key(s) the template never uses: {', '.join(unused)}"
        )
    print(f"  keys      {len(used)} used, all supplied by spec.yaml")
    return 0


def main() -> int:
    if not LOCAL.exists():
        print(f"FAIL  no local template at {LOCAL.relative_to(ROOT)}")
        print(
            "      build it: cd <workflow dir> && pixi run python ../dev/build_report_template.py"
        )
        return 1

    if _check_keys():
        return 1

    urls = sorted(set(URL_RE.findall(SPEC.read_text())))
    if len(urls) != 1:
        print(
            f"FAIL  expected exactly one Drive template URL in spec.yaml, found {len(urls)}: {urls}"
        )
        return 1
    url = urls[0]

    local_bytes = LOCAL.read_bytes()
    local_sha = hashlib.sha256(local_bytes).hexdigest()

    try:
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - pinned https Drive URL
            remote_bytes = resp.read()
            status = resp.status
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"FAIL  could not fetch {url}\n      {e}")
        return 1

    remote_sha = hashlib.sha256(remote_bytes).hexdigest()

    print(f"  spec pin   {url}")
    print(f"  local      {len(local_bytes):>7} bytes  sha256 {local_sha[:12]}")
    print(
        f"  drive      {len(remote_bytes):>7} bytes  sha256 {remote_sha[:12]}  HTTP {status}"
    )

    if not remote_bytes.startswith(DOCX_MAGIC):  # noqa: SIM102 - ordered checks
        # Drive serves an HTML interstitial for large files and for files it has
        # converted to a Google Doc. Either way docxtpl's table tags are gone.
        head = remote_bytes[:120].decode("utf-8", "replace")
        print("\nFAIL  Drive did not return a .docx blob. First bytes:")
        print(f"      {head!r}")
        print("      Check the share setting is anyoneWithLink, and that the file is")
        print("      stored as .docx rather than converted to a Google Doc.")
        return 1

    if local_sha == remote_sha:
        print("\nOK    Drive and the repo serve identical bytes.")
        return 0

    # Bytes differ. That is NOT conclusive on its own: a .docx is a zip, and
    # uploading one through Drive (or opening and saving it in Word) can
    # repack the archive -- different member order, timestamps, compression
    # levels -- while `word/document.xml` is unchanged. The first upload after
    # this check was written came back 106 bytes larger for exactly that kind
    # of reason. Comparing bytes alone would cry wolf on every upload.
    #
    # `word/document.xml` is the part that decides which docxtpl tags exist
    # and therefore which sections render, so that is what gets compared.
    local_doc = _document_xml(local_bytes, "local")
    remote_doc = _document_xml(remote_bytes, "drive")
    if local_doc is None or remote_doc is None:
        return 1

    if local_doc == remote_doc:
        print("\nOK    Drive's zip is packed differently but word/document.xml is")
        print("      identical, so the same template renders. No action needed.")
        return 0

    print("\nFAIL  Drive is serving a DIFFERENT template from the one in this repo.")
    print(
        f"      word/document.xml: local {len(local_doc)} bytes, drive {len(remote_doc)} bytes"
    )
    _report_tag_drift(local_doc, remote_doc)
    print("\n      A run will use Drive's. Rebuild and re-upload over the pinned id:")
    print(
        "        pixi run python ../dev/build_report_template.py   # from the workflow dir"
    )
    print(f"        upload {LOCAL.relative_to(ROOT)} over {url.rsplit('=', 1)[1]}")
    return 1


def _document_xml(blob: bytes, label: str) -> bytes | None:
    """Return `word/document.xml` from a .docx blob, or None after reporting."""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            return z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        print(f"\nFAIL  {label} copy is not a readable .docx: {e}")
        return None


def _report_tag_drift(local_doc: bytes, remote_doc: bytes) -> None:
    """Name the docxtpl keys that differ, which is the actionable difference.

    A section renders only if its tag is in the template, so a missing key
    here is precisely a section that will be absent from the report.
    """
    tag = re.compile(
        rb"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)|\{%\s*\w+\s+for\s+\w+\s+in\s+([A-Za-z_][A-Za-z0-9_]*)"
    )

    def keys(doc: bytes) -> set[str]:
        found = set()
        for m in tag.finditer(doc):
            name = m.group(1) or m.group(2)
            if name:
                found.add(name.decode())
        return found

    local_keys, remote_keys = keys(local_doc), keys(remote_doc)
    missing = sorted(local_keys - remote_keys)
    extra = sorted(remote_keys - local_keys)
    if missing:
        print(f"      in repo but NOT on Drive ({len(missing)}): {', '.join(missing)}")
        print("        -> these sections will be MISSING from the generated report")
    if extra:
        print(f"      on Drive but not in repo ({len(extra)}): {', '.join(extra)}")
    if not missing and not extra:
        print("      same tag set; the difference is wording or formatting only")


if __name__ == "__main__":
    sys.exit(main())
