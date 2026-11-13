"""The GitHub Pages site builds from the example organizations without leaking local paths."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("site_build", ROOT / "site" / "build.py")
site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(site)


def test_site_builds(tmp_path):
    out = tmp_path / "_site"
    demos = site.build(out)

    index = (out / "index.html").read_text(encoding="utf-8")
    assert [d["slug"] for d in demos] == ["platform-team", "small-team"]
    for demo in demos:
        report = (out / demo["href"]).read_text(encoding="utf-8")
        assert f'aria-label="Score {demo["score"]} of 100"' in report
        assert f'href="{demo["href"]}"' in index
        assert f"<b>{demo['score']}</b>" in index
        assert str(ROOT) not in report and str(tmp_path) not in report
    assert (out / "social-preview.png").stat().st_size > 0
    assert (out / ".nojekyll").exists()
    assert 'property="og:image"' in index
