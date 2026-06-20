# ⚡ ViralForge

Motor de viralidade para o X (Twitter). Você dá **parâmetros bem definidos**, o produto
**gera posts otimizados** e atribui um **Viral Score** a cada um. Híbrido: regras
determinísticas + Claude (`claude-opus-4-8`).

Feito para o nicho de **agentes de IA / tech / ciência / consciência / build in public /
money / hacks / insights** — mas funciona para qualquer nicho.

---

## O que ele faz

**1. Gerar** — você informa tema, nicho, formato, janela de horário e quantidade.
O Claude escreve N variações distintas, já seguindo as regras de viralidade (hook forte,
sem link no corpo, CTA de reply, etc). Cada variação recebe um **Viral Score híbrido**.

**2. Analisar** — cole um rascunho e veja o score em tempo real (100% determinístico,
roda offline, sem custo de API), com breakdown por dimensão e sugestões acionáveis.

---

## Os parâmetros bem definidos (o motor determinístico)

O Viral Score é uma **média ponderada de 8 dimensões mensuráveis**, cada uma 0–100:

| Dimensão | Peso | O que mede |
|---|---|---|
| Força do hook | 24% | Gatilhos na 1ª linha: contrário, numérico, loop de curiosidade, stakes; tamanho |
| Emoção / opinião | 15% | Presença de opinião forte e carga emocional |
| Gancho de engajamento | 15% | Termina com pergunta / CTA de reply / loop aberto |
| Especificidade | 12% | Números e entidades concretas vs. genérico |
| Escaneabilidade | 10% | Quebras de linha, ausência de parede de texto |
| Higiene de algoritmo | 10% | Penaliza link no corpo, excesso de hashtags/CAIXA ALTA/emojis |
| Aderência ao formato | 8% | O texto bate com o formato escolhido (thread, single, listicle…) |
| Horário | 6% | Janela de pico selecionada |

Os pesos vivem em `public/viralEngine.js` (`WEIGHTS`) — **ajuste lá** quando tiver o
spec do Aumi.group e os números recalibram automaticamente no app inteiro.

**Score das variações geradas** = `0.7 × determinístico + 0.3 × julgamento do Claude`.

> Honestidade do produto: ele **maximiza a probabilidade** de viralidade por post —
> não garante (ninguém garante). A estratégia é volume × análise × dobrar no que pegou.

---

## Rodando

Requisitos: Node 18+.

```bash
cd viralforge
npm install
cp .env.example .env        # edite e coloque sua ANTHROPIC_API_KEY
npm start                   # http://localhost:3000
```

Sem `ANTHROPIC_API_KEY` o app sobe normalmente e o **analisador determinístico
continua 100% funcional** — só a aba de geração por IA fica desabilitada.

---

## Arquitetura

```
viralforge/
├── server.js              Express: serve o app + POST /api/generate (Claude)
├── public/
│   ├── index.html         UI (gerar | analisar)
│   ├── styles.css
│   ├── app.js             frontend; chama o motor + a API
│   └── viralEngine.js     MOTOR determinístico (fonte única dos parâmetros)
├── .env.example
└── package.json
```

- O motor (`viralEngine.js`) é a fonte única da verdade e roda **no navegador**
  (tempo real, sem custo) e pode ser importado no Node se quiser pontuar no servidor.
- A geração usa structured outputs (`output_config.format`) — o Claude devolve JSON
  validado com `hook`, `body`, `hashtags`, `aiPredictedScore` e `rationale`.

---

## Próximos passos sugeridos

- Plugar o spec de viralidade do **Aumi.group / Discord** nos `WEIGHTS` e nos bancos
  de palavras do `viralEngine.js`.
- Calibrar os pesos com dados reais: exporte seus posts e o engajamento e ajuste para
  que o score correlacione com impressões/replies de contas verificadas.
- Banco de 30 hooks e 10 templates de thread como atalho de geração.
- Calendário: gerar os 70+ posts da semana em lote e exportar.
