# Treino de pronúncia · Espanhol

Aplicação local de estudo de espanhol construída em volta de flashcards, áudio de
referência e **avaliação acústica da pronúncia** — não apenas transcrição.

A interface é toda em inglês; o conteúdo estudado é espanhol. Essa separação é
deliberada e sustentada pelo código: todo texto de interface vive em
`frontend/src/i18n/en.ts`, e a tipografia a reforça — a serifada é usada só para
espanhol, a sem serifa só para a interface, a monoespaçada só para medidas.

Roda em hardware modesto: toda a análise da fala acontece na CPU, sem GPU e sem
PyTorch. A única chamada externa é a síntese do áudio de referência, uma vez por
carta.

```
flashcard ──▶ ouvir referência ──▶ gravar ──▶ retorno som a som ──▶ repetir
```

---

## O que ele mede, de verdade

A maioria dos treinadores compara a transcrição com o texto esperado. Isso mede
inteligibilidade: o Whisper usa contexto de linguagem e acerta a frase mesmo com
os sons errados.

Aqui há uma segunda medida. O `espeak-ng` gera os fonemas esperados e um modelo
wav2vec2 pergunta, para cada um deles, **se o áudio sustenta aquele som naquele
trecho** (GOP, via CTC forced alignment). Os dois componentes usam o mesmo
alfabeto de fonemas, então a comparação é medição e não inferência.

Não há modelo de linguagem em lugar nenhum do caminho: todo texto que o aluno lê
vem de medida ou de conteúdo escrito à mão.

Cada observação na tela carrega a etiqueta da evidência que a sustenta —
`transcrição`, `som` ou `ritmo`. Quando a análise acústica não está disponível,
a aplicação **diz isso** e não produz conclusões sobre sons.

O raciocínio completo, com os números medidos e as limitações, está em
[`docs/pronunciation-assessment.md`](docs/pronunciation-assessment.md). Vale a
leitura antes de confiar em qualquer nota.

---

## Requisitos

| Componente | Versão | Observação |
|---|---|---|
| Python | ≥ 3.12 | via `uv` |
| Node.js | ≥ 20.19 | o aviso do npm 12 sobre a versão é cosmético |
| `ffmpeg` | qualquer | decodifica o áudio do navegador |
| `espeak-ng` | qualquer | **obrigatório** — gera os fonemas de referência |
| Conta ElevenLabs | free serve | 10k caracteres/mês bastam, graças ao cache |

```bash
# Arch
sudo pacman -S espeak-ng ffmpeg
# Debian/Ubuntu
sudo apt install espeak-ng ffmpeg
```

## Instalação

```bash
cp .env.example .env
$EDITOR .env          # preencha ELEVENLABS_API_KEY
chmod 600 .env

cd backend  && uv sync
cd ../frontend && npm install
```

## Execução

A aplicação são dois processos: a API em `:8000` e a interface em `:5173`. O
`run.sh` sobe os dois.

```bash
./run.sh          # primeiro plano — Ctrl+C derruba os dois
./run.sh --bg     # segundo plano — sobrevive ao fechamento do terminal
./run.sh --stop   # derruba o que subiu com --bg
./run.sh --status # o que está de pé
./run.sh --logs   # acompanha os logs do modo --bg
```

Abra <http://localhost:5173>. O Vite encaminha `/api` para o backend.

**Primeiro plano morre junto com o terminal.** `uv run uvicorn` e `npm run dev`
ficam presos à janela: ao fechá-la, os dois recebem SIGHUP e caem. O `--bg`
coloca cada servidor na própria sessão (`setsid`), fora do alcance desse sinal —
dá para fechar o terminal, ou até deslogar, que eles continuam.

Os PIDs e os logs ficam em `.run/` (fora do versionamento). Se preferir subir na
mão, sem o script:

```bash
# terminal 1
cd backend && uv run uvicorn sptrainer.api.app:app --reload --port 8000
# terminal 2
cd frontend && npm run dev
```

Na primeira gravação o faster-whisper e o modelo de fonemas são baixados e
carregados — essa tentativa demora mais; as seguintes, não.

## Testes

```bash
cd backend
uv run pytest                      # suíte completa, sem tocar em serviço externo
uv run pytest -m "not integration" # explícito
uv run ruff check src tests

cd ../frontend
npm test            # interface logic: the copy shown to the learner
npm run typecheck
```

A ElevenLabs é dublada em todos os testes automatizados: **rodar a suíte não
consome créditos.**

---

## Custo da ElevenLabs

A conta free dá 10k caracteres/mês (20k nos modelos flash/turbo). Uma carta tem
10–40 caracteres.

Três decisões mantêm o consumo baixo:

1. **Cache endereçado por conteúdo.** Cada combinação (texto, voz, modelo,
   formato) é sintetizada uma única vez. As respostas trazem `X-Cache` e
   `X-Characters-Billed`.
2. **Reprodução lenta no navegador.** 0.75× e 0.5× saem do `playbackRate`, sem
   pedir áudio novo.
3. **`preload="none"`.** Folhear cartas não baixa áudio; só o botão *Ouvir* baixa.

Para dobrar a cota, troque para o modelo mais barato no `.env`:

```ini
ELEVENLABS_MODEL_ID=eleven_flash_v2_5
```

---

## Conteúdo

95 cartas iniciais em três níveis, oito tipos (vocabulário, frase, pergunta,
expressão, verbo, pronúncia, entonação) e quinze temas.

Os níveis são **definidos pela aplicação** e não correspondem a CEFR.

```bash
curl 'localhost:8000/api/content/export?fmt=csv' -o baralho.csv
curl -F 'file=@baralho.csv' localhost:8000/api/content/validate
```

O validador confere ids repetidos, texto duplicado, tamanho por nível,
pontuação de pergunta espanhola (`¿…?`), caracteres fora do alfabeto espanhol e
se os fonemas-alvo realmente aparecem na pronúncia. Traduções e explicações
gramaticais geradas por modelo **não** são presumidas corretas — o dataset
inicial foi escrito à mão, e os fonemas esperados sempre vêm do `espeak-ng`.

---

## Configuração

Tudo em `.env` (veja `.env.example`). Os mais úteis:

| Variável | Padrão | Para quê |
|---|---|---|
| `SPANISH_ACCENT` | `es-419` | `es-419` latino-americano, `es` peninsular |
| `ELEVENLABS_MODEL_ID` | `eleven_multilingual_v2` | `eleven_flash_v2_5` custa metade |
| `WHISPER_MODEL` | `small` | `base` é mais rápido, `medium` mais preciso |
| `PHONEME_ASSESSMENT_ENABLED` | `1` | `0` desliga a análise por som |

O acento muda a referência de verdade: `gracias` é `ɡɾasjas` em `es-419` e
`ɡɾaθjas` em `es`. As duas variantes são aceitas — seseo e distinción não contam
como erro.

---

## Compromissos assumidos

- **Precisão da pronúncia.** A detecção foi validada contra fala sintética com
  sotaque, não contra gravações de estudantes reais. Os limiares são
  conservadores e devem ser recalibrados com áudio real. Ver
  `docs/pronunciation-assessment.md` §7.
- **Desempenho.** `small` + int8 em vez de modelos maiores: ~137–242 ms por
  trecho na análise de fonemas, ~2–4 s na transcrição, numa CPU sem GPU.
- **Custo.** O áudio de referência vem da nuvem porque voz sintética local boa o
  bastante para servir de modelo de pronúncia não cabe neste orçamento de
  hardware. O cache limita isso a uma chamada por carta.
- **Sem LLM.** Um modelo local de 4B foi avaliado e removido: ele não
  acrescentava nenhum fato ao retorno e errava fonética e gramática. Veja
  `docs/architecture.md` para a medição que levou a essa decisão.
- **As notas servem ao estudo.** Não certificam proficiência.

## Licenças dos modelos

`wav2vec2-lv-60-espeak-cv-ft` e a build int8 ONNX: Apache-2.0. `faster-whisper`:
MIT. `espeak-ng`: GPLv3 (usado como processo externo).

## Documentação

- [`docs/architecture.md`](docs/architecture.md) — módulos, fronteiras, degradação
- [`docs/pronunciation-assessment.md`](docs/pronunciation-assessment.md) — medidas, fórmulas, limitações
