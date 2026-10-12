"""Variacao legitima do espanhol, e artefatos do modelo, que NAO sao erro.

Sem esta camada o avaliador reprova pronuncia correta. No spike M0, aplicar estas
equivalencias derrubou o PER de fala natural correta de 18.6% para 3.9%, enquanto
a fala com sotaque carregado quase nao se moveu (60.0% -> 58.7%): remove artefato
de representacao sem apagar erro de verdade.

**Equivalencia aqui NAO e transitiva, e isso e proposital.** A tentacao e unir os
grupos e trabalhar com um representante canonico por classe. Isso quebra: /s/~/h/
vale (aspiracao de coda) e /x/~/h/ vale (jota caribenha), mas encadear os dois
tornaria "casa" e "caja" indistinguiveis. Pelo mesmo motivo /n/~/ŋ/ entra e
/n/~/m/ fica de fora -- "cama" e "cana" sao par minimo de verdade.

Tres origens, mantidas separadas porque tem consequencias diferentes:

1. `ALLOPHONIC`    -- alofonia obrigatoria do espanhol. Cobrar seria cobrar o
                      aluno por falar espanhol corretamente.
2. `REGIONAL`      -- variantes igualmente validas (seseo/distincion, yeismo).
3. `MODEL_ARTIFACT` -- limitacao medida do reconhecedor, nao da fala. Conta na
                      nota, mas nunca vira feedback por som.
"""

from __future__ import annotations

from itertools import combinations

# --- 1. Alofonia posicional obrigatoria do espanhol -----------------------
ALLOPHONIC: tuple[tuple[str, ...], ...] = (
    ("b", "β"),        # intervocalico: "lobo"
    ("d", "ð"),        # intervocalico: "nada"
    ("ɡ", "ɣ"),        # intervocalico: "lago"
    ("n", "ŋ"),        # assimilacao velar: "tengo". /m/ fica FORA (cama != cana)
)

# --- 2. Variacao regional valida ------------------------------------------
REGIONAL: tuple[tuple[str, ...], ...] = (
    ("s", "θ"),        # seseo (America) vs distincion (Espanha): "gracias"
    ("ʝ", "ʎ"),        # yeismo vs lleismo: "llave"
    ("ʝ", "j"),        # realizacao aproximante de /ʝ/: "yo"
    ("s", "h"),        # aspiracao de /s/ em coda: "ehto" por "esto"
    ("x", "h"),        # jota caribenha/andaluza: "trabajo"
)

# --- 3. Artefatos medidos do reconhecedor ---------------------------------
MODEL_ARTIFACT: tuple[tuple[str, ...], ...] = (
    ("ɾ", "r"),        # o modelo escreve a vibrante como tap duplicado
    ("x", "k"),        # jota ouvida como /k/  (ver JOTA_CONFUSION)
)


def _pairs(*groups: tuple[tuple[str, ...], ...]) -> frozenset[frozenset[str]]:
    """Pares nao ordenados. Sem fecho transitivo -- ver docstring do modulo."""
    out: set[frozenset[str]] = set()
    for group_set in groups:
        for group in group_set:
            for a, b in combinations(group, 2):
                out.add(frozenset((a, b)))
    return frozenset(out)


ALLOPHONIC_PAIRS = _pairs(ALLOPHONIC)
REGIONAL_PAIRS = _pairs(REGIONAL)
ARTIFACT_PAIRS = _pairs(MODEL_ARTIFACT)
EQUIVALENT_PAIRS = ALLOPHONIC_PAIRS | REGIONAL_PAIRS | ARTIFACT_PAIRS

JOTA_CONFUSION = frozenset({"x", "k"})
"""Par que o reconhecedor confunde sozinho.

Entra na nota -- senao toda palavra com jota perde pontos sem motivo -- mas nunca
vira a afirmacao "voce disse K no lugar de J": nessa direcao nao da para separar
erro do aluno de erro do modelo.
"""

GEMINATE_COLLAPSE = frozenset({"ɾ", "r"})
"""Fonemas em que repeticao adjacente e notacao, nao som a mais."""


def equivalent(a: str, b: str) -> bool:
    """True quando dois fonemas nao devem contar como erro um do outro."""
    return a == b or frozenset((a, b)) in EQUIVALENT_PAIRS


def equivalence_reason(a: str, b: str) -> str | None:
    """Por que estes dois fonemas nao sao erro. None quando sao diferentes mesmo."""
    if a == b:
        return "identical"
    pair = frozenset((a, b))
    if pair in ALLOPHONIC_PAIRS:
        return "allophonic"
    if pair in REGIONAL_PAIRS:
        return "regional"
    if pair in ARTIFACT_PAIRS:
        return "model_artifact"
    return None


def is_model_artifact(expected: str, heard: str) -> bool:
    """True quando a troca e falha conhecida do reconhecedor, nao do aluno."""
    return frozenset((expected, heard)) in ARTIFACT_PAIRS and expected != heard


def collapse_geminates(phones: list[str]) -> list[str]:
    """Colapsa taps/vibrantes repetidos: o modelo escreve `r` como `ɾɾ`."""
    out: list[str] = []
    for p in phones:
        if out and out[-1] == p and p in GEMINATE_COLLAPSE:
            continue
        out.append(p)
    return out
