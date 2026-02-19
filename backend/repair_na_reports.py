"""Repair N/A reports where ai_analysis contains nested JSON from markdown code blocks.
Tries full JSON parse first, falls back to regex extraction for truncated cases."""
import json
import re
import sys
sys.path.insert(0, '.')

from app.db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# Find reports where ai_analysis summary contains nested JSON (```json wrapped)
rows = db.execute(text("""
    SELECT id, symbol, ai_analysis FROM ai_analysis_reports
    WHERE ai_analysis LIKE '%```json%'
""")).fetchall()

print(f"Found {len(rows)} reports with nested JSON")

fixed = 0
for r in rows:
    rid = r[0]
    symbol = r[1]
    ai_text = r[2]

    if not ai_text:
        continue

    # Parse the outer JSON
    try:
        outer = json.loads(ai_text)
        summary_raw = outer.get("summary", "")
    except Exception:
        print(f"  {rid} ({symbol}): Could not parse outer JSON")
        continue

    if "```json" not in summary_raw and "{" not in summary_raw:
        continue

    # Try to extract full inner JSON first
    inner = None

    # Pattern 1: ```json\n{...}\n```
    match = re.search(r'```(?:json)?\s*\n([\s\S]+?)\n```', summary_raw)
    if match:
        try:
            inner = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Pattern 2: Find { ... } in summary
    if inner is None:
        brace_start = summary_raw.find('{')
        brace_end = summary_raw.rfind('}')
        if brace_start >= 0 and brace_end > brace_start:
            try:
                inner = json.loads(summary_raw[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass

    if inner and isinstance(inner, dict) and (inner.get("grade") or inner.get("summary")):
        # Full JSON parse succeeded
        grade = inner.get("grade")
        inner_summary = inner.get("summary")
        perf = inner.get("performance_analysis")
        action = inner.get("action")
        risk = inner.get("risk_level")
        news = inner.get("news_articles", [])
        recs = inner.get("recommendations", [])
        news_impact = inner.get("news_impact")
        param_suggestions = inner.get("parameter_suggestions")

        # Build repaired ai_analysis from inner JSON
        repaired = dict(inner)
        repaired["note"] = "repaired from nested JSON"
    else:
        # Fallback: regex extraction for truncated cases
        inner_text = summary_raw

        grade_match = re.search(r'"grade"\s*:\s*"([^"]+)"', inner_text)
        grade = grade_match.group(1) if grade_match else None

        summary_match = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', inner_text)
        inner_summary = summary_match.group(1) if summary_match else None
        if inner_summary:
            inner_summary = inner_summary.replace('\\"', '"').replace('\\n', '\n')

        action_match = re.search(r'"action"\s*:\s*"([^"]+)"', inner_text)
        action = action_match.group(1) if action_match else None

        risk_match = re.search(r'"risk_level"\s*:\s*"([^"]+)"', inner_text)
        risk = risk_match.group(1) if risk_match else None

        perf_match = re.search(r'"performance_analysis"\s*:\s*"((?:[^"\\]|\\.)*)"', inner_text)
        perf = perf_match.group(1) if perf_match else None
        if perf:
            perf = perf.replace('\\"', '"').replace('\\n', '\n')

        if not grade and not inner_summary:
            print(f"  {rid} ({symbol}): No extractable fields")
            continue

        news = []
        recs = []
        repaired = {
            "summary": inner_summary or summary_raw[:200],
            "grade": grade or "N/A",
            "performance_analysis": perf or "",
            "news_articles": [],
            "recommendations": [],
            "action": action or "유지",
            "risk_level": risk or "medium",
            "note": "repaired from truncated nested JSON",
        }

    updates = {
        "ai": json.dumps(repaired, ensure_ascii=False),
        "grade": grade or "N/A",
        "kf": json.dumps({"summary": inner_summary or repaired.get("summary"), "performance_analysis": perf or ""}),
        "rid": rid,
    }

    set_parts = ["ai_analysis = :ai", "grade = :grade", "key_findings = :kf"]

    if action:
        updates["action"] = action
        set_parts.append("action = :action")
    if risk:
        updates["risk"] = risk
        set_parts.append("risk_level = :risk")
    if news:
        updates["news"] = json.dumps(news, ensure_ascii=False)
        set_parts.append("news_data = :news")
    if recs:
        updates["recs"] = json.dumps(recs, ensure_ascii=False)
        set_parts.append("recommendations = :recs")

    db.execute(text(f"""
        UPDATE ai_analysis_reports SET {', '.join(set_parts)} WHERE id = :rid
    """), updates)

    fixed += 1
    print(f"  {rid} ({symbol}): Fixed -> grade={grade}, action={action}, risk={risk}")

db.commit()
db.close()
print(f"\nDone. Fixed {fixed} reports.")
