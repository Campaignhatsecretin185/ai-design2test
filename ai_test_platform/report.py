from __future__ import annotations

from html import escape
from typing import Any


def build_report_html(run: dict[str, Any]) -> str:
    summary = run.get("summary", {})
    results = run.get("results", [])
    rows = "\n".join(
        f"""
        <tr>
          <td>#{result['test_case_id']}</td>
          <td>{escape(result['title'])}</td>
          <td>{escape(result['feature'])}</td>
          <td>{escape(result['priority'])}</td>
          <td><span class="status {escape(result['status'])}">{escape(result['status'])}</span></td>
          <td>{result['duration_ms']}ms</td>
          <td><pre>{escape(result['output'][:1200])}</pre></td>
        </tr>
        """
        for result in results
    )
    release_advice = "Release recommended" if summary.get("failed", 0) == 0 and summary.get("blocked", 0) == 0 else "Release not recommended"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Test Report - Run #{run['id']}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17202a; }}
    h1 {{ margin-bottom: 4px; }}
    .meta {{ color: #5f6b7a; margin-bottom: 24px; }}
    .summary {{ display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 12px; margin: 24px 0; }}
    .metric {{ border: 1px solid #d8dee8; border-radius: 8px; padding: 14px; background: #fbfcfe; }}
    .metric strong {{ display: block; font-size: 26px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #e5e9f0; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f5f7fb; }}
    pre {{ max-width: 520px; white-space: pre-wrap; margin: 0; font-size: 12px; }}
    .status {{ padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
    .passed {{ background: #e6f6ed; color: #116329; }}
    .failed {{ background: #ffebe9; color: #82071e; }}
    .blocked {{ background: #fff8c5; color: #7d4e00; }}
  </style>
</head>
<body>
  <h1>Test Report Run #{run['id']}</h1>
  <div class="meta">{escape(run['name'])} · {escape(run['mode'])} · {escape(run['status'])} · {escape(run['created_at'])}</div>
  <h2>Release Decision: {release_advice}</h2>
  <div class="summary">
    <div class="metric"><span>Total</span><strong>{summary.get('total', 0)}</strong></div>
    <div class="metric"><span>Passed</span><strong>{summary.get('passed', 0)}</strong></div>
    <div class="metric"><span>Failed</span><strong>{summary.get('failed', 0)}</strong></div>
    <div class="metric"><span>Blocked</span><strong>{summary.get('blocked', 0)}</strong></div>
    <div class="metric"><span>Pass Rate</span><strong>{summary.get('pass_rate', '0%')}</strong></div>
  </div>
  <table>
    <thead>
      <tr><th>Case</th><th>Title</th><th>Feature</th><th>Priority</th><th>Status</th><th>Duration</th><th>Output</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""
