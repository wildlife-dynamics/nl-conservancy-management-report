"""Force ruamel.yaml onto its pure-Python emitter.

THIRD workaround for the same class of problem: wt-compiler 0.8.3 meeting an
environment that pixi assembled differently from the one it was tested on.

The failure:

    Error: a bytes-like object is required, not 'str'

and a 0-byte VERSION.yaml in the generated directory, with nothing written
after it. wt_compiler/artifacts.py does

    yaml = ruamel.yaml.YAML(typ="safe")          # module level
    ...
    def dump(self, dst):                          # VersionYaml.dump
        with dst.open("wb") as f:
            yaml.dump(self.model_dump(), f)

`YAML(typ="safe")` selects ruamel's C emitter whenever `ruamel.yaml.clib` is
installed — and conda pulls clib in as a dependency of ruamel.yaml, so it
always is here. The C emitter cannot write to a binary stream; the pure-Python
one can. Reproduced directly:

    YAML(typ="safe")             -> CEmitter -> TypeError on a "wb" stream
    YAML(typ="safe", pure=True)  -> Emitter  -> writes b'{MAJ: 0, MIN: 0, …}'

So this is wt-compiler's bug — `open("wb")` plus an emitter that may be the C
one — and it only shows up where clib is present. We cannot pass `pure=True`
from outside, so this file defaults it on for every YAML() in the process.

sitecustomize.py is imported automatically by CPython at startup when it is on
PYTHONPATH, which pixi.toml's [activation.env] arranges. It therefore applies
to `pixi run` locally and in CI, and to nothing outside this repo.

DELETE THIS, dev/shims/ruff/ and the PYTHONPATH line in pixi.toml when
wt-compiler is fixed. Three shims for one compiler version is two too many.
"""

try:
    import ruamel.yaml.main as _ruamel_main
except Exception:  # pragma: no cover - ruamel absent is not our problem
    pass
else:
    _original_init = _ruamel_main.YAML.__init__

    def _pure_by_default(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        kwargs.setdefault("pure", True)
        _original_init(self, *args, **kwargs)

    # Idempotent: re-importing sitecustomize must not stack wrappers.
    if not getattr(_ruamel_main.YAML.__init__, "_wt_pure_shim", False):
        _pure_by_default._wt_pure_shim = True
        _ruamel_main.YAML.__init__ = _pure_by_default
