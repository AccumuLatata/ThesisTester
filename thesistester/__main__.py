"""Module entry point for ``python -m thesistester``.

Run-verb ``OSError`` (including ``ValueError`` whose ``__cause__`` is
``OSError``, e.g. missing experiment file) maps to ``EX_NOINPUT``.
Other ``ValueError`` maps to ``EX_DATAERR`` (QI-06-07 / E-3).
``study`` / ``journal`` dispatch is unchanged.
"""

from __future__ import annotations

from thesistester.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
