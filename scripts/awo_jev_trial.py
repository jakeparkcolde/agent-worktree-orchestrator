"""Small local Jev trial journal; no prompts, keys, candidate text or automation."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import uuid

MODEL = 'jev-1.13.0'
STATUSES = {'disabled', 'unavailable', 'shadow_advisory', 'suggested'}
REASONS = set('''not_requested apply_boundary invalid_explicit_project rules_blocked
rules_sufficient missing_key input_limit sensitive_input candidate_limit response_limit
rate_limited http_error timeout network_error malformed_response unknown_id stale_candidates
inconsistent_candidates candidate_state_unavailable candidate_recommendation request_needs_review
no_single_candidate invalid_key_format key_file_type key_file_owner key_file_permissions
key_file_unreadable key_file_format trial_expired trial_not_started trial_config_invalid
trial_window_changed'''.split())
COHORTS = ('production', 'smoke')
MAX_JOURNAL = 16 * 1024 * 1024


class TrialError(Exception):
    pass


def trial_directory():
    return Path.home() / '.awo/jev-trial'


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError('invalid time')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timezone required')
    return parsed.astimezone(timezone.utc)


def trial_state():
    """Never create settings or infer a trial period."""
    try:
        with (trial_directory() / 'config.json').open('rb') as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError('config limit')
        config = json.loads(raw)
        if not isinstance(config, dict) or set(config) != {'starts_at', 'ends_at'}:
            raise ValueError('config fields')
        start, end = parse_time(config['starts_at']), parse_time(config['ends_at'])
        if start >= end:
            raise ValueError('config interval')
        now = utcnow()
        state = 'not_started' if now < start else ('expired' if now >= end else 'active')
        return {'status': state, 'starts_at': timestamp(start), 'ends_at': timestamp(end)}
    except FileNotFoundError:
        return {'status': 'not_configured'}
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        return {'status': 'unavailable', 'reason': 'trial_config_invalid'}


def same_active_window(window):
    current = trial_state()
    return current['status'] == 'active' and current == window


@contextmanager
def journal_file(create=False, exclusive=False):
    """One append-only file, flock for concurrent appends/read-modify-appends."""
    flags = os.O_RDWR | os.O_APPEND if exclusive else os.O_RDONLY
    flags |= os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    if create:
        flags |= os.O_CREAT
    fd = os.open(trial_directory() / 'events.jsonl', flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise TrialError('journal_unavailable')
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield fd
    finally:
        os.close(fd)


def append_row(fd, row):
    encoded = (json.dumps(row, allow_nan=False, separators=(',', ':')) + '\n').encode()
    while encoded:
        count = os.write(fd, encoded)
        if count <= 0:
            raise OSError('append failed')
        encoded = encoded[count:]
    os.fsync(fd)


def record(result, metrics, window, cohort):
    """Allowlist every persisted value. Failures supplement, never change action."""
    try:
        return _record(result, metrics, window, cohort)
    except (OSError, ValueError, TypeError, KeyError, TrialError):
        return {'status': 'unavailable', 'reason': 'record_failed'}


def _record(result, metrics, window, cohort):
    if not same_active_window(window):
        return {'status': 'not_recorded', 'reason': 'trial_window_changed'}
    event_id = str(uuid.uuid4())
    selections = {name: hashlib.sha256((event_id + name + answer['choice']).encode()).hexdigest()
                  for name, answer in result.get('answers', {}).items()
                  if name in ('project', 'existing_goal', 'request_type')}
    event = {'type': 'event', 'event_id': event_id, 'timestamp': timestamp(utcnow()),
             'cohort': cohort, 'status': result['status'] if result['status'] in STATUSES else 'unavailable',
             'reason': result['reason'] if result['reason'] in REASONS else 'unknown_reason',
             'model': MODEL, 'api_called': metrics['api_called'],
             'api_latency_ms': metrics['api_latency_ms'],
             'input_tokens': metrics['input_tokens'], 'selection_ids': selections}
    try:
        with journal_file(create=True, exclusive=True) as fd:
            # A lock wait may cross expiry. Never append results outside the window.
            if not same_active_window(window):
                return {'status': 'not_recorded', 'reason': 'trial_window_changed'}
            event['timestamp'] = timestamp(utcnow())
            append_row(fd, event)
        return {'status': 'recorded', 'event_id': event_id, 'cohort': cohort,
                'selection_ids': selections}
    except (OSError, ValueError, TypeError, TrialError):
        return {'status': 'unavailable', 'reason': 'record_failed'}


def read_rows(fd):
    raw = bytearray()
    while len(raw) <= MAX_JOURNAL:
        chunk = os.read(fd, min(65536, MAX_JOURNAL + 1 - len(raw)))
        if not chunk:
            break
        raw.extend(chunk)
    if len(raw) > MAX_JOURNAL:
        raise TrialError('journal_limit')
    if raw and not raw.endswith(b'\n'):
        raise TrialError('journal_invalid')
    try:
        rows = [json.loads(line) for line in raw.splitlines()]
        events = {}
        for row in rows:
            if not isinstance(row, dict) or str(uuid.UUID(row['event_id'])) != row['event_id']:
                raise ValueError('event ID')
            parse_time(row['timestamp'])
            if row['type'] == 'event':
                if (row['event_id'] in events or row['cohort'] not in COHORTS
                        or row['status'] not in STATUSES or row['model'] != MODEL
                        or type(row['api_called']) is not bool):
                    raise ValueError('event fields')
                latency = row['api_latency_ms']
                if ((row['api_called'] and (type(latency) not in (float, int) or
                        not 0 <= latency < float('inf'))) or (not row['api_called'] and latency is not None)):
                    raise ValueError('latency')
                tokens = row['input_tokens']
                if tokens is not None and (type(tokens) is not int or tokens < 0):
                    raise ValueError('tokens')
                events[row['event_id']] = row
            elif row['type'] == 'feedback':
                if (row['event_id'] not in events or row['result'] not in ('accepted', 'corrected', 'uncertain')
                        or type(row['critical_misroute']) is not bool):
                    raise ValueError('feedback fields')
            else:
                raise ValueError('row type')
        return rows
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise TrialError('journal_invalid') from None


def read_journal():
    try:
        with journal_file() as fd:
            return read_rows(fd)
    except FileNotFoundError:
        return []


def reviewable(event):
    return event['api_called'] and event['status'] in ('suggested', 'shadow_advisory')


def feedback(event_id, result, critical):
    try:
        if str(uuid.UUID(event_id)) != event_id:
            raise ValueError('invalid ID')
    except ValueError:
        raise TrialError('invalid_event_id') from None
    with journal_file(exclusive=True) as fd:
        rows = read_rows(fd)
        event = next((r for r in rows if r['type'] == 'event' and r['event_id'] == event_id), None)
        if not event:
            raise TrialError('unknown_event_id')
        if not reviewable(event):
            raise TrialError('event_not_reviewable')
        append_row(fd, {'type': 'feedback', 'event_id': event_id, 'timestamp': timestamp(utcnow()),
                        'result': result, 'critical_misroute': critical})
    return {'status': 'recorded', 'event_id': event_id, 'result': result,
            'critical_misroute': critical}


def percentile(values, percent):
    # Nearest-rank observations; not an inferred performance distribution.
    return sorted(values)[math.ceil(percent * len(values)) - 1] if values else None


def summarize(rows, window, cohort):
    start, end = parse_time(window['starts_at']), parse_time(window['ends_at'])
    events = {r['event_id']: r for r in rows if r['type'] == 'event' and r['cohort'] == cohort
              and start <= parse_time(r['timestamp']) < end}
    latest = {r['event_id']: r for r in rows if r['type'] == 'feedback' and r['event_id'] in events}
    calls = [e for e in events.values() if e['api_called']]
    successes = [e for e in calls if reviewable(e)]
    reviewed = [latest[e['event_id']] for e in successes if e['event_id'] in latest]
    latencies = [e['api_latency_ms'] for e in calls]
    tokens = [e['input_tokens'] for e in calls if e['input_tokens'] is not None]
    return {'events': len(events), 'live_calls': len(calls), 'live_successes': len(successes),
            'live_failures': len(calls) - len(successes), 'skipped_calls': len(events) - len(calls),
            'latency_ms': {'samples': len(latencies), 'p50': percentile(latencies, 0.5),
                           'p95': percentile(latencies, 0.95), 'method': 'nearest_rank'},
            'input_tokens': {'known_total': sum(tokens), 'unknown_calls': len(calls) - len(tokens)},
            'reviewed': len(reviewed), 'unreviewed': len(successes) - len(reviewed),
            'accepted': sum(r['result'] == 'accepted' for r in reviewed),
            'corrected': sum(r['result'] == 'corrected' for r in reviewed),
            'uncertain': sum(r['result'] == 'uncertain' for r in reviewed),
            'critical_misroutes': sum(r['critical_misroute'] for r in reviewed),
            'sufficiency': 'unknown', 'quality': 'unknown',
            'evidence': 'insufficient_data' if not reviewed else 'exploratory_only'}


def report():
    window = trial_state()
    if window['status'] in ('not_configured', 'unavailable'):
        return {'trial': window, 'sufficiency': 'unknown', 'cohorts': {}}
    rows = read_journal()
    return {'trial': window, 'sufficiency': 'unknown',
            'cohorts': {cohort: summarize(rows, window, cohort) for cohort in COHORTS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('status', 'report'):
        commands.add_parser(name).add_argument('--json', action='store_true')
    item = commands.add_parser('feedback')
    item.add_argument('event_id')
    item.add_argument('--result', required=True, choices=['accepted', 'corrected', 'uncertain'])
    item.add_argument('--critical-misroute', action='store_true')
    item.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'status':
            result = {'trial': trial_state(), 'automatic_execution': False}
        elif args.command == 'report':
            result = report()
        else:
            result = feedback(args.event_id, args.result, args.critical_misroute)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, TrialError) as exc:
        reason = str(exc) if isinstance(exc, TrialError) else 'journal_unavailable'
        print(json.dumps({'status': 'unavailable', 'reason': reason, 'sufficiency': 'unknown'}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
