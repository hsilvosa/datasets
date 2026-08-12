import unittest

from ign_earthquakes.normalize import (
    intensity_numeric,
    location_country,
    parse_csv,
    parse_html,
    repair_mojibake,
)


class NormalizeTests(unittest.TestCase):
    def test_parses_and_limits_rows(self):
        content = (
            b"Evento;Fecha;Hora;Latitud;Longitud;Prof.;Inten.;Mag.;Tipo;Lugar\n"
            b" es2026a;01/08/2026;02:52:42;41.1;0.1;11.0;;1.2;4;W TEST.TE\n"
            b" es2026b;01/08/2026;03:00:00;42.0;-1.0;5.0;4.0;2.0;4;N TEST.Z\n"
        )
        rows = parse_csv(content, max_rows=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_id"], "es2026a")
        self.assertEqual(rows[0]["occurred_at_utc"], "2026-08-01T02:52:42Z")
        self.assertIsNone(rows[0]["maximum_intensity"])

    def test_repairs_common_double_utf8(self):
        broken = "MAZALEÓN".encode().decode("latin-1")
        self.assertEqual(repair_mojibake(broken), "MAZALEÓN")

    def test_converts_roman_intensity_range(self):
        self.assertEqual(intensity_numeric("VIII-IX"), 8.5)

    def test_parses_html_fallback_row(self):
        content = b"""
        <table><tr><td>es1427aaaaa</td><td>23/04/1427</td><td>11:00:00</td>
        <td></td><td>41.9833</td><td>2.5833</td><td></td><td></td>
        <td>null</td><td>-1</td><td>SW AMER.GI</td><td></td></tr></table>
        """
        rows = parse_html(content)
        self.assertEqual(rows[0]["event_id"], "es1427aaaaa")
        self.assertEqual(rows[0]["latitude"], 41.9833)
        self.assertIsNone(rows[0]["maximum_intensity_numeric"])
        self.assertEqual(rows[0]["source_format"], "html_fallback")

    def test_derives_country_from_ign_location_suffix(self):
        self.assertEqual(location_country("NW LA MONGIE.FRA"), ("FR", "France"))
        self.assertEqual(location_country("NE MONCHIQUE.POR"), ("PT", "Portugal"))
        self.assertEqual(location_country("SE GRANADA.GR"), ("ES", "Spain"))
        self.assertEqual(
            location_country("O Santa Cruz de la Palma.LP,Isla de La Palma"),
            ("ES", "Spain"),
        )
        self.assertEqual(location_country("W. Lisboa"), (None, None))
        self.assertEqual(location_country("GOLFO DE CÁDIZ"), (None, None))


if __name__ == "__main__":
    unittest.main()
