"""
Build the GitHub Pages site: a landing page and live HTML reports of the example organizations.

    python site/build.py --out _site

Reports are produced by the `hrg` command line, exactly as users get them. Only fictional
example organizations are published.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

from human_risk_graph import __version__
from human_risk_graph.html_report import GRADE_COLORS

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/LF3551/human-risk-graph"
SITE_URL = "https://lf3551.github.io/human-risk-graph/"
DEMOS = [
    {
        "slug": "platform-team",
        "file": ROOT / "data" / "example_organization.json",
        "title": "Platform and security team",
        "text": "Ten people across SRE, security, platform and compliance, with approvals, "
        "escalations and emergency bypasses.",
    },
    {
        "slug": "small-team",
        "file": ROOT / "examples" / "organization.yaml",
        "title": "Small team",
        "text": "Five people where one head of platform approves almost everything and a "
        "bypass skips her review.",
    },
    {
        "slug": "critical-functions",
        "file": ROOT / "examples" / "functions.yaml",
        "title": "Critical functions (model hrg-3)",
        "text": "Merge, release, database restore and key rotation: who can perform each, "
        "what stops without one person, who can complete it alone, and who has gone inactive.",
        "model": "hrg-3",
    },
]


def _hrg(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "human_risk_graph.cli", *args], check=True, cwd=ROOT)


def build_report(demo: dict, out: Path) -> dict:
    """Write the HTML report for a demo and return its summary for the landing page."""
    report = (out / "demo" / f"{demo['slug']}.html").resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    source = demo["file"].relative_to(ROOT).as_posix()
    common = ("--no-visualize", "--quiet", "--model", demo.get("model", "hrg-2"))
    _hrg("analyze", source, "--format", "html", "--output", str(report), *common)
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "report.json"
        _hrg("analyze", source, "--format", "json", "--output", str(data), *common)
        result = json.loads(data.read_text(encoding="utf-8"))
    findings = [f for f in result["findings"] if not f.get("accepted")]
    return {
        **demo,
        "href": f"demo/{demo['slug']}.html",
        "score": result["results"]["score"],
        "grade": result["results"]["grade"],
        "risk_level": result["results"]["risk_level"],
        "people": result["metadata"]["organization_size"],
        "dependencies": result["metadata"]["dependencies_count"],
        "errors": sum(1 for f in findings if f["level"] == "error"),
        "warnings": sum(1 for f in findings if f["level"] != "error"),
        "top_fix": (result["fix_plan"] or [{}])[0].get("title"),
    }


def _card(demo: dict) -> str:
    color = GRADE_COLORS.get(demo["grade"], "#334155")
    fix = f'<p class="fix">Top fix: {escape(demo["top_fix"])}</p>' if demo.get("top_fix") else ""
    return f"""<a class="card" href="{escape(demo['href'])}">
  <div class="grade" style="--grade:{color}"><b>{demo['score']}</b><span>{escape(demo['grade'])}</span></div>
  <div>
    <h3>{escape(demo['title'])}</h3>
    <p>{escape(demo['text'])}</p>
    <p class="meta">{demo['people']} people · {demo['dependencies']} dependencies ·
      {escape(demo['risk_level'])} risk · {demo['errors']} errors · {demo['warnings']} warnings</p>
    {fix}
    <span class="open">Open the report →</span>
  </div>
</a>"""


def landing(demos: list) -> str:
    cards = "\n".join(_card(d) for d in demos)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Human Risk Graph: find the people your security depends on</title>
<meta name="description" content="Open-source tool that finds single points of failure, approval concentration and control bypasses in who approves what. Live example reports.">
<meta property="og:title" content="Human Risk Graph">
<meta property="og:description" content="Find the people your security depends on: single points of failure, approval concentration and control bypasses.">
<meta property="og:image" content="{SITE_URL}social-preview.png">
<meta property="og:url" content="{SITE_URL}">
<meta name="twitter:card" content="summary_large_image">
<style>
:root {{ --bg:#f8fafc; --fg:#0f172a; --muted:#475569; --card:#fff; --line:#e2e8f0; --accent:#4f46e5; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0b1120; --fg:#e2e8f0; --muted:#94a3b8; --card:#111827; --line:#1f2937; --accent:#818cf8; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--fg); }}
main {{ max-width: 960px; margin: 0 auto; padding: 48px 20px 64px; }}
h1 {{ font-size: clamp(30px, 5vw, 44px); line-height: 1.15; margin: 0 0 12px; }}
h2 {{ font-size: 22px; margin: 44px 0 14px; }}
h3 {{ margin: 0 0 6px; font-size: 19px; }}
p {{ margin: 0 0 10px; }}
a {{ color: var(--accent); }}
.lead {{ font-size: 19px; color: var(--muted); max-width: 720px; }}
.links {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:20px; }}
.links a {{ text-decoration:none; border:1px solid var(--line); background:var(--card); padding:8px 14px; border-radius:999px; font-weight:600; }}
.cards {{ display:grid; gap:16px; }}
.card {{ display:grid; grid-template-columns: 96px 1fr; gap:18px; align-items:start; padding:20px; border:1px solid var(--line); border-radius:14px; background:var(--card); color:inherit; text-decoration:none; transition: border-color .15s; }}
.card:hover, .card:focus-visible {{ border-color: var(--accent); }}
.grade {{ width:96px; height:96px; border-radius:50%; border:8px solid var(--grade); display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.grade b {{ font-size:28px; line-height:1; }}
.grade span {{ font-weight:700; color:var(--grade); }}
.meta, .fix {{ color: var(--muted); font-size: 14px; }}
.open {{ font-weight: 600; color: var(--accent); }}
pre {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; overflow-x:auto; font-size:14px; }}
ul {{ padding-left: 20px; }}
footer {{ margin-top: 48px; color: var(--muted); font-size: 14px; }}
@media (max-width: 560px) {{ .card {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<main>
<h1>Find the people your security depends on</h1>
<p class="lead">Human Risk Graph models who approves, who escalates and who can override a
control, then shows the single points of failure, how concentrated approval authority is,
which controls can be bypassed, and the changes that help most.</p>
<div class="links">
  <a href="{REPO}">GitHub</a>
  <a href="https://github.com/marketplace/actions/human-risk-graph">GitHub Action</a>
  <a href="https://pypi.org/project/human-risk-graph/">PyPI</a>
  <a href="{REPO}/blob/main/docs/model.md">How the score works</a>
  <a href="{REPO}/blob/main/docs/validation-hrg3.md">Validation</a>
  <a href="{REPO}/blob/main/docs/privacy.md">Privacy &amp; GDPR</a>
  <a href="{REPO}/blob/main/docs/benchmark.md">Benchmark</a>
</div>

<h2>Live example reports</h2>
<p class="meta">Fictional organizations, analyzed by human-risk-graph {escape(__version__)}.
Each report is a single offline HTML file: open the map, click a person, print it as PDF.</p>
<div class="cards">
{cards}
</div>

<h2>Try it on your organization</h2>
<pre><code>pip install human-risk-graph
hrg analyze org.yaml                       # describe people and dependencies in YAML
hrg scan github my-org/my-repo             # or draft them from a GitHub repository
hrg scan github --org my-org               # or from a whole GitHub organization
hrg analyze my-org-org.yaml --model hrg-3  # merge, release, deploy: two-person rule, inactive people
hrg analyze org.yaml --pseudonymize        # reports without names (GDPR)</code></pre>
<p>In CI, with findings in code scanning and a job summary on every pull request:</p>
<pre><code>- uses: LF3551/human-risk-graph@v{escape(__version__)}
  with:
    file: org.yaml
    min-score: 70</code></pre>

<h2>What it is not</h2>
<ul>
  <li>Not a code-ownership tool: it models authority (who may approve), not who knows the code.</li>
  <li>Not a probability of an incident: the score is a structural index; read the findings.</li>
  <li>Not for judging people: it measures the organization; reports can use keyed pseudonyms
    instead of names (<a href="{REPO}/blob/main/docs/privacy.md">privacy</a>).</li>
  <li>Nothing leaves your machine: the CLI and the action run locally or in your own CI.</li>
</ul>

<footer>Apache-2.0 · human-risk-graph {escape(__version__)} ·
  <a href="{REPO}">source</a> · <a href="{REPO}/issues">issues</a></footer>
</main>
</body>
</html>
"""


def build(out: Path) -> list:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    demos = [build_report(demo, out) for demo in DEMOS]
    (out / "index.html").write_text(landing(demos), encoding="utf-8")
    shutil.copy(ROOT / "docs" / "figures" / "social-preview.png", out / "social-preview.png")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return demos


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the GitHub Pages site.")
    parser.add_argument("--out", type=Path, default=ROOT / "_site")
    args = parser.parse_args(argv)
    for demo in build(args.out):
        print(f"{demo['href']}: {demo['score']}/100 {demo['grade']}")
    print(f"Site written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
