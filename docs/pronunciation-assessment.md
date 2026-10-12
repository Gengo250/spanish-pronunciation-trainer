# Avaliação de pronúncia: o que é medido, como, e o que não dá para afirmar

Este é o documento mais importante do projeto. Ele existe porque a parte fácil de
um treinador de pronúncia é mostrar um número, e a parte difícil é esse número
significar alguma coisa.

Regra que organiza tudo o que vem abaixo: **nenhuma afirmação sobre a fala do
aluno sem evidência medida que a sustente.** Quando a medida não existe, o
resultado diz que não existe, em vez de estimar.

---

## 1. O pipeline

```
                      ┌─ espeak-ng (es-419 | es) ──▶ fonemas esperados ─┐
texto do flashcard ───┤                                                 │
                      └─ ElevenLabs (cache) ───────▶ áudio de referência ┤
                                                           │            │
                                                           ▼            ▼
                                                   perfil de referência (GOP + ritmo)
                                                                        │
gravação do aluno ──▶ ffmpeg ──▶ PCM 16 kHz ──┬──▶ faster-whisper ──▶ palavras + tempos
                                              │                         │
                                              └──▶ wav2vec2 CTC ──▶ GOP por fonema
                                                                        │
                                                                        ▼
                                                        comparação relativa ──▶ resultado
```

| Etapa | Onde roda | Custo |
|---|---|---|
| G2P (`espeak-ng`) | local | nenhum |
| Áudio de referência (ElevenLabs) | **nuvem** | créditos, **uma vez por carta** |
| Decodificação (`ffmpeg`) | local | nenhum |
| Transcrição (faster-whisper `small`) | local | CPU |
| Fonemas (wav2vec2 int8 ONNX) | local | CPU |

A ElevenLabs é o único componente que sai da máquina, e só na primeira vez que
cada carta é ouvida.

---

## 2. Por que dois modelos, e não só o Whisper

Transcrição não mede pronúncia. O Whisper usa contexto de linguagem e acerta a
frase mesmo quando os sons saíram errados — é treinado exatamente para isso. Uma
nota baseada só na transcrição mede *inteligibilidade*, não pronúncia.

O segundo modelo responde a outra pergunta. Em vez de "que sons são estes?", ele
pergunta "o áudio sustenta o som /x/ **neste trecho**?". Isso é o **GOP**
(*Goodness of Pronunciation*): alinha-se a sequência esperada ao áudio por CTC
*forced alignment* e lê-se o log-posterior médio de cada fonema.

A peça que torna isso possível sem GPU: o `espeak-ng` emite rótulos de fonema do
espeak, e o modelo `wav2vec2-lv-60-espeak-cv-ft` **emite os mesmos rótulos**.
Esperado e reconhecido caem no mesmo alfabeto, então comparar é medir, não inferir.

Cobertura verificada: 397 fonemas gerados a partir de 75 palavras, nas duas
variantes — **100% dos símbolos do espeak-ng existem no vocabulário de 392 tokens
do modelo, nenhum não mapeado.** O espanhol usa 31–33 fonemas distintos.

---

## 3. Três resultados que mudaram o desenho

### 3.1 Decodificação livre não funciona — é preciso restringir ao espanhol

O modelo é multilíngue sobre 392 símbolos. Decodificando livremente, ele
interpreta espanhol como se fosse mandarim:

```
esperado:  x  w  a  n  t  ɾ  a  x  o   ...     ("Juan trajo jamón…")
ouvido:    s. u5 w ɑ5 n t  l ɑ5 ɕ onɡ5 ...     ← fonemas com marca de tom
```

Mascarar os logits para o inventário do espanhol antes do `argmax` derrubou o PER
de **85.7% para 46.4%** no mesmo áudio. A máscara não é otimização: sem ela o
módulo não funciona.

### 3.2 Fala sintética não serve para calibrar

A primeira bateria usou áudio do próprio `espeak-ng`. Resultado: até a pronúncia
*correta* marcava 28–88% de PER. O `espeak-ng` é síntese de formantes robótica, e
o wav2vec2 foi treinado em voz humana. Repetindo com áudio natural:

| frase | PER sintético → natural | GOP natural | GOP com sotaque |
|---|---|---|---|
| Me gustaría aprender español | 28.0% → **8.0%** | −0.21 | −1.67 |
| El perro corre rápido… | 19.2% → **19.2%** | −0.18 | −5.12 |
| Juan trajo jamón… | 46.4% → **28.6%** | −0.70 | −3.71 |

Com voz natural o GOP separa certo de errado de forma consistente nas três
frases; com voz sintética ele errava o sinal em 2 de 5.

### 3.3 Limiar absoluto acusa erro em pronúncia correta

Restava um problema sério: o áudio de referência da ElevenLabs — correto por
construção — gerava acusações como *"em 'aprender', o áudio sustenta mal o som
/a/"*.

As causas são fonéticas, não aleatórias:

- **Sinalefa.** Em `gustaría aprender` os dois /a/ se fundem numa vogal só. É
  espanhol correto; o /a/ esperado não tem suporte acústico independente.
- **Aproximantes intervocálicas.** /β ð ɣ/ são de baixa energia por natureza.
- **Palavras átonas.** O /d/ de `de` é fraco mesmo numa leitura perfeita.

Medido sobre 79 fonemas:

| critério | falsos positivos na referência | detecções no sotaque |
|---|---|---|
| absoluto −2.0 | 5/79 | 45/79 |
| absoluto −2.5 | 1/79 | 42/79 |
| **relativo, Δ < −2.0** | **0/79 por construção** | **45/79** |

**Decisão: comparar o aluno com a referência da mesma frase, som a som.** O que é
intrinsecamente fraco é fraco nos dois lados, a diferença fica perto de zero e
não vira erro. Mesma capacidade de detecção, zero falsos positivos — e absorve de
graça sinalefa, aproximantes e átonas, sem regra especial para cada caso.

O limiar absoluto (−2.5, mais conservador) só entra quando não há referência.

---

## 4. Sotaque válido não é erro

Equivalências aplicadas antes de qualquer comparação. Elas derrubaram o PER da
fala correta de 18.6% para 3.9%, deixando o sotaque carregado praticamente
intacto (60.0% → 58.7%) — suprimem artefato de representação, não erro real.

| classe | pares | por quê |
|---|---|---|
| alofonia | b~β, d~ð, ɡ~ɣ, n~ŋ | obrigatória em espanhol |
| regional | s~θ, ʝ~ʎ, ʝ~j, s~h, x~h | seseo/distinción, yeísmo, aspiração |
| artefato | ɾ~r, x~k | limitação medida do reconhecedor |

**A equivalência não é transitiva, de propósito.** `s~h` vale e `x~h` vale, mas
encadear os dois tornaria *casa* e *caja* indistinguíveis. Pelo mesmo motivo
`n~ŋ` entra e `n~m` fica de fora: *cama* e *cana* são par mínimo real.

A confusão /x/~/k/ entra na nota — senão toda palavra com jota perde pontos — mas
**nunca vira feedback por som**: nessa direção não há como separar erro do aluno
de erro do modelo.

---

## 5. As fórmulas

Todas em `assessment/scoring.py`, puras e testadas.

```
word_accuracy    = 1 − WER(esperado, reconhecido)
                   palavras minúsculas, sem pontuação, sem acento — mas "ñ"
                   preservado, porque "ano" e "año" são palavras diferentes

phoneme_accuracy = 1 − PER(esperado, ouvido)
                   após equivalências e colapso de geminadas

fluency          = ritmo × pausas
                   ritmo  = 1.0 entre 0.75× e 1.30× da referência, caindo fora
                   pausas = 1 − max(0, total_pausado − 0.6s) / 3s
                   None quando não há referência ou a carta tem 1 palavra

practice_score   = 100 × média ponderada dos componentes disponíveis
                   palavra 0.50 · fonema 0.35 · fluência 0.15
                   componente ausente é excluído e os pesos renormalizados
```

Nota de prática **não é certificação**. Não há mapeamento para CEFR. Serve para o
aluno comparar tentativas da mesma carta.

---

## 6. Desempenho medido (Intel Alder Lake-P, 12 threads, sem GPU)

| etapa | tempo |
|---|---|
| wav2vec2 int8 (trecho de 2–3 s) | **137–242 ms** (RTF ≈ 0.08) |
| faster-whisper `small` | ~2–4 s |
| perfil da referência | ~160 ms, uma vez por carta |

Sem PyTorch: ONNX Runtime (~50 MB) no lugar de um wheel de ~900 MB.

---

## 7. Limitações — leia antes de confiar nos números

1. **A classe negativa não foi validada em fala humana.** Os exemplos "com
   sotaque" são síntese em voz portuguesa, não gravações de estudantes reais. A
   capacidade de detecção está demonstrada contra esse substituto, **não** contra
   erro humano de verdade. Os limiares devem ser recalibrados com gravações reais.
2. **Amostra pequena.** 79 fonemas, 3 frases, uma voz de referência.
3. **/x/ vs /k/ não é reportado** (seção 4).
4. **Entonação só em grosso.** A F0 sai de autocorrelação e sustenta apenas
   "sobe / desce / plano" no fim do enunciado. Nada mais fino é afirmado.
5. **Sem referência, a análise é mais conservadora** — limiar absoluto, menos
   detecções.
6. **O G2P roda palavra a palavra** e por isso não vê alofonia entre palavras
   (`días` isolado dá /d/; em `buenos días` soa /ð/). As classes de equivalência
   cobrem o caso.
7. **A nota mede o que foi medido.** Sem modelo acústico ela vem só de palavras e
   ritmo, e o resultado declara isso em `capabilities` e `limitations`.
