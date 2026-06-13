from icoder.experts.coding_expert import CodingExpert

exp = CodingExpert()


def test_search_synonym():
    hits = exp.search("慢性心衰")
    assert hits and hits[0]["code"] == "I50.900"


def test_verify_notes():
    v = exp.verify("J18.900")
    assert v is not None
    kinds = {n.kind for n in v["notes"]}
    assert "excludes1" in kinds


def test_verify_unknown_is_none():
    assert exp.verify("ZZZ.000") is None


def test_guidelines_present():
    assert exp.guidelines("M80.900")["guideline"]


def test_explore_hierarchy():
    e = exp.explore("N18.900")
    assert "N18.500" in e["children"]


def test_alternatives_high_risk():
    alts = exp.alternatives("M80.900")
    assert any(a.code == "M81.900" for a in alts)


def test_find_evidences_exact_offsets():
    text = "患者有肺炎，肺炎复发"
    evs = exp.find_evidences(text, "肺炎")
    assert len(evs) == 2
    for ev in evs:
        assert text[ev.start:ev.end] == ev.text == "肺炎"
