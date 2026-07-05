import json
import anthropic

NARRATIVE_MODEL = 'claude-sonnet-5'
GENERATION_MODEL = 'claude-opus-4-8'


def _client(api_key):
    return anthropic.Anthropic(api_key=api_key)


def _extract_text(resp):
    """Some models return a thinking block before the actual text block, so
    content[0] isn't reliably the text - find the first block that has one."""
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            return block.text
    raise ValueError('Claude response contained no text block')


def test_connection(api_key):
    client = _client(api_key)
    client.messages.create(model=NARRATIVE_MODEL, max_tokens=8, messages=[{'role': 'user', 'content': 'Say OK.'}])
    return True


def narrative_analysis(api_key, data):
    client = _client(api_key)
    payload = {
        'period': data['period_label'],
        'total_sessions': data['total_sessions'],
        'total_revenue': data['total_revenue'],
        'group_breakdown': data['group_breakdown'],
        'site_breakdown': data['site_breakdown'],
        'flags': data['flags'],
        'rotation_weeks': data['rotation_weeks'],
        'consult_scope_session_ratio': data['consult_scope_ratio'],
        'referral_pipelines': data['pipelines'],
    }
    prompt = f"""You are analysing the practice schedule of a solo gastroenterologist (SHORE \
Gastroenterology) across multiple consulting/procedural sites, for the period: {data['period_label']}.

Sites are grouped into four categories for revenue/session reporting:
- FORHEALTH Medical Centre: the corporate consulting rooms (Chatswood, Leichhardt, Brookvale, \
Blacktown, Darlinghurst, Maroubra) - likely to be phased out over time.
- SHORE Gastroenterology: the practice's own sites (Mater Clinic, NBH Clinic).
- CDD: a single site doing both consult and scope work, deliberately NOT split by activity - \
treat it as its own thing, not part of either side of the referral pipelines below.
- Scopes: all procedural/endoscopy work (ESPH, Freshwater, Dee Why, plus Mater's own Scope \
sessions specifically - Mater's Clinic sessions count under SHORE Gastroenterology instead).

This practice relies on two referral pipelines - consult/clinic work at certain sites is what \
generates scope bookings at specific associated procedure sites:
- Pipeline 1: Chatswood + Brookvale + SHORE Gastroenterology (consult/clinic work) feed scope \
bookings at Mater (Scope), Freshwater, and Dee Why.
- Pipeline 2: Darlinghurst + Leichhardt + Maroubra + Blacktown (consult work) feed scope bookings \
at East Sydney Private Hospital (ESPH).

A "healthy" pipeline ratio means a reasonable number of consults are converting into scope \
referrals - something like 10 consults generating only 1 scope booking would be UNHEALTHY (too \
many consults not converting into procedures). Comment specifically on whether each pipeline's \
ratio (source sessions : target sessions, given in `referral_pipelines`) looks healthy or concerning.

`rotation_weeks` breaks the data down by the practice's perpetual 4-week rotation (Week 1-4, \
which repeats regardless of calendar month/year - NOT the same as calendar week-of-year), with \
a Monday-Friday breakdown inside each. Use this to flag if a particular rotation week or weekday \
is consistently under/over-performing.

Data (JSON):
{json.dumps(payload, indent=2)}

Write a concise practical analysis in markdown with these sections: "Summary", "Revenue mix" \
(comment on the FORHEALTH vs SHORE vs CDD vs Scopes split and what it means for income direction), \
"Referral pipeline health" (comment specifically on both pipeline ratios using the logic above), \
"Weekly rotation pattern" (any Week 1-4 or weekday-of-week pattern worth flagging, from \
`rotation_weeks`), "Concerns" (utilization flags), and "Recommendations". Be specific, reference \
real site/week names and numbers from the data. Keep it under 550 words."""
    resp = client.messages.create(
        model=NARRATIVE_MODEL,
        max_tokens=1500,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return _extract_text(resp).strip()


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
    text = _extract_text(resp).strip()
    start, end = text.find('['), text.rfind(']') + 1
    if start < 0 or end <= start:
        raise ValueError('Claude did not return a JSON array.')
    return json.loads(text[start:end])
