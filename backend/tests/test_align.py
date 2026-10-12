from sptrainer.assessment.align import Op, accuracy, align, error_rate


def test_identical_sequences_have_no_errors():
    pairs = align(list("kasa"), list("kasa"))
    assert all(p.op is Op.MATCH for p in pairs)
    assert error_rate(list("kasa"), list("kasa")) == 0.0


def test_regional_variant_scores_perfect():
    """'gracias' com seseo e com distincion valem o mesmo."""
    distincion = ["ɡ", "ɾ", "a", "θ", "j", "a", "s"]
    seseo = ["ɡ", "ɾ", "a", "s", "j", "a", "s"]
    assert accuracy(distincion, seseo) == 1.0
    assert any(p.op is Op.EQUIVALENT for p in align(distincion, seseo))


def test_substitution_is_detected():
    pairs = align(list("kasa"), list("kesa"))
    subs = [p for p in pairs if p.op is Op.SUBSTITUTION]
    assert len(subs) == 1
    assert (subs[0].expected, subs[0].heard) == ("a", "e")


def test_deletion_and_insertion():
    assert any(p.op is Op.DELETION for p in align(list("sol"), list("so")))
    assert any(p.op is Op.INSERTION for p in align(list("so"), list("sol")))


def test_empty_expected_sequence():
    assert error_rate([], []) == 0.0
    assert error_rate([], ["a"]) == 1.0


def test_accuracy_is_clamped():
    assert 0.0 <= accuracy(list("a"), list("bcdefgh")) <= 1.0
