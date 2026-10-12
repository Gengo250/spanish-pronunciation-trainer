import pytest

from sptrainer.assessment.g2p import (
    flatten,
    phoneme_word_map,
    phonemize_text,
    phonemize_word,
    tokenize_ipa,
)


def test_ch_is_a_single_phoneme():
    assert "tʃ" in phonemize_word("muchacho").phonemes


def test_stress_index_points_at_the_stressed_vowel():
    word = phonemize_word("gustaría")
    assert word.phonemes[word.stressed_index] == "i"


def test_stress_marks_are_not_phonemes():
    phones, _ = tokenize_ipa("ɡɾˈaθjas")
    assert "ˈ" not in phones and "ˌ" not in phones


def test_punctuation_does_not_glue_words_together():
    """O espeak atravessa virgula em frase inteira; por palavra, nao."""
    words = phonemize_text("cansado, decidió")
    assert [w.word for w in words] == ["cansado", "decidió"]


def test_accent_changes_the_reference():
    """Distincion na Espanha, seseo na America."""
    assert "θ" in phonemize_word("gracias", "es").phonemes
    assert "θ" not in phonemize_word("gracias", "es-419").phonemes
    assert "ʎ" in phonemize_word("llave", "es").phonemes
    assert "ʝ" in phonemize_word("llave", "es-419").phonemes


def test_phoneme_word_map_has_one_entry_per_phoneme():
    words = phonemize_text("Hola amigo")
    assert len(phoneme_word_map(words)) == len(flatten(words))
    assert set(phoneme_word_map(words)) == {0, 1}


@pytest.mark.parametrize("text", ["", "   ", "¿?"])
def test_empty_input_yields_nothing(text):
    assert phonemize_text(text) == []
