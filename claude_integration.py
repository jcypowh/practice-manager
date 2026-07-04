import json
import anthropic

NARRATIVE_MODEL = 'claude-sonnet-5'
GENERATION_MODEL = 'claude-opus-4-8'


def _client(api_key):
    return anthropic.Anthropic(api_key=api_key)


def test_connection(api_key):
    client = _client(api_key)
    client.messages.create(model=NARRATIVE_MODEL, max_tokens=8, messages=[{'role': 'user', 'content': 'Say OK.'}])
    return True


def narrative_analysis(api_key, breakdown, flags, weekly_totals, n_months):
    client = _client(api_key)
    payload = {
        'trailing_months': n_months,
        'site_breakdown': breakdown,
        'flags': flags,
        'weekly_totals': [{'week_starting': w, **v} for w, v in weekly_totals],
    }
    prompt = f"""You are analysing the practice schedule of a solo gastroenterologist (SHORE \
Gastroenterology) across multiple consulting/procedural sites. Below is pre-aggregated data \
(session counts, net earnings, and utilization flags) for the last {n_months} month(s).

Data (JSON):
{json.dumps(payload, indent=2)}

Write a concise practical analysis in markdown with three sections: "Summary", "Concerns", and \
"Recommendations". Focus on site allocation, income mix between corporate consulting rooms (likely \
to be phased out) and SHORE-owned sites (Mater, NBH), and utilization flags. Be specific and \
reference site names and numbers from the data. Keep it under 400 words."""
    resp = client.messages.create(
        model=NARRATIVE_MODEL,
        max_tokens=1200,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return resp.content[0].text.strip()


def generate_schedule_draft(api_key, reference_blocks, location_names, target_year, target_month, constraints_text):
    client = _client(api_key)
    month_label = f'{target_year}-{target_month:02d}'
    prompt = f"""Dr Jeffrey Tu (SHORE Gastroenterology) runs a recurring 4-week rotation of \
consulting/procedural sessions. Below is his schedule from a recent reference month, one row per \
session slot (date, weekday, AM/PM/All day, site, activity):

{json.dumps(reference_blocks, indent=2)}

Generate a full weekday-by-weekday schedule for {month_label} (list every Monday-Friday business \
day in that month), following the same recurring rotation pattern as the reference month above, \
adjusted for these constraints (if any): {constraints_text or 'none'}.

Use ONLY these site names, exactly as spelled: {', '.join(location_names)}.

Return ONLY a JSON array (no other text), one object per slot:
[{{"date": "YYYY-MM-DD", "slot": "AM|PM|All day", "site": "<site name>", "activity": "Consult|Clinic|Scope|All day|Other", "note": ""}}]"""
    resp = client.messages.create(
        model=GENERATION_MODEL,
        max_tokens=4096,
        messages=[{'role': 'user', 'content': prompt}],
    )
    text = resp.content[0].text.strip()
    start, end = text.find('['), text.rfind(']') + 1
    if start < 0 or end <= start:
        raise ValueError('Claude did not return a JSON array.')
    return json.loads(text[start:end])
