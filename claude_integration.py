import json
import anthropic

NARRATIVE_MODEL = 'claude-sonnet-5'
GENERATION_MODEL = 'claude-opus-4-8'

# Shared domain knowledge injected into every analysis-style prompt (narrative, days-off
# planning, expansion trade-off), so each one reasons with the full picture regardless of
# which specific question is being asked - not just whatever happens to be relevant to one.
PRACTICE_KNOWLEDGE = """You are advising a solo gastroenterologist (SHORE Gastroenterology) who \
runs consulting/procedural sessions across multiple sites, on a perpetual 4-week rotation \
(Week 1-4, which repeats regardless of calendar month/year - NOT the same as calendar \
week-of-year).

Sites are grouped into four categories for revenue/session reporting:
- FORHEALTH Medical Centre: the corporate consulting rooms (Chatswood, Leichhardt, Brookvale, \
Blacktown, Darlinghurst, Maroubra) - lower-yield, and the ones this practice is prepared to \
phase out or reduce over time.
- SHORE Gastroenterology: the practice's own sites (Mater Clinic, NBH Clinic) - the practice's \
own growth priority; it is always looking to expand its footprint here.
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
referrals - something like 10 consults generating only 1 scope booking would be UNHEALTHY. Never \
recommend cutting a pipeline's source-site volume so much that its associated scope target site \
starves for referrals.

"Time units" measure actual time/effort, not raw slot counts: an AM or PM session = 1 unit, an \
All-day session = 2 units by default (some sessions are manually weighted differently if they \
run longer/shorter than normal, e.g. a 7:30am-4pm Scope weighted 2.5). $/time-unit is the true \
earning-efficiency measure - prefer it over raw session counts when ranking sites."""


def _client(api_key):
    return anthropic.Anthropic(api_key=api_key)


def _extract_text(resp):
    """Some models return a thinking block before the actual text block, so
    content[0] isn't reliably the text - find the first block that has one."""
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            return block.text
    raise ValueError('Claude response contained no text block')


def _ask(api_key, prompt, max_tokens=1500):
    client = _client(api_key)
    # Extended thinking is disabled: these are well-scoped analytical asks, not open-ended
    # reasoning, and leaving thinking enabled was non-deterministically consuming the whole
    # max_tokens budget on some calls, leaving zero room for the actual text response.
    resp = client.messages.create(model=NARRATIVE_MODEL, max_tokens=max_tokens,
                                   thinking={'type': 'disabled'},
                                   messages=[{'role': 'user', 'content': prompt}])
    return _extract_text(resp).strip()


def test_connection(api_key):
    client = _client(api_key)
    client.messages.create(model=NARRATIVE_MODEL, max_tokens=8, messages=[{'role': 'user', 'content': 'Say OK.'}])
    return True


def narrative_analysis(api_key, data):
    payload = {
        'period': data['period_label'],
        'total_sessions': data['total_sessions'],
        'total_revenue': data['total_revenue'],
        'total_time_units': data['total_time_units'],
        'group_breakdown': data['group_breakdown'],
        'site_breakdown': data['site_breakdown'],
        'efficiency_worst_first': data['efficiency'],
        'flags': data['flags'],
        'rotation_weeks': data['rotation_weeks'],
        'consult_scope_time_ratio': data['consult_scope_ratio'],
        'referral_pipelines': data['pipelines'],
    }
    prompt = f"""{PRACTICE_KNOWLEDGE}

You are analysing the schedule for the period: {data['period_label']}.

Data (JSON):
{json.dumps(payload, indent=2)}

Write a concise practical analysis in markdown with these sections: "Summary", "Revenue mix" \
(comment on the FORHEALTH vs SHORE vs CDD vs Scopes split and what it means for income direction), \
"Referral pipeline health" (comment specifically on both pipeline ratios using the logic above), \
"Weekly rotation pattern" (any Week 1-4 or weekday-of-week pattern worth flagging, from \
`rotation_weeks`), "Time efficiency" (call out any site from `efficiency_worst_first` that's \
consuming significant time for low $/time-unit return), "Concerns" (utilization flags), and \
"Recommendations". Be specific, reference real site/week names and numbers from the data. Keep \
it under 600 words."""
    return _ask(api_key, prompt, max_tokens=1500)


def suggest_days_off(api_key, rotation_weeks, num_days, period_label):
    prompt = f"""{PRACTICE_KNOWLEDGE}

Dr Tu wants to take {num_days} consecutive CALENDAR days off as leave (not just business days). \
Weekends already have no scheduled work, so a window that includes a weekend gets "free" rest \
days that cost nothing in earnings - always prefer a window that overlaps a Saturday/Sunday over \
one that doesn't, if the earning impact is otherwise similar.

Below is the $-earning and session-count breakdown for every weekday within each of the 4 \
rotation weeks (based on data from: {period_label}). Because the rotation repeats, this tells you \
which weekday-in-which-rotation-week is consistently the lowest earning, regardless of the actual \
calendar date it next falls on.

rotation_weeks (JSON):
{json.dumps(rotation_weeks, indent=2)}

Task: recommend which specific run of {num_days} consecutive calendar days (naming it by rotation \
week + weekday, e.g. "Thursday of Week 3 through Monday of Week 4", and noting it overlaps a \
weekend where applicable) would have the LOWEST total earning impact if taken as leave. State the \
total $ impact of your top recommendation, then give 1-2 alternative windows ranked below it. Be \
concise and concrete - this is a practical scheduling decision, not a report."""
    return _ask(api_key, prompt, max_tokens=1800)


def suggest_shore_expansion_tradeoff(api_key, group_breakdown, site_breakdown, pipelines, extra_sessions, period_label):
    payload = {'group_breakdown': group_breakdown, 'site_breakdown': site_breakdown, 'referral_pipelines': pipelines}
    prompt = f"""{PRACTICE_KNOWLEDGE}

SHORE Gastroenterology (Mater/NBH Clinic) always wants to expand, but Dr Tu's total available \
working days are fixed - so growing SHORE Gastro means deliberately giving up ("sacrificing") \
session time elsewhere. Below is the revenue/session/efficiency breakdown by site and group, for \
the period: {period_label}.

Data (JSON):
{json.dumps(payload, indent=2)}

Task: if SHORE Gastroenterology sessions increase by {extra_sessions} per week, recommend \
specifically WHICH site(s) or session(s) should be reduced to free up that time, ranked by which \
sacrifice costs the least (prioritize cutting the lowest $/time-unit, lowest-yield sessions first \
- normally the FORHEALTH Medical Centre corporate sites, which are already earmarked to shrink) - \
while explicitly checking neither referral pipeline gets starved of source-site consult volume as \
a result (a pipeline needs enough consults feeding it to keep generating scope referrals). Give a \
specific, ranked, practical recommendation naming real sites. Keep it concise."""
    return _ask(api_key, prompt, max_tokens=1800)


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
        thinking={'type': 'disabled'},
        messages=[{'role': 'user', 'content': prompt}],
    )
    text = _extract_text(resp).strip()
    start, end = text.find('['), text.rfind(']') + 1
    if start < 0 or end <= start:
        raise ValueError('Claude did not return a JSON array.')
    return json.loads(text[start:end])
