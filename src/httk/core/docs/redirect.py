#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Generate the relative root redirect for a versioned documentation site."""

from html import escape
from pathlib import Path

__all__ = ["root_redirect_html", "write_root_redirect"]


def root_redirect_html(target_relative_path: str) -> str:
    """Return a complete HTML5 document redirecting to a relative site path.

    :param target_relative_path: Relative path receiving the redirect.
    :return: HTML redirect document.
    """

    target = escape(target_relative_path, quote=True)
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0; url={target}">\n'
        "<title>httk documentation</title>\n</head>\n<body>\n"
        f'<p>Redirecting to <a href="{target}">the httk documentation</a>.</p>\n'
        "</body>\n</html>\n"
    )


def write_root_redirect(site_root: str | Path, target: str) -> None:
    """Write ``index.html`` at *site_root* with a relative redirect to *target*.

    :param site_root: Site root receiving the redirect file.
    :param target: Relative path receiving the redirect.
    """

    root = Path(site_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(root_redirect_html(target), encoding="utf-8")
