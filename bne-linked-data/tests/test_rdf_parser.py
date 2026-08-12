import pytest

from bne_linked_data.rdf_parser import parse_ntriples_line


def test_parse_iri_object() -> None:
    triple = parse_ntriples_line(
        "<http://datos.bne.es/resource/XX1> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
        "<http://datos.bne.es/def/C1005> ."
    )
    assert triple is not None
    assert triple.subject == "http://datos.bne.es/resource/XX1"
    assert triple.object_kind == "iri"
    assert triple.language is None


def test_parse_language_literal_and_escapes() -> None:
    triple = parse_ntriples_line(
        '<http://datos.bne.es/resource/XX1> <http://www.w3.org/2000/01/rdf-schema#label> '
        '"Biblioteca \\"Nacional\\"\\nEspaña"@es .'
    )
    assert triple is not None
    assert triple.object == 'Biblioteca "Nacional"\nEspaña'
    assert triple.object_kind == "literal"
    assert triple.language == "es"


def test_parse_typed_literal_and_blank_node() -> None:
    triple = parse_ntriples_line(
        '_:node1 <http://example.org/year> "2021"^^<http://www.w3.org/2001/XMLSchema#gYear> .'
    )
    assert triple is not None
    assert triple.subject == "_:node1"
    assert triple.datatype == "http://www.w3.org/2001/XMLSchema#gYear"


@pytest.mark.parametrize("line", ["", "# comment", "   # comment"])
def test_ignore_empty_and_comment_lines(line: str) -> None:
    assert parse_ntriples_line(line) is None


def test_reject_malformed_line() -> None:
    with pytest.raises(ValueError):
        parse_ntriples_line("<http://example.org/s> <http://example.org/p> missing-period")

