"""The optional LLM-source fold-in (app.rijal.llm_source) and its pipeline hook — all GATED, so
without the files the pipeline is byte-for-byte the regex pipeline."""

from __future__ import annotations

import json

from app.parsing.hadith_extract import parse_book_file
from app.rijal.index import RijalIndex
from app.rijal.llm_source import (
    llm_associations, load_llm_chains, load_llm_rijal, text_key,
)


def test_load_llm_rijal_into_rijal_shape(tmp_path):
    p = tmp_path / "rijal_llm.jsonl"
    p.write_text(json.dumps(
        {"name": "مالك بن أنس", "grade_word": "الإمام", "category": "ثقة",
         "kunya": "أبو عبد الله", "death_year": 179, "shuyukh": ["نافع"], "talamidh": ["الشافعي"]},
        ensure_ascii=False) + "\n", encoding="utf-8")
    rec = load_llm_rijal(p)[0]
    assert rec["name"] == "مالك بن أنس" and rec["grade"] == "الإمام"   # grade = verbatim word
    assert rec["kunya"] == "أبو عبد الله" and rec["death_year"] == 179
    assert "shuyukh" not in rec                                         # network is for the graph, not the record


def test_llm_associations_only_for_unambiguous_men(tmp_path):
    p = tmp_path / "rijal_llm.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"name": "مالك بن أنس الأصبحي", "shuyukh": ["نافع", "الزهري"], "talamidh": ["الشافعي"]},
        {"name": "سفيان", "shuyukh": ["منصور"]},   # ambiguous → contributes no company
    ]) + "\n", encoding="utf-8")
    rijal = RijalIndex([
        {"name": "مالك بن أنس الأصبحي", "grade": "ثقة"},
        {"name": "سفيان الثوري", "grade": "ثقة"}, {"name": "سفيان بن عيينة", "grade": "ثقة"},
    ])
    assoc = llm_associations(p, rijal)
    assert "نافع" in assoc["مالك بن أنس الأصبحي"]          # company of an unambiguous man is added
    assert not any("سفيان" in k for k in assoc)            # ambiguous «سفيان» is skipped


def test_load_llm_chains_keyed_by_text(tmp_path):
    p = tmp_path / "chains_llm.jsonl"
    p.write_text(json.dumps(
        {"source_text": "حدثنا قتيبة عن مالك", "isnad": "حدثنا قتيبة عن مالك", "matn": "",
         "narrators": ["قتيبة", "مالك"]}, ensure_ascii=False) + "\n", encoding="utf-8")
    m = load_llm_chains(p)
    assert text_key("حدثنا قتيبة عن مالك") in m
    assert text_key("حدثنا  قتيبة عن مالكٍ") in m            # whitespace/tashkeel-stable key


def test_parse_book_file_chain_override_is_gated(tmp_path):
    book = tmp_path / "9.json"
    book.write_text(json.dumps(
        {"book_id": 9, "pages": [{"pg": 1, "text": "١- حدثنا قتيبة عن مالك عن نافع عن ابن عمر قال إنما الأعمال"}]},
        ensure_ascii=False), encoding="utf-8")
    base = parse_book_file(book)                            # no map → ordinary regex parse
    assert base and base[0].matn_confidence != "llm"
    over = parse_book_file(book, llm_chains={
        text_key(base[0].text): {"isnad": "إسناد مُصحَّح", "matn": "متن", "narrators": []}})
    assert over[0].isnad == "إسناد مُصحَّح" and over[0].matn_confidence == "llm"
