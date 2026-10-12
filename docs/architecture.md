# Arquitetura

## Princípio

Dez módulos com fronteiras explícitas. O que mais importa: **transcrição,
avaliação de pronúncia e LLM não se conhecem**. Cada um pode ser trocado sem
tocar nos outros, e dois dos três podem falhar sem derrubar a aula.

```
backend/src/sptrainer/
├── config.py          configuração por ambiente; segredo nunca entra em repr()
├── content/           modelo, JSON/CSV, validação, dataset inicial
├── scheduling/        filtros, sorteio, anti-repetição
├── audio/             decodificação do navegador, utilidades de sinal
├── stt/               faster-whisper + timestamps por palavra
├── assessment/        ← o núcleo
│   ├── g2p.py         espeak-ng → fonemas esperados
│   ├── phonemes.py    wav2vec2 ONNX → fonemas ouvidos + GOP
│   ├── align.py       alinhamento Needleman-Wunsch
│   ├── accents.py     equivalências de sotaque (não transitivas)
│   ├── prosody.py     ritmo, pausas, F0
│   ├── scoring.py     fórmulas puras
│   ├── summary.py     frase de retorno, determinística
│   └── pipeline.py    orquestra e decide o que pode ser afirmado
├── tts/               ElevenLabs + cache + perfil da referência
├── progress/          SQLite
└── api/               FastAPI
```

## Local vs. nuvem

| Componente | Onde | Observação |
|---|---|---|
| G2P, decodificação, transcrição, fonemas, prosódia, notas, resumo | **local** | funciona offline |
| Áudio de referência (ElevenLabs) | **nuvem** | uma chamada por carta, depois cache |

## O contrato que sustenta a honestidade

`AssessmentResult` carrega `capabilities` e `limitations`, e **toda observação
nomeia sua evidência** (`transcript`, `phoneme_acoustic`, `prosody`). Se o modelo
acústico estiver desligado, ausente ou falhar:

- `PHONEME_ANALYSIS` não entra em `capabilities`;
- nenhuma observação de fonema é gerada;
- `phoneme_accuracy` é `None` e os pesos da nota são renormalizados;
- a limitação aparece em texto, na tela.

Nada é estimado para preencher a lacuna.

## Degradação

| Falha | Consequência |
|---|---|
| Sem `ELEVENLABS_API_KEY` | cartas e gravação funcionam; áudio novo → 503 |
| Cota da ElevenLabs esgotada | cartas já em cache continuam tocando |
| Modelo de fonemas ausente | avaliação cai para transcrição + prosódia, e declara |
| `ffmpeg` ausente | erro claro na gravação |
| Gravação muda | `no_speech_detected`, **não** nota zero |

## Reaproveitamento do protótipo

| Origem (`voice-assistant`) | Destino |
|---|---|
| `ollama_service.py` | não reaproveitado — o trainer não usa LLM |
| `speech.py` | `tts/elevenlabs_client.py` — síntese + tradução de erros; `play_bytes` descartado |
| `transcription.py` | `stt/whisper.py` — `es` + timestamps por palavra |
| `audio_input.py` | `audio/utils.py` — só as partes numpy/wave |
| `config.py` | `config.py` — mesmo padrão |
| `llm.py`, `main.py` | não reaproveitados (loop de conversa por voz) |

O microfone e a reprodução saíram do Python e foram para o navegador: o backend
não abre dispositivo de áudio.

## Decisões e seus porquês

1. **ONNX Runtime, não PyTorch.** ~50 MB contra ~900 MB; 137–242 ms por trecho na CPU.
2. **GOP relativo à referência da própria carta.** Zero falsos positivos contra
   5/79 do limiar absoluto. Ver `pronunciation-assessment.md` §3.3.
3. **Nenhum LLM.** Avaliado e removido: não acrescentava fato ao retorno e errava
   fonética e gramática. Ver "Por que não há LLM".
4. **Gravação no navegador.** Tira o microfone do processo Python e faz a
   interface funcionar em qualquer máquina.
5. **SQLite com uma linha por tentativa.** Estatística é consulta, não coluna;
   nenhum relatório novo exige migração. **O áudio nunca é guardado.**
6. **Equivalência fonética sem fecho transitivo.** Evita que `s~h` + `x~h`
   tornem *casa* e *caja* iguais.

## Por que não há LLM

Um `qwen3:4b-instruct` local chegou a ser integrado (explicações de vocabulário
e gramática, e um resumo da tentativa reescrito pelo modelo) e depois foi
**removido por inteiro**. O registro da avaliação fica aqui porque a conclusão é
reaproveitável.

### O que foi medido nesta máquina (CPU, sem GPU)

| tarefa | `qwen3:4b-instruct` | `qwen3:4b` |
|---|---|---|
| explicação de vocabulário | 10.1 s | 27.2 s (estourou o teto de tokens) |
| explicação de gramática | 10.9 s | 20.9 s (idem) |
| resumo de tentativa | 7–15 s | — |

### Por que não compensava

1. **O resumo não acrescentava informação.** Para não inventar diagnóstico, o
   modelo tinha de ficar preso a uma lista fechada de fatos, conferida por um
   verificador. Preso assim, ele só reescrevia o que o resumo determinístico já
   dizia — em 15 s no lugar de 4 s.

2. **As explicações erravam.** Verificado: disse que `llave` "se pronuncia
   ah-veh" (é *ya-ve*), chamou `hubiera tenido` de "condicional passado" (é
   mais-que-perfeito do subjuntivo) e afirmou que `rojo` é falso amigo do
   português (não é). Foi preciso proibi-lo de falar de pronúncia e carimbar
   todo texto como gerado — ou seja, o recurso vinha com uma ressalva que
   admitia não dar para confiar nele.

3. **O custo era real.** 2,5 GB em disco, ~3 GB de RAM carregado, e o serviço
   subia sozinho por trás (`OLLAMA_AUTOSTART=1`) quando alguém pedia explicação.

A pronúncia sempre veio do `espeak-ng`, determinística; o diagnóstico sempre veio
da medida acústica. O modelo de linguagem não participava de nenhum dos dois.
Tirá-lo não custou nenhuma funcionalidade do núcleo.

O que sobrou no lugar: `assessment/summary.py`, uma função pura que monta a frase
de retorno a partir das observações medidas — instantânea e incapaz de citar algo
que não foi medido.

**Onde um LLM ainda faria sentido:** gerar flashcards em lote, offline, passando
pelo validador de conteúdo e por revisão humana antes de entrar no baralho. Aí a
latência não importa e o erro é filtrado antes de chegar ao aluno. Não está
implementado.

## Seleção adaptativa (SRS-lite)

`Order.ADAPTIVE` repondera o sorteio pela melhor nota de cada carta:

| situação | peso |
|---|---|
| nunca praticada | 2.0 |
| praticada, abaixo de 80 | 1.0 + 3.0 × (quanto falta) |
| dominada (≥ 80) | 0.3 |

Uma carta com nota 0 pesa 4.0 — cerca de treze vezes mais que uma dominada. A
carta inédita fica acima de uma carta "média" de propósito: conteúdo novo vale
mais que insistir no que já sai razoável.

Repetição espaçada de verdade agenda por data. Isto é deliberadamente mais
simples e sem estado temporal, para não exigir migração depois. A janela
anti-repetição continua valendo e tem precedência sobre o peso.
