"""Deterministic, unadmitted TEI study preparation. Pure bytes in/bytes out.

No file, network, model, database, translation or correction operations. Do not
replace a different preparation's pinned hashes with this distinct format.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import re
import xml.etree.ElementTree as ET

FORMAT = "jace-fresh-private-tei-study-v1"
PARSER_CONTRACT = "tei-body-overlapping-units-and-parsed-text-slots-v1"
TEI = "{http://www.tei-c.org/ns/1.0}"
XML = "{http://www.w3.org/XML/1998/namespace}"
LICENSE = "CC-BY-SA-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
MAX_SOURCE_BYTES = 1024 * 1024
MAX_NOTICE_BYTES = 64 * 1024
MAX_ELEMENTS = 20000
MAX_DEPTH = 64
MAX_RECORDS = 5000
MAX_PARTS = 100000
MAX_PARTS_PER_RECORD = 4096
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
UNIT_TAGS = frozenset(TEI + x for x in (
    "p", "note", "q", "quote", "head", "trailer", "lg", "item"))
QUOTE_TAGS = frozenset(TEI + x for x in ("q", "quote", "cit"))
LITERAL_INLINE_TAGS = frozenset(TEI + x for x in ("hi", "ref"))
SAFETY_FLAGS = (
    "scan_identity_verified", "ocr_verified", "transcription_verified",
    "scholarly_verified", "rights_verified", "reviewer_identity_verified",
    "runtime_admitted", "training_admitted", "parsed_text_is_original_byte_quotation",
)
CHANGE_NOTICE = (
    "Fresh private preparation v1, not the original 1,396-record preparation. "
    "Original XML and attribution/accession notices are retained byte-for-byte. "
    "Selected TEI body units are extracted into overlapping parsed-text records; "
    "XML line endings and predefined/numeric character references are interpreted "
    "by the parser. Comments and processing instructions are retained only in "
    "the original XML and are not executed. No correction, translation, whitespace "
    "normalization, scholarly validation, runtime admission or training admission "
    "is performed. Preserve attribution and this change notice; separately "
    "authorized sharing of adaptations must follow applicable CC BY-SA 4.0 terms."
)
WARNING = (
    "Private, unreviewed literal source study only. Mechanical identifiers and "
    "inherited language labels are not verified citations, authorship, language "
    "interpretation or doctrinal validation. This preparation does not authorize "
    "external disclosure, public publication or use by external models. The "
    "approved Sanskrit commentary is not the complete Agama canon and does not "
    "include the excluded modern Hindi translation."
)


class PreparationError(ValueError):
    """Rejected source, declaration, structure, resource bound or verification."""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


@dataclass(frozen=True)
class Declaration:
    source_sha256: str
    attribution_sha256: str
    accession_sha256: str
    accepted_license: str
    purpose: str
    opted_in: bool


@dataclass(frozen=True)
class Preparation:
    records_jsonl: bytes
    manifest_json: bytes


def _checked_bytes(raw, digest, limit, label):
    if type(raw) is not bytes or not raw or len(raw) > limit:
        raise PreparationError("Invalid bounded " + label + " bytes")
    if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise PreparationError("Invalid " + label + " digest declaration")
    if sha256(raw) != digest:
        raise PreparationError(label + " fingerprint mismatch")
    try:
        raw.decode("utf-8")
    except UnicodeError:
        raise PreparationError(label + " must be UTF-8") from None


def _parse(source):
    text = source.decode("utf-8-sig")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise PreparationError("DTD and entity declarations are not supported")
    declaration = re.match(r"<\?xml\s+([^?]*)\?>", text)
    if declaration:
        version = re.search(r"\bversion\s*=\s*(['\"])(.*?)\1", declaration[1])
        if version and version[2] != "1.0":
            raise PreparationError("Only XML 1.0 is supported")
        encoding = re.search(r"\bencoding\s*=\s*(['\"])(.*?)\1", declaration[1])
        if encoding and encoding[2].lower() not in ("utf-8", "utf8"):
            raise PreparationError("Only UTF-8 XML declarations are supported")
    # The parser does not load URLs, run processing instructions or XInclude.
    # Pull parsing enforces element/depth bounds before building an unbounded tree.
    parser = ET.XMLPullParser(events=("start", "end"))
    root = None
    count = depth = 0
    try:
        for start in range(0, len(text), 4096):
            parser.feed(text[start:start + 4096])
            for event, element in parser.read_events():
                if event == "start":
                    count += 1
                    depth += 1
                    if count > MAX_ELEMENTS or depth > MAX_DEPTH:
                        raise PreparationError("XML structure exceeds resource limit")
                    if root is None:
                        root = element
                    if not isinstance(element.tag, str) or not element.tag.startswith(TEI):
                        raise PreparationError("Only TEI namespace elements are supported")
                    if len(element.tag) > 192:
                        raise PreparationError("XML element name exceeds resource limit")
                    if any(len(k) > 512 or len(v) > 4096 for k, v in element.attrib.items()):
                        raise PreparationError("XML attribute exceeds resource limit")
                else:
                    depth -= 1
        parser.close()
    except (ET.ParseError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, PreparationError):
            raise
        raise PreparationError("Malformed or unsupported XML") from None
    if root is None or root.tag != TEI + "TEI":
        raise PreparationError("A single TEI root is required")
    if [c.tag for c in root] != [TEI + "teiHeader", TEI + "text"]:
        raise PreparationError("Exactly one direct TEI header and text are required")
    text_element = root[1]
    if [c.tag for c in text_element] != [TEI + "body"]:
        raise PreparationError("Only a single direct TEI body is supported")
    structural_slots = [root.text, root.tail, text_element.text]
    structural_slots.extend(child.tail for child in root)
    structural_slots.extend(child.tail for child in text_element)
    if any(value and value.strip() for value in structural_slots):
        raise PreparationError("Non-whitespace text outside the header/body is unsupported")
    if (sum(e.tag == TEI + "text" for e in root.iter()) != 1
            or sum(e.tag == TEI + "body" for e in root.iter()) != 1
            or sum(e.tag == TEI + "TEI" for e in root.iter()) != 1
            or sum(e.tag == TEI + "teiHeader" for e in root.iter()) != 1):
        raise PreparationError("Nested or duplicate TEI containers are unsupported")
    return root, text_element[0], count


def _structure(root):
    paths, parents, ids = {}, {}, set()

    def visit(node, path):
        if len(path) > 4096:
            raise PreparationError("XML structural path exceeds resource limit")
        paths[node] = path
        identifier = node.get(XML + "id")
        if identifier is not None:
            if not identifier or len(identifier) > 256 or identifier in ids:
                raise PreparationError("Empty, oversized or duplicate xml:id")
            ids.add(identifier)
        counters = Counter()
        for child in node:
            parents[child] = node
            counters[child.tag] += 1
            visit(child, path + "/" + child.tag + "[" + str(counters[child.tag]) + "]")

    visit(root, "/" + root.tag + "[1]")
    return paths, parents, ids


def _ancestors(node, parents):
    chain = [node]
    while node in parents:
        node = parents[node]
        chain.append(node)
    return chain


def _slots(node):
    """Yield a text slot plus its context owner. A child's tail belongs to its parent."""
    if node.text is not None:
        yield node, "text", node, node.text
    for child in node:
        yield from _slots(child)
        if child.tail is not None:
            yield child, "tail", node, child.tail


def _classification(node, chain):
    identifier = node.get(XML + "id")
    if any(e.tag in QUOTE_TAGS for e in chain):
        return "quotation_markup", "not_a_root_or_commentary_citation"
    if any(e.tag == TEI + "note" for e in chain):
        return "note_markup", "not_a_root_or_commentary_citation"
    if node.tag == TEI + "p":
        for prefix, pattern, category in (
            ("TAS_", r"TAS_[1-9][0-9]*\.[1-9][0-9]*", "root_text_label"),
            ("SAS_", r"SAS_[1-9][0-9]*[ab]?", "commentary_label"),
        ):
            if identifier and identifier.startswith(prefix):
                status = ("complete_identifier_syntax_unreviewed" if re.fullmatch(pattern, identifier)
                          else "incomplete_or_unsupported_identifier_syntax")
                return category, status
        return "unclassified_paragraph", "missing_or_unrecognized_identifier"
    return {
        TEI + "head": "heading_markup", TEI + "trailer": "trailer_markup",
        TEI + "lg": "verse_group_markup", TEI + "item": "list_item_markup",
    }[node.tag], "not_a_root_or_commentary_citation"


def prepare(source_xml: bytes, attribution: bytes, accession: bytes,
            *, declaration: Declaration) -> Preparation:
    """Extract a new format under explicit caller pins; no right is inferred."""
    if type(declaration) is not Declaration or declaration.opted_in is not True:
        raise PreparationError("Explicit per-call declaration required")
    if (declaration.accepted_license != LICENSE
            or declaration.purpose != "fresh-private-source-study"):
        raise PreparationError("Explicit license and private study purpose required")
    _checked_bytes(source_xml, declaration.source_sha256, MAX_SOURCE_BYTES, "source")
    _checked_bytes(attribution, declaration.attribution_sha256, MAX_NOTICE_BYTES, "attribution")
    _checked_bytes(accession, declaration.accession_sha256, MAX_NOTICE_BYTES, "accession")
    root, body, element_count = _parse(source_xml)
    paths, parents, ids = _structure(root)
    units = [node for node in body.iter() if node.tag in UNIT_TAGS]
    if not units or len(units) > MAX_RECORDS:
        raise PreparationError("Invalid study unit count")
    record_ids = {node: FORMAT + ":" + str(i + 1).zfill(5) for i, node in enumerate(units)}
    safety = dict.fromkeys(SAFETY_FLAGS, False)
    records, covered, wire_records = [], set(), []
    output_size = 0
    parts_count = 0
    for node in units:
        chain = _ancestors(node, parents)
        category, citation_status = _classification(node, chain)
        parts = []
        for slot_node, slot_kind, owner, value in _slots(node):
            parts_count += 1
            if parts_count > MAX_PARTS:
                raise PreparationError("Extracted text parts exceed resource limit")
            if len(parts) >= MAX_PARTS_PER_RECORD:
                raise PreparationError("Record text parts exceed resource limit")
            covered.add((slot_node, slot_kind))
            context = _ancestors(owner, parents)
            parts.append({
                "xml_path": paths[slot_node], "slot": slot_kind, "text": value,
                "within_quotation_markup": any(e.tag in QUOTE_TAGS for e in context),
                "within_note_markup": any(e.tag == TEI + "note" for e in context),
                "inherited_xml_lang": next((e.get(XML + "lang") for e in context
                                             if XML + "lang" in e.attrib), None),
            })
        parsed_text = "".join(p["text"] for p in parts)
        within_quote = any(e.tag in QUOTE_TAGS for e in chain)
        within_note = any(e.tag == TEI + "note" for e in chain)
        contains_quote = any(e.tag in QUOTE_TAGS for e in node.iter())
        contains_note = any(e.tag == TEI + "note" for e in node.iter())
        contains_nested_units = any(e is not node and e.tag in UNIT_TAGS for e in node.iter())
        contextual_tags = sorted({e.tag for e in node.iter()
                                  if e is not node and e.tag not in LITERAL_INLINE_TAGS})
        candidate = (category in ("root_text_label", "commentary_label")
                     and citation_status == "complete_identifier_syntax_unreviewed"
                     and not (within_quote or within_note or contains_quote or contains_note
                              or contains_nested_units or contextual_tags)
                     and bool(parsed_text.strip()))
        records.append({
            "format": FORMAT, "id": record_ids[node],
            "source_sha256": declaration.source_sha256,
            "source_xml_path": paths[node], "source_xml_id": node.get(XML + "id"),
            "element_tag": node.tag, "category": category,
            "citation_status": citation_status,
            "inherited_xml_lang": next((e.get(XML + "lang") for e in chain
                                         if XML + "lang" in e.attrib), None),
            "containing_record_ids": [record_ids[e] for e in reversed(chain[1:]) if e in record_ids],
            "parsed_text": parsed_text, "parsed_text_sha256": sha256(parsed_text.encode("utf-8")),
            "parsed_text_parts": parts, "within_quotation_markup": within_quote,
            "contains_quotation_markup": contains_quote, "within_note_markup": within_note,
            "contains_note_markup": contains_note,
            "contains_nested_study_units": contains_nested_units,
            "contextual_markup_tags": contextual_tags,
            "candidate_for_literal_study": candidate, "safety": safety.copy(),
            "license": LICENSE, "attribution_sha256": declaration.attribution_sha256,
            "accession_sha256": declaration.accession_sha256,
        })
        wire = canonical(records[-1]) + b"\n"
        output_size += len(wire)
        if output_size > MAX_OUTPUT_BYTES:
            raise PreparationError("Prepared records exceed output limit")
        wire_records.append(wire)
    all_slots = list(_slots(body))
    uncovered = [(n, k, value) for n, k, _, value in all_slots if (n, k) not in covered]
    if any(value.strip() for _, _, value in uncovered):
        raise PreparationError("Unsupported non-whitespace body text outside selected units")
    records_bytes = b"".join(wire_records)
    if len(records_bytes) > MAX_OUTPUT_BYTES:
        raise PreparationError("Prepared records exceed output limit")
    manifest = {
        "format": FORMAT, "parser_contract": PARSER_CONTRACT,
        "lineage": "new_preparation_not_original_1396_record_preparation",
        "provenance_status": "structural_source_binding_only",
        "source_sha256": declaration.source_sha256, "source_bytes": len(source_xml),
        "records_sha256": sha256(records_bytes), "records_bytes": len(records_bytes),
        "attribution_sha256": declaration.attribution_sha256,
        "accession_sha256": declaration.accession_sha256,
        "license": LICENSE, "license_url": LICENSE_URL,
        "rights_assertion": "caller_declared_existing_approval_not_independent_verification",
        "required_companions": ["original.xml", "ATTRIBUTION.md", "accession.json", "CHANGES.txt"],
        "change_notice": CHANGE_NOTICE, "change_notice_sha256": sha256(CHANGE_NOTICE.encode("utf-8")),
        "warning": WARNING, "records_can_overlap": True,
        "header_preserved_in_original_only": True,
        "parsed_parts_are_byte_offsets": False,
        "limits": {
            "source_bytes": MAX_SOURCE_BYTES, "each_notice_bytes": MAX_NOTICE_BYTES,
            "xml_elements": MAX_ELEMENTS, "xml_depth": MAX_DEPTH, "records": MAX_RECORDS,
            "text_parts_total": MAX_PARTS, "text_parts_per_record": MAX_PARTS_PER_RECORD,
            "output_records_bytes": MAX_OUTPUT_BYTES, "element_name_characters": 192,
            "structural_path_characters": 4096, "attribute_name_characters": 512,
            "attribute_value_characters": 4096, "xml_id_characters": 256,
        },
        "safety": safety.copy(),
        "counts": {
            "xml_elements": element_count, "xml_ids": len(ids),
            "records": len(records), "categories": dict(sorted(Counter(r["category"] for r in records).items())),
            "literal_study_candidates": sum(r["candidate_for_literal_study"] for r in records),
            "incomplete_or_unsupported_root_commentary_ids": sum(
                r["citation_status"] == "incomplete_or_unsupported_identifier_syntax" for r in records),
            "overlapping_records": sum(bool(r["containing_record_ids"]) for r in records),
            "extracted_text_parts_with_overlap": parts_count,
            "body_text_slots": len(all_slots), "covered_body_text_slots": len(covered),
            "unrepresented_whitespace_slots": len(uncovered),
            "unrepresented_non_whitespace_slots": 0,
        },
    }
    return Preparation(records_bytes, canonical(manifest) + b"\n")


def verify(source_xml: bytes, attribution: bytes, accession: bytes,
           preparation: Preparation, *, declaration: Declaration) -> dict:
    """Regenerate under external source pins and compare every output byte."""
    if type(preparation) is not Preparation:
        raise PreparationError("A preparation value is required")
    if (type(preparation.records_jsonl) is not bytes
            or len(preparation.records_jsonl) > MAX_OUTPUT_BYTES
            or type(preparation.manifest_json) is not bytes
            or len(preparation.manifest_json) > MAX_NOTICE_BYTES):
        raise PreparationError("Invalid bounded preparation bytes")
    expected = prepare(source_xml, attribution, accession, declaration=declaration)
    if (expected.records_jsonl != preparation.records_jsonl
            or expected.manifest_json != preparation.manifest_json):
        raise PreparationError("Preparation does not exactly reproduce from pinned source")
    return json.loads(expected.manifest_json)
