import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import monitor as m

ISSUED = datetime(2026, 10, 6, 16, tzinfo=timezone.utc)


class ParserTests(unittest.TestCase):
    def record(self, body, mode="wave_detail"):
        return m.parse_zone('.WEDNESDAY...' + body, ISSUED, mode)[0]

    def test_user_sample_no_match_and_missing_period(self):
        records = m.parse_zone(Path('sample.txt').read_text(), ISSUED)
        self.assertEqual(len(records), 8)
        self.assertFalse(any(m.qualifies(r) for r in records))
        self.assertEqual(records[0]['period_lo'], 7)
        self.assertEqual(records[0]['seas_hi'], 8)
        self.assertIsNone(records[-1]['period_lo'])

    def test_boundary_range(self):
        self.assertTrue(m.qualifies(self.record('Seas 1 to 2 ft. Dominant period 7 seconds.')))
        self.assertFalse(m.qualifies(self.record('Seas 2 to 3 ft. Dominant period 8 seconds.')))

    def test_missing_period(self):
        r = self.record('Seas 1 to 2 feet.')
        self.assertFalse(m.qualifies(r))
        self.assertIn('period not listed', m.compact(r))

    def test_period_range_uses_low_end(self):
        self.assertFalse(m.qualifies(self.record('Seas 2 feet. Dominant period 6 to 8 seconds.')))

    def test_night_match_and_combined_heading(self):
        r = m.parse_zone('.WEDNESDAY AND WEDNESDAY NIGHT...Seas 1 foot. Dominant period 8 seconds.', ISSUED)
        self.assertEqual([(x['date'], x['slot']) for x in r], [('2026-10-07','D'),('2026-10-07','N')])
        self.assertTrue(all(m.qualifies(x) for x in r))

    def test_combined_two_dates(self):
        r = m.parse_zone('.FRIDAY NIGHT AND SATURDAY...Seas 1 foot. Dominant period 8 seconds.', ISSUED)
        self.assertEqual([(x['date'], x['slot']) for x in r], [('2026-10-09','N'),('2026-10-10','D')])

    def test_seas_changes_and_occasional(self):
        self.assertFalse(m.qualifies(self.record('Seas 1 to 2 feet, building to 2 to 3 feet. Dominant period 8 seconds.')))
        r = self.record('Seas 1 to 2 feet, occasionally to 3 feet. Dominant period 8 seconds.')
        self.assertTrue(m.qualifies(r))
        self.assertEqual(r['occasional'], 3)

    def test_or_less_decimal_and_unicode(self):
        self.assertTrue(m.qualifies(self.record('Seas 2 feet or less. Dominant period 7 seconds.')))
        self.assertTrue(m.qualifies(self.record('Seas 1.5 to 2 feet. Dominant period 7.5 seconds.')))
        r = m.parse_zone('[TONIGHT\u2028Seas 1–2 feet. Wave Detail: East 2 feet at 8 seconds.]', ISSUED)
        self.assertTrue(m.qualifies(r[0]))

    def test_wave_detail_tallest_not_longest(self):
        r = self.record('Seas 1 to 2 feet. Wave Detail: East 2 feet at 6 seconds and north 1 foot at 10 seconds.')
        self.assertEqual(r['period_lo'], 6)
        self.assertFalse(m.qualifies(r))

    def test_wave_tie_and_transitions(self):
        for detail in ['East 2 feet at 8 seconds and north 2 feet at 6 seconds', 'East 2 feet at 8 seconds, becoming north 1 foot at 6 seconds']:
            r = self.record('Seas 1 to 2 feet. Wave Detail: ' + detail + '.')
            self.assertFalse(m.qualifies(r))
        self.assertTrue(m.qualifies(self.record('Seas 1 to 2 feet. Wave Detail: East 2 feet at 8 seconds, becoming east 1 foot at 7 seconds.')))

    def test_strict(self):
        r = self.record('Seas 1 to 2 feet. Wave Detail: East 2 feet at 8 seconds.', 'strict')
        self.assertIsNone(r['period_lo'])
        self.assertFalse(m.qualifies(r))

    def test_unsupported_and_unbounded(self):
        self.assertFalse(m.qualifies(self.record('Seas 2 feet or more. Dominant period 8 seconds.')))
        with self.assertRaises(RuntimeError):
            m.parse_zone('.EARLY NEXT WEEK...Seas 1 foot.', ISSUED)

    def test_through_heading(self):
        r = m.parse_zone('.FRIDAY THROUGH SATURDAY...Seas 1 foot. Dominant period 8 seconds.', ISSUED)
        self.assertEqual([(x['date'],x['slot']) for x in r], [('2026-10-09','D'),('2026-10-09','N'),('2026-10-10','D')])

    def test_live_api_fixture(self):
        p=json.loads(Path('live-api-fixture.json').read_text())
        issued=datetime.fromisoformat(p['issuanceTime'])
        zones={z:m.parse_zone(b,issued) for z,b in m.zone_sections(p['productText']).items()}
        self.assertEqual(set(zones),set(m.ZONES))
        self.assertTrue(all(len(r)>=8 for r in zones.values()))
        self.assertFalse(any(m.qualifies(r) for rows in zones.values() for r in rows))

    def test_missing_zone_and_combined_ugc(self):
        text = 'AMZ450-452-070700-\n.WEDNESDAY...Seas 1 foot. Dominant period 8 seconds.\n$$\nAMZ454-070700-\n.WEDNESDAY...Seas 3 feet.\n$$'
        sections = m.zone_sections(text)
        self.assertEqual(set(sections), set(m.ZONES))
        with self.assertRaises(RuntimeError):
            m.zone_sections(text.split('$$')[0])

    def test_signature_ignores_nonmatch_changes(self):
        r = self.record('Seas 1 to 2 feet. Dominant period 8 seconds.')
        zones = {'AMZ452':[r]}
        sig = m.signature(zones, 'wave_detail')
        zones['AMZ452'].append(self.record('Seas 6 feet. Dominant period 8 seconds.'))
        self.assertEqual(m.signature(zones, 'wave_detail'), sig)
        r['period_lo'] = r['period_hi'] = 9
        self.assertNotEqual(m.signature(zones, 'wave_detail'), sig)

    def test_seven_dates_no_invented_forecast(self):
        r = m.parse_zone(Path('sample-match.txt').read_text(), ISSUED)
        msg = m.format_message({z:r for z in m.ZONES}, ISSUED, ISSUED, True)
        self.assertEqual(msg.count('Sun 10/11 forecast not available'), 2)
        self.assertIn('✅N', msg)
        self.assertLess(len(msg.encode()), 4096)
        self.assertEqual(len(m.next_week(r, ISSUED + timedelta(days=7))), 0)

    def test_midnight_uses_issuance_date(self):
        r = m.parse_zone('.TONIGHT...Seas 1 foot. Dominant period 8 seconds.\n.WEDNESDAY...Seas 2 feet.', ISSUED)
        now = datetime(2026,10,7,5,tzinfo=timezone.utc)
        self.assertEqual(len(m.next_week(r, now)), 1)

    def test_duplicate_partial_heading_is_conservative(self):
        r = m.parse_zone('.FRIDAY...Seas 1 foot. Dominant period 8 seconds.\n.FRIDAY...Seas 1 foot.', ISSUED)
        self.assertEqual(len(r),1)
        self.assertFalse(m.qualifies(r[0]))


class DeliveryTests(unittest.TestCase):
    def test_send_suppress_change_reset_reappear(self):
        text = 'AMZ452-070700-\n.TODAY...Seas 1 foot. Dominant period 8 seconds.\n$$\nAMZ454-070700-\n.TODAY...Seas 1 foot. Dominant period 8 seconds.\n$$'
        with tempfile.TemporaryDirectory() as d:
            original = os.getcwd()
            try:
                os.chdir(d)
                issued = datetime.now(timezone.utc)
                args = argparse.Namespace(mode='check')
                with patch.object(m, 'fetch_product', return_value=(text,issued)), patch.object(m, 'publish') as send, patch.object(m, 'backup_email',return_value=True):
                    m.run(args)
                    m.run(args)
                    self.assertEqual(send.call_count, 1)
                with patch.object(m, 'fetch_product', return_value=(text.replace('8 seconds','9 seconds'),issued)), patch.object(m, 'publish') as send, patch.object(m, 'backup_email',return_value=True):
                    m.run(args)
                    self.assertEqual(send.call_count, 1)
                with patch.object(m, 'fetch_product', return_value=(text.replace('1 foot','4 feet'),issued)), patch.object(m, 'publish') as send:
                    m.run(args)
                    self.assertEqual(send.call_count, 0)
                    self.assertIsNone(json.loads(Path('state.json').read_text())['active_signature'])
                with patch.object(m, 'fetch_product', return_value=(text,issued)), patch.object(m, 'publish') as send, patch.object(m, 'backup_email',return_value=True):
                    m.run(args)
                    self.assertEqual(send.call_count, 1)
            finally:
                os.chdir(original)

    def test_publish_failure_does_not_mark_sent(self):
        text = 'AMZ452-070700-\n.TODAY...Seas 1 foot. Dominant period 8 seconds.\n$$\nAMZ454-070700-\n.TODAY...Seas 1 foot. Dominant period 8 seconds.\n$$'
        with tempfile.TemporaryDirectory() as d:
            original = os.getcwd()
            try:
                os.chdir(d)
                with patch.object(m, 'fetch_product', return_value=(text, datetime.now(timezone.utc))), patch.object(m, 'publish', side_effect=RuntimeError('mock failure')):
                    with self.assertRaises(RuntimeError):
                        m.run(argparse.Namespace(mode='check'))
                    self.assertFalse(Path('state.json').exists())
            finally:
                os.chdir(original)


if __name__ == '__main__':
    unittest.main()
