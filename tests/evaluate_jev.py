#!/usr/bin/env python3
"""Explicit fixture replay or live provider-only evaluation; never applies work."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from awo_advice import AdviceError, MODEL, build_payload, call_jev, load_key, validate_response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--replay', action='store_true', help='synthetic schema check, not model evaluation')
    mode.add_argument('--live', action='store_true', help='send synthetic cases to TypeSafe (may incur cost)')
    parser.add_argument('--limit', type=int, default=3, choices=range(1, 13))
    args = parser.parse_args()
    data = json.loads((Path(__file__).parent / 'fixtures/jev-korean-cases.json').read_text())
    source = 'fixture_replay' if args.replay else 'live'
    key = None
    if args.live:
        try:
            key = load_key()
        except AdviceError as exc:
            print(json.dumps({'source': source, 'status': 'unavailable', 'reason': str(exc),
                              'live_api_verified': False}))
            return 0
    results = []
    for case in data['cases'][:args.limit]:
        payload = build_payload(case['request'], '', data['projects'], data['existing_goals'], True, True)
        try:
            if args.replay:
                # Deliberately synthetic, constructed from labels. Cannot measure accuracy.
                raw = {'model': MODEL, 'usage': {'input_tokens': 0}, 'answers': {
                    name: {'type': 'choice', 'choice': case['expected'][name], 'confidence': 1,
                           'probabilities': {k: int(k == case['expected'][name]) for k in q['criteria']}}
                    for name, q in payload['questions'].items()}}
            else:
                raw = call_jev(payload, key)
            answers, usage = validate_response(raw, payload)
            result = {'id': case['id'], 'status': 'schema_valid', 'answers': answers, 'usage': usage}
            if args.live:
                result['label_matches'] = {n: a['choice'] == case['expected'][n] for n, a in answers.items()}
            results.append(result)
        except AdviceError as exc:
            results.append({'id': case['id'], 'status': 'unavailable', 'reason': str(exc)})
            break  # Avoid amplifying rate limits, authentication failures or outages.
    print(json.dumps({'source': source, 'model': MODEL, 'confidence_is_accuracy': False,
                      'live_api_verified': args.live and any(r['status'] == 'schema_valid' for r in results),
                      'is_accuracy_measurement': args.live,
                      'results': results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
