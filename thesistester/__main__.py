"""Module entry point for ``python -m thesistester``.

Run-verb ``ValueError`` / ``OSError`` map to ``EX_DATAERR`` / ``EX_NOINPUT``
in ``cli.main`` (QI-06-07 / E-3). ``study`` / ``journal`` dispatch is unchanged.
"""

from __future__ import annotations

from thesistester.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
