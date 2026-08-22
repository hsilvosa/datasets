from omie_electricity.normalize import parse_curva_pbc_file, parse_omie_marginal_line


def test_parse_marginal_line():
    line = "2024;01;01;1;55,40;55,40;"
    res = parse_omie_marginal_line(line)
    assert res is not None
    assert res["year"] == 2024
    assert res["hour"] == 1
    assert res["price_es"] == 55.40
