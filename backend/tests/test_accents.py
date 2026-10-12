"""Valid variation must not become an error -- and a minimal pair must not become an equivalence."""

import pytest

from sptrainer.assessment.accents import (
    collapse_geminates,
    equivalence_reason,
    equivalent,
    is_model_artifact,
)


@pytest.mark.parametrize(
    "a,b,reason",
    [
        ("θ", "s", "regional"),      # seseo vs distincion: "gracias"
        ("ʎ", "ʝ", "regional"),      # lleismo vs yeismo: "llave"
        ("x", "h", "regional"),      # jota caribenha: "trabajo"
        ("s", "h", "regional"),      # aspiracao de coda: "ehto"
        ("b", "β", "allophonic"),    # "lobo"
        ("d", "ð", "allophonic"),    # "nada"
        ("ɡ", "ɣ", "allophonic"),    # "lago"
        ("n", "ŋ", "allophonic"),    # "tengo"
        ("ɾ", "r", "model_artifact"),
    ],
)
def test_valid_variation_is_not_an_error(a, b, reason):
    assert equivalent(a, b)
    assert equivalence_reason(a, b) == reason


@pytest.mark.parametrize(
    "a,b,why",
    [
        ("n", "m", "cama vs cana"),
        ("s", "x", "casa vs caja -- must not chain through /h/"),
        ("s", "k", "casa vs caca"),
        ("p", "b", "pata vs bata"),
        ("t", "d", "tos vs dos"),
        ("a", "e", "vogais distintas"),
        ("l", "r", "pelo vs pero"),
    ],
)
def test_real_minimal_pairs_stay_distinct(a, b, why):
    assert not equivalent(a, b), why


def test_equivalence_is_not_transitive():
    """s~h and x~h hold, but s~x must not -- otherwise casa == caja."""
    assert equivalent("s", "h") and equivalent("x", "h")
    assert not equivalent("s", "x")


def test_jota_confusion_is_flagged_as_model_artifact():
    assert is_model_artifact("x", "k")
    assert not is_model_artifact("x", "p")


def test_geminate_trill_collapses():
    assert collapse_geminates(list("peɾɾo")) == list("peɾo")
    assert collapse_geminates(list("kasa")) == list("kasa")
