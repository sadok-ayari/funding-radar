import unittest

from radar.textutil import (
    days_between, find_deadline, parse_amount, parse_loose_date, strip_html, to_iso,
)


class TextUtilTests(unittest.TestCase):
    def test_strip_html_collapses_markup_and_entities(self):
        self.assertEqual(
            strip_html("<p>Grants of up to <b>USD 500,000</b> &amp; more.</p>"),
            "Grants of up to USD 500,000 & more.",
        )

    def test_rfc822_date(self):
        self.assertEqual(to_iso("Mon, 10 Nov 2026 09:00:00 +0000"), "2026-11-10")

    def test_offset_iso_date_is_normalised_to_utc(self):
        self.assertEqual(to_iso("2026-11-09+01:00"), "2026-11-09")
        self.assertEqual(to_iso("2026-11-09T00:30:00+02:00"), "2026-11-08")

    def test_prose_dates(self):
        self.assertEqual(parse_loose_date("30 November 2026"), "2026-11-30")
        self.assertEqual(parse_loose_date("30 Nov 2026"), "2026-11-30")
        self.assertEqual(parse_loose_date("November 30, 2026"), "2026-11-30")
        self.assertIsNone(parse_loose_date("sometime next spring"))

    def test_deadline_is_found_only_near_a_deadline_phrase(self):
        text = "Published 10 November 2026. Deadline: 15 December 2026."
        self.assertEqual(find_deadline(text), "2026-12-15")
        self.assertIsNone(find_deadline("Published 10 November 2026."))

    def test_amounts(self):
        self.assertEqual(parse_amount("up to USD 500,000 in grants"), (500000.0, "USD"))
        self.assertEqual(parse_amount("a €1.2 million envelope"), (1200000.0, "EUR"))
        self.assertEqual(parse_amount("EUR 1.200.000 total"), (1200000.0, "EUR"))
        self.assertEqual(parse_amount("no money mentioned here"), (None, None))
        # A bare small number is not a grant size.
        self.assertEqual(parse_amount("3 grants of $500"), (None, None))

    def test_days_between(self):
        self.assertEqual(days_between("2026-11-20", "2026-11-12"), 8)
        self.assertEqual(days_between("2026-11-01", "2026-11-12"), -11)
        self.assertIsNone(days_between(None, "2026-11-12"))


if __name__ == "__main__":
    unittest.main()
