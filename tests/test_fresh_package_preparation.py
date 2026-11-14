"""Fictional fixtures only. No real source text, network or model calls."""
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from jace._fresh_study import preparation as f


ATTRIBUTION = b"Fictional fixture attribution; no real source passages."
ACCESSION = b'{"fixture":true,"license":"CC-BY-SA-4.0"}'


def xml(body, *, header="<teiHeader/>", attrs="", preamble=""):
    return (preamble + '<TEI xmlns="http://www.tei-c.org/ns/1.0" ' + attrs + '>'
            + header + '<text xml:lang="sa-Latn"><body>' + body
            + '</body></text></TEI>').encode("utf-8")


def declaration(raw):
    return f.Declaration(f.sha256(raw), f.sha256(ATTRIBUTION), f.sha256(ACCESSION),
                         f.LICENSE, "fresh-private-source-study", True)


def prepare(raw):
    return f.prepare(raw, ATTRIBUTION, ACCESSION, declaration=declaration(raw))


def records(prep):
    return [json.loads(line) for line in prep.records_jsonl.splitlines()]


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.raw = xml('<p xml:id="TAS_1.1">fixture root</p>'
                       '<p xml:id="SAS_1">fixture explanation</p>')

    def test_deterministic_and_verified(self):
        a, b = prepare(self.raw), prepare(self.raw)
        self.assertEqual(a, b)
        manifest = f.verify(self.raw, ATTRIBUTION, ACCESSION, a,
                            declaration=declaration(self.raw))
        self.assertEqual(manifest["counts"]["records"], 2)
        self.assertEqual(manifest["counts"]["literal_study_candidates"], 2)
        self.assertEqual(manifest["source_sha256"], f.sha256(self.raw))
        self.assertEqual(manifest["records_sha256"], f.sha256(a.records_jsonl))
        self.assertIn("not_original_1396", manifest["lineage"])

    def test_all_safety_flags_false(self):
        result = prepare(self.raw)
        for item in records(result) + [json.loads(result.manifest_json)]:
            self.assertEqual(item["safety"], dict.fromkeys(f.SAFETY_FLAGS, False))

    def test_explicit_declaration(self):
        d = declaration(self.raw)
        for changed in (None, {}, replace(d, opted_in=False), replace(d, opted_in=1),
                        replace(d, purpose="training"), replace(d, accepted_license="CC0")):
            with self.subTest(changed=changed), self.assertRaises(f.PreparationError):
                f.prepare(self.raw, ATTRIBUTION, ACCESSION, declaration=changed)

    def test_pins_cover_all_inputs(self):
        for args in ((self.raw + b" ", ATTRIBUTION, ACCESSION),
                     (self.raw, ATTRIBUTION + b" ", ACCESSION),
                     (self.raw, ATTRIBUTION, ACCESSION + b" ")):
            with self.subTest(), self.assertRaises(f.PreparationError):
                f.prepare(*args, declaration=declaration(self.raw))

    def test_types_and_digests(self):
        d = declaration(self.raw)
        for field in ("source_sha256", "attribution_sha256", "accession_sha256"):
            for value in ("A" * 64, "x", None, 0):
                with self.subTest(field=field, value=value), self.assertRaises(f.PreparationError):
                    f.prepare(self.raw, ATTRIBUTION, ACCESSION,
                              declaration=replace(d, **{field: value}))
        for value in (bytearray(self.raw), self.raw.decode(), b"", None):
            with self.subTest(), self.assertRaises(f.PreparationError):
                f.prepare(value, ATTRIBUTION, ACCESSION, declaration=d)

    def test_utf8_bom_exact_bytes(self):
        a = prepare(self.raw)
        raw = b"\xef\xbb\xbf" + self.raw
        b = prepare(raw)
        self.assertNotEqual(a, b)
        self.assertEqual([r["parsed_text"] for r in records(a)],
                         [r["parsed_text"] for r in records(b)])
        self.assertEqual(json.loads(b.manifest_json)["source_sha256"], f.sha256(raw))

    def test_xml_line_end_and_character_reference_semantics(self):
        raw = xml('<p xml:id="TAS_1.1">A\r\nB\rC &amp; &#x3A9; e\u0301</p>')
        r = records(prepare(raw))[0]
        self.assertEqual(r["parsed_text"], "A\nB\nC & Ω e\u0301")
        self.assertFalse(r["safety"]["parsed_text_is_original_byte_quotation"])
        self.assertEqual(r["parsed_text_sha256"], f.sha256(r["parsed_text"].encode()))

    def test_mixed_content_tails_and_roles(self):
        raw = xml('<p xml:id="TAS_1.1">before <q>quoted <hi>inner</hi> qtail</q>'
                  ' after <note xml:lang="en">note <hi>label</hi> tail</note> end</p>')
        rs = records(prepare(raw))
        self.assertEqual(len(rs), 3)
        p, q, note = rs
        self.assertEqual(p["parsed_text"], "before quoted inner qtail after note label tail end")
        self.assertEqual(q["parsed_text"], "quoted inner qtail")
        self.assertEqual(note["parsed_text"], "note label tail")
        self.assertFalse(p["candidate_for_literal_study"])
        self.assertEqual(q["containing_record_ids"], [p["id"]])
        self.assertEqual(note["containing_record_ids"], [p["id"]])
        for part in p["parsed_text_parts"]:
            if part["text"] == " after ":
                self.assertEqual(part["slot"], "tail")
                self.assertFalse(part["within_quotation_markup"])
                self.assertFalse(part["within_note_markup"])
            if part["text"] == "label":
                self.assertTrue(part["within_note_markup"])
                self.assertEqual(part["inherited_xml_lang"], "en")

    def test_within_ancestor_quote_blocks_candidate(self):
        raw = xml('<q><p xml:id="TAS_1.1">root-like fixture</p></q>')
        rs = records(prepare(raw))
        self.assertTrue(all(not r["candidate_for_literal_study"] for r in rs))
        self.assertTrue(all(r["within_quotation_markup"] for r in rs))
        self.assertEqual(rs[1]["category"], "quotation_markup")

    def test_cit_ancestor_and_tail(self):
        raw = xml('<p xml:id="SAS_1">a<cit><hi>b</hi></cit>c</p>')
        r = records(prepare(raw))[0]
        self.assertFalse(r["candidate_for_literal_study"])
        self.assertTrue(r["contains_quotation_markup"])
        self.assertTrue(r["parsed_text_parts"][1]["within_quotation_markup"])
        self.assertFalse(r["parsed_text_parts"][2]["within_quotation_markup"])

    def test_notes_stay_distinct_from_commentary(self):
        raw = xml('<note><p xml:id="SAS_1">note fixture</p></note>')
        for r in records(prepare(raw)):
            self.assertEqual(r["category"], "note_markup")
            self.assertFalse(r["candidate_for_literal_study"])

    def test_identifier_syntax(self):
        ids = ("TAS_1.1", "TAS_1.", "TAS_0.1", "TAS_01.1", "SAS_1", "SAS_1a",
               "SAS_1b", "SAS_1c", "SAS_", "OTHER_1", None)
        raw = xml("".join('<p' + ((' xml:id="' + i + '"') if i else '') + '>fixture</p>' for i in ids))
        self.assertEqual([r["candidate_for_literal_study"] for r in records(prepare(raw))],
                         [True, False, False, False, True, True, True, False, False, False, False])

    def test_duplicate_ids_anywhere_rejected(self):
        for raw in (xml('<p xml:id="same">a</p><p xml:id="same">b</p>'),
                    xml('<p xml:id="same">b</p>', header='<teiHeader xml:id="same"/>'),
                    xml('<p xml:id="">a</p>')):
            with self.subTest(), self.assertRaises(f.PreparationError):
                prepare(raw)

    def test_all_selected_body_units(self):
        raw = xml('<head>heading</head><lg><l>verse one</l><l>verse two</l></lg>'
                  '<list><item>item <note>annotation</note> tail</item></list><trailer>end</trailer>')
        rs = records(prepare(raw))
        self.assertEqual([r["category"] for r in rs],
                         ["heading_markup", "verse_group_markup", "list_item_markup", "note_markup", "trailer_markup"])
        self.assertEqual(rs[1]["parsed_text"], "verse oneverse two")
        self.assertTrue(all(not r["candidate_for_literal_study"] for r in rs))

    def test_no_added_separators_or_normalization(self):
        raw = xml('<p xml:id="SAS_1">  a<hi>b</hi>c\t\n  </p>')
        r = records(prepare(raw))[0]
        self.assertEqual(r["parsed_text"], "  abc\t\n  ")
        self.assertEqual("".join(p["text"] for p in r["parsed_text_parts"]), r["parsed_text"])

    def test_empty_and_nested_paragraphs_not_candidates(self):
        raw = xml('<p xml:id="TAS_1.1"> </p><p xml:id="SAS_1"><p>nested</p></p>')
        self.assertTrue(all(not r["candidate_for_literal_study"] for r in records(prepare(raw))))

    def test_paths_sibling_indexed_by_qualified_tag(self):
        raw = xml('<p>a</p><head>x</head><p>b</p><div><p>c</p></div>')
        rs = records(prepare(raw))
        self.assertTrue(rs[2]["source_xml_path"].endswith(f.TEI + "p[2]"))
        self.assertTrue(rs[3]["source_xml_path"].endswith(f.TEI + "div[1]/" + f.TEI + "p[1]"))
        self.assertEqual(len(set(r["source_xml_path"] for r in rs)), len(rs))

    def test_header_not_a_study_record(self):
        raw = xml('<p>body fixture</p>', header='<teiHeader><p>header fixture</p></teiHeader>')
        rs = records(prepare(raw))
        self.assertEqual(len(rs), 1)
        self.assertNotIn("header fixture", rs[0]["parsed_text"])

    def test_comments_and_processing_instructions_not_interpreted(self):
        raw = xml('<p xml:id="SAS_1">a<!--comment--><?unknown remote="http://invalid.invalid"?>b</p>',
                  preamble='<?xml version="1.0" encoding="UTF-8"?><?xml-model href="http://invalid.invalid"?>')
        self.assertEqual(records(prepare(raw))[0]["parsed_text"], "ab")

    def test_uncovered_nonwhitespace_fails_closed(self):
        for body in ('orphan<p>unit</p>', '<p>unit</p>orphan', '<div>orphan<p>unit</p></div>',
                     '<unknown>orphan</unknown><p>unit</p>'):
            with self.subTest(body=body), self.assertRaises(f.PreparationError):
                prepare(xml(body))
        manifest = json.loads(prepare(xml(' \n<p>a</p> \t')).manifest_json)
        self.assertEqual(manifest["counts"]["unrepresented_whitespace_slots"], 2)

    def test_dtd_entities_and_xinclude_rejected(self):
        for raw in (xml('<p>&custom;</p>', preamble='<!DOCTYPE TEI [<!ENTITY custom "expanded">]>'),
                    xml('<p>x</p>', preamble='<!DOCTYPE TEI SYSTEM "http://invalid.invalid/source.dtd">'),
                    xml('<p>x</p><xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="/etc/passwd"/>')):
            with self.subTest(), self.assertRaises(f.PreparationError):
                prepare(raw)

    def test_non_tei_or_alternate_containers_rejected(self):
        values = [b'<TEI><teiHeader/><text><body><p>x</p></body></text></TEI>',
                  xml('<p xmlns="urn:foreign">x</p>'),
                  self.raw.replace(b'<text ', b'<group ').replace(b'</text>', b'</group>'),
                  self.raw.replace(b'<body>', b'<front/><body>'),
                  self.raw.replace(b'<teiHeader/>', b'<teiHeader/><teiHeader/>'),
                  xml('<div><body><p>x</p></body></div>'),
                  xml('<p>x</p>', header='<teiHeader><text/></teiHeader>')]
        for raw in values:
            with self.subTest(), self.assertRaises(f.PreparationError):
                prepare(raw)

    def test_bad_encoding_malformed_and_trailing_garbage(self):
        for raw in (b'\xff', self.raw.decode().encode('utf-16'),
                    xml('<p>x</p>', preamble='<?xml version="1.0" encoding="ISO-8859-1"?>'),
                    xml('<p>'), self.raw + b'garbage', self.raw + self.raw):
            with self.subTest(), self.assertRaises(f.PreparationError):
                prepare(raw)

    def test_resource_bounds(self):
        changes = (("MAX_SOURCE_BYTES", len(self.raw) - 1), ("MAX_NOTICE_BYTES", 1),
                   ("MAX_ELEMENTS", 3), ("MAX_DEPTH", 3), ("MAX_RECORDS", 1),
                   ("MAX_PARTS", 1), ("MAX_PARTS_PER_RECORD", 0), ("MAX_OUTPUT_BYTES", 1))
        for name, value in changes:
            with self.subTest(name=name), patch.object(f, name, value), self.assertRaises(f.PreparationError):
                prepare(self.raw)

    def test_no_records_fails(self):
        with self.assertRaises(f.PreparationError):
            prepare(xml('  '))

    def test_large_attributes_and_identifiers_rejected(self):
        for body in ('<p xml:id="' + 'a' * 257 + '">x</p>',
                     '<p custom="' + 'a' * 4097 + '">x</p>',
                     '<p><' + 'a' * 193 + '/></p>'):
            with self.subTest(), self.assertRaises(f.PreparationError):
                prepare(xml(body))

    def test_verification_rejects_rehashed_record_forgery(self):
        a = prepare(self.raw)
        rs = records(a)
        for mutation in ('parsed_text', 'source_xml_path', 'citation_status', 'safety', 'text_part'):
            modified = json.loads(json.dumps(rs))
            if mutation == 'safety':
                modified[0]['safety']['runtime_admitted'] = True
            elif mutation == 'text_part':
                modified[0]['parsed_text_parts'][0]['within_note_markup'] = True
            else:
                modified[0][mutation] = 'forged fixture'
            wire = b''.join(f.canonical(r) + b'\n' for r in modified)
            manifest = json.loads(a.manifest_json)
            manifest['records_sha256'] = f.sha256(wire)
            manifest['records_bytes'] = len(wire)
            with self.subTest(mutation=mutation), self.assertRaises(f.PreparationError):
                f.verify(self.raw, ATTRIBUTION, ACCESSION,
                         f.Preparation(wire, f.canonical(manifest) + b'\n'),
                         declaration=declaration(self.raw))

    def test_verification_rejects_manifest_tampering_and_formatting(self):
        a = prepare(self.raw)
        for b in (f.Preparation(a.records_jsonl + b'\n', a.manifest_json),
                  f.Preparation(a.records_jsonl, a.manifest_json + b' '),
                  f.Preparation(a.records_jsonl, a.manifest_json.replace(b'false', b'true', 1)),
                  f.Preparation(a.records_jsonl.decode(), a.manifest_json), None):
            with self.subTest(), self.assertRaises(f.PreparationError):
                f.verify(self.raw, ATTRIBUTION, ACCESSION, b, declaration=declaration(self.raw))

    def test_fresh_format_is_not_old_adapter_format(self):
        r = records(prepare(self.raw))[0]
        self.assertNotIn('text', r)
        self.assertNotIn('source_text_parts', r)
        self.assertIn('fresh-private-tei-study-v1', r['format'])

    def test_structural_container_text_cannot_disappear(self):
        for raw in (self.raw.replace(b'<teiHeader/>', b'orphan<teiHeader/>'),
                    self.raw.replace(b'<teiHeader/>', b'<teiHeader/>orphan'),
                    self.raw.replace(b'<body>', b'orphan<body>'),
                    self.raw.replace(b'</body>', b'</body>orphan'),
                    self.raw.replace(b'</text>', b'</text>orphan')):
            with self.subTest(), self.assertRaises(f.PreparationError):
                prepare(raw)

    def test_contextual_and_editorial_markup_blocks_candidates(self):
        for markup in ('<choice><sic>wrng</sic><corr>right</corr></choice>',
                       '<app><lem>one</lem><rdg>two</rdg></app>', '<del>deleted</del>',
                       '<add>added</add>', '<supplied>supplied</supplied>', '<unclear>unclear</unclear>',
                       '<gap/>', '<lb/>', '<pb/>', '<unknown>unspecified</unknown>'):
            with self.subTest(markup=markup):
                r = records(prepare(xml('<p xml:id="SAS_1">before' + markup + 'after</p>')))[0]
                self.assertFalse(r['candidate_for_literal_study'])
                self.assertTrue(r['contextual_markup_tags'])
        r = records(prepare(xml('<p xml:id="SAS_1">a<hi>b</hi><ref target="#fixture">c</ref></p>')))[0]
        self.assertTrue(r['candidate_for_literal_study'])
        self.assertEqual(r['contextual_markup_tags'], [])

    def test_manifest_declares_resource_limits(self):
        limits = json.loads(prepare(self.raw).manifest_json)['limits']
        self.assertEqual(limits['source_bytes'], f.MAX_SOURCE_BYTES)
        self.assertEqual(limits['xml_depth'], f.MAX_DEPTH)
        self.assertEqual(limits['text_parts_per_record'], f.MAX_PARTS_PER_RECORD)
        self.assertEqual(limits['output_records_bytes'], f.MAX_OUTPUT_BYTES)

    def test_non_xml_10_rejected(self):
        with self.assertRaises(f.PreparationError):
            prepare(xml('<p>x</p>', preamble='<?xml version="1.1"?>'))


if __name__ == '__main__':
    unittest.main()
