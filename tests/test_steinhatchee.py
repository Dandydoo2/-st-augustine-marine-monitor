import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import steinhatchee_monitor as m


class SteinhatcheeTests(unittest.TestCase):
    issued = datetime(2026, 10, 11, 8, 1, tzinfo=timezone.utc)

    def record(self, body):
        return m.parse_zone('.TODAY...' + body, self.issued)[0]

    def test_three_conditions_and_knot_conversion(self):
        r = self.record('North winds 5 knots. Waves 1 foot or less. Wave Detail: North 1 foot at 4 seconds.')
        self.assertTrue(m.qualifies(r))
        self.assertAlmostEqual(r['wind_hi'], 5.7538972401)
        for text in ['North winds 5 to 10 knots.', 'North winds 7 knots.', 'North winds 5 knots, increasing to 10 knots.', 'North winds 5 knots with gusts to 10 knots.']:
            with self.subTest(text=text):
                self.assertFalse(m.qualifies(self.record(text + ' Seas 1 foot. Dominant period 4 seconds.')))

    def test_mph_boundary_and_missing_data(self):
        for wind, expected in [('7 mph', True), ('7.01 mph', False), ('5 to 7 mph', True), ('around 5 knots', True), ('light and variable', False)]:
            with self.subTest(wind=wind):
                self.assertEqual(m.qualifies(self.record('North winds ' + wind + '. Seas 1 foot. Dominant period 4 seconds.')), expected)
        for body in ['Seas 1 foot. Dominant period 4 seconds.', 'North winds 5 knots. Seas 1 foot.', 'North winds 5 knots. Seas 1 to 2 feet. Dominant period 4 seconds.', 'North winds 5 knots. Seas 1 foot. Dominant period 3 to 4 seconds.']:
            self.assertFalse(m.qualifies(self.record(body)))

    def test_waves_change_and_period_tie(self):
        self.assertFalse(m.qualifies(self.record('North winds 5 knots. Waves 1 foot or less, then 2 feet. Dominant period 4 seconds.')))
        self.assertFalse(m.qualifies(self.record('North winds 5 knots. Waves 1 foot or less. Wave Detail: North 1 foot at 3 seconds and south 1 foot at 5 seconds.')))

    def test_combined_gulf_zone_and_layout(self):
        text = 'GMZ730-751-752-755-765-770-772-775-111500-\nCoastal waters\n.TODAY...North winds 5 knots. Seas 1 foot. Dominant period 4 seconds.\n$$'
        zones = {z: m.parse_zone(body, self.issued) for z, body in m.zone_sections(text).items()}
        self.assertEqual(set(zones), {'GMZ765'})
        msg = m.format_message(zones, self.issued, self.issued)
        self.assertIn('STEINHATCHEE MARINE FORECAST', msg)
        self.assertIn('Wind: 7 mph or less', msg)
        self.assertIn('5.8 mph wind', msg)
        self.assertLessEqual(len(msg.encode()), 4096)

    def test_wind_changes_signature(self):
        r = self.record('North winds 5 mph. Seas 1 foot. Dominant period 4 seconds.')
        first = m.signature({'GMZ765': [r]}, 'wave_detail')
        r['wind_hi'] = 6
        self.assertNotEqual(first, m.signature({'GMZ765': [r]}, 'wave_detail'))

    def test_fetch_accepts_only_tallahassee(self):
        product = {'id': '11111111-1111-1111-1111-111111111111', 'issuingOffice': 'KTAE', 'wmoCollectiveId': 'FZUS52', 'productCode': 'CWF', 'issuanceTime': self.issued.isoformat()}
        with patch.object(m, 'http_json', side_effect=[{'@graph': [product]}, {'issuanceTime': self.issued.isoformat(), 'productText': 'FZUS52 KTAE 110801\nCWFTAE\n'}]):
            self.assertIn('CWFTAE', m.fetch_product(self.issued)[0])
        with patch.object(m, 'http_json', return_value={'@graph': [dict(product, issuingOffice='KJAX')]}):
            with self.assertRaises(RuntimeError):
                m.fetch_product(self.issued)
