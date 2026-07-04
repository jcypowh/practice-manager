import re
from collections import Counter
from datetime import date

MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

_DATE_RE = re.compile(r'(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})')
_TIME_NOTE_RE = re.compile(r'\(([^)]+)\)')


def _parse_date(raw):
    if raw is None:
        return None
    if hasattr(raw, 'strftime'):
        return raw.strftime('%Y-%m-%d')
    m = _DATE_RE.match(str(raw).strip())
    if not m:
        return None
    day, mon_name, year = m.groups()
    mon = MONTHS.get(mon_name[:3].lower())
    if not mon:
        return None
    return date(int(year), mon, int(day)).isoformat()


def _clean_site(raw):
    s = (raw or '').strip()
    if s in ('', '—', '-'):
        return 'Unknown', ''
    if s.endswith('*'):
        return s[:-1].strip(), '*'
    return s, ''


def _extract_time_note(raw):
    s = (raw or '').strip()
    m = _TIME_NOTE_RE.search(s)
    if not m or not any(ch.isdigit() for ch in m.group(1)):
        return s, ''
    return _TIME_NOTE_RE.sub('', s).strip(), m.group(1).strip()


def _normalize_activity(stripped):
    s = (stripped or '').strip()
    if s in ('', '—', '-'):
        return 'Other'
    if s in ('Consult', 'Clinic', 'Scope', 'All day'):
        return s
    if s == 'Endoscopy':
        return 'Scope'
    if 'Scope' in s:
        return 'Scope'
    if 'Consult' in s:
        return 'Consult'
    if 'Clinic' in s:
        return 'Clinic'
    return 'Other'


def _infer_year_month(rows):
    counts = Counter((int(r['date'][:4]), int(r['date'][5:7])) for r in rows if r['date'])
    return counts.most_common(1)[0][0]


_TITLE_MONTH_YEAR_RE = re.compile(r'([A-Za-z]+)\s+(\d{4})')
_GRID_DAY_RE = re.compile(r'(\d{1,2})\s+([A-Za-z]{3,})')
_SITE_ACTIVITY_RE = re.compile(r'\s[-–—]\s')


def _infer_title_month_year(title):
    for m in _TITLE_MONTH_YEAR_RE.finditer(title or ''):
        mon = MONTHS.get(m.group(1)[:3].lower())
        if mon:
            return int(m.group(2)), mon
    return None, None


def _parse_grid_day_date(cell, year, title_month):
    if not cell:
        return None
    m = _GRID_DAY_RE.search(str(cell))
    if not m:
        return None
    day = int(m.group(1))
    mon = MONTHS.get(m.group(2)[:3].lower())
    if not mon:
        return None
    yr = year + 1 if mon < title_month else year
    return date(yr, mon, day).isoformat()


def _split_site_activity(s):
    parts = _SITE_ACTIVITY_RE.split(s, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return s.strip(), ''


def _parse_grid_cell(text):
    """Parse a calendar-grid cell like 'AM\\nChatswood - Consult' or 'CDD\\n(All day)'.
    Returns (slot, site_name, activity_text) or None if the cell has no usable content."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return None
    is_allday = 'all day' in lines[-1].lower()
    if is_allday:
        lines = lines[:-1]
    if not lines:
        return None

    if lines[0].upper() in ('AM', 'PM'):
        slot = lines[0].upper()
        rest = lines[1] if len(lines) > 1 else ''
        site_name, activity_text = _split_site_activity(rest)
    else:
        slot = 'All day' if is_allday else 'AM'
        site_name, activity_text = _split_site_activity(lines[0])
        if len(lines) > 1:
            activity_text = lines[1]

    if is_allday:
        slot = 'All day'
        if not activity_text:
            activity_text = 'All day'
    return slot, site_name or 'Unknown', activity_text


def parse_calendar_grid(wb, sheet_name=None):
    """Fallback parser for the merged-cell calendar-grid sheet (used when no 'Schedule
    List' sheet exists). wb: an openpyxl Workbook already loaded with data_only=True.
    Returns (year, month, rows) or raises ValueError if the grid can't be parsed."""
    ws = wb[sheet_name] if sheet_name else wb[wb.sheetnames[0]]
    all_rows = list(ws.iter_rows(values_only=True))
    if not all_rows:
        raise ValueError('Calendar grid sheet is empty.')

    title = str(all_rows[0][0] or '')
    year, title_month = _infer_title_month_year(title)
    if not year:
        raise ValueError('Could not determine the month/year from the calendar grid title.')

    header_idx = None
    for i, row in enumerate(all_rows):
        if row and row[0] is not None and str(row[0]).strip() == 'Week':
            header_idx = i
            break
    if header_idx is None:
        raise ValueError('Could not find the calendar grid header row ("Week | Monday | ... | Friday").')

    rows_out = []
    day_dates = None
    for row in all_rows[header_idx + 1:]:
        first = row[0] if row else None
        if isinstance(first, str) and first.strip().startswith('Week'):
            day_dates = [_parse_grid_day_date(row[c] if len(row) > c else None, year, title_month)
                         for c in range(1, 6)]
            continue
        if first is None and row and any(v is not None for v in row[1:6]):
            if day_dates is None:
                continue
            for c in range(1, 6):
                cell = row[c] if len(row) > c else None
                if not cell:
                    continue
                parsed = _parse_grid_cell(str(cell))
                if not parsed:
                    continue
                slot, site_name, activity_text = parsed
                d = day_dates[c - 1]
                if not d:
                    continue
                activity_stripped, time_note = _extract_time_note(activity_text)
                activity_norm = _normalize_activity(activity_stripped)
                rows_out.append({
                    'date': d,
                    'day_name': '',
                    'slot': slot,
                    'site_name': site_name,
                    'site_note': '',
                    'activity': activity_norm,
                    'activity_raw': str(cell),
                    'time_note': time_note,
                })
            continue
        break

    if not rows_out:
        raise ValueError('Found a calendar grid sheet but could not parse any session blocks from it.')
    return year, title_month, rows_out


def parse_schedule_list(wb):
    """wb: an openpyxl Workbook already loaded with data_only=True.
    Returns (year, month, rows) or raises ValueError if no 'Schedule List' sheet."""
    if 'Schedule List' not in wb.sheetnames:
        raise ValueError('This file has no "Schedule List" sheet - please export/select a version '
                          'of the schedule that includes it.')
    ws = wb['Schedule List']
    rows_out = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        if not row:
            continue
        padded = (list(row) + [None] * 5)[:5]
        date_raw, day_raw, session_raw, site_raw, activity_raw = padded
        if not date_raw:
            continue
        date_iso = _parse_date(date_raw)
        if not date_iso:
            continue
        slot = (session_raw or '').strip() or 'AM'
        site_name, site_note = _clean_site(site_raw)
        activity_stripped, time_note = _extract_time_note(activity_raw)
        activity_norm = _normalize_activity(activity_stripped)
        rows_out.append({
            'date': date_iso,
            'day_name': (day_raw or '').strip() if isinstance(day_raw, str) else '',
            'slot': slot,
            'site_name': site_name,
            'site_note': site_note,
            'activity': activity_norm,
            'activity_raw': str(activity_raw) if activity_raw is not None else '',
            'time_note': time_note,
        })
    if not rows_out:
        raise ValueError('Sheet has a "Schedule List" tab but no data rows were found.')
    year, month = _infer_year_month(rows_out)
    return year, month, rows_out
