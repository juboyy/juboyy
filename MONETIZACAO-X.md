# Operação: Monetizar o X do zero — índice

Ponto de entrada único de tudo que foi construído nesta operação. Branch:
`claude/x-account-monetization-8xdfc7`.

## Mapa

| Peça | Onde | O que é |
|---|---|---|
| **Plano de 7 dias** | [`plano-monetizacao-x-7dias.md`](plano-monetizacao-x-7dias.md) | Estratégia honesta de elegibilidade + tração no X (Premium, 500 seguidores, engajamento de verificados) |
| **ViralForge** (app) | [`viralforge/`](viralforge/) | Web app que pontua cada post (Viral Score, 8 parâmetros) e gera variações com Claude (`claude-opus-4-8`) |
| **Semana 1 de execução** | [`x-content-skills/`](x-content-skills/) | Calendário dia a dia (posts, DMs, oferta), pipeline de leads e radar do X |
| **Handoff** | [`x-content-skills/HANDOFF-jarvis.md`](x-content-skills/HANDOFF-jarvis.md) | Estado da operação para passar a outra pessoa/sessão |

## Como usar (ordem prática)

1. **Leia** o `plano-monetizacao-x-7dias.md` — define a meta real da semana.
2. **Suba o ViralForge**: `cd viralforge && npm install && cp .env.example .env` (coloque `ANTHROPIC_API_KEY`) `&& npm start` → `http://localhost:3000`.
3. **Execute** o `x-content-skills/calendar/semana-01.md` — cada post passa antes pelo analisador do ViralForge para subir o Viral Score.
4. **Prospecte** com `x-content-skills/data/leads.csv` + `scripts/bird-x-radar.sh`.

## Verdades que orientam tudo

- Em 7 dias você fica **elegível** à monetização e ganha tração — o **payout** acumula ao longo de semanas (o X paga por engajamento de contas **verificadas**).
- **Ninguém garante viralidade por post.** O ViralForge maximiza a *probabilidade*; a alavanca é volume × análise × dobrar no que pegou.

## Limitações conhecidas

- O repo local `x-content-skills-repo` (Windows) é separado deste — a pasta `x-content-skills/` aqui é **portável** para copiar pra lá.
- Não há integração com o X nem com "Jarvis": ações externas (DM/post no X, avisar terceiros) precisam ser feitas por você. Aqui só atuo no GitHub `juboyy/juboyy`.

## Próximos passos em aberto

- Calibrar os pesos do ViralForge (`viralforge/public/viralEngine.js` → `WEIGHTS`) com o spec do Aumi.group e com dados reais de engajamento.
- Banco de 30 hooks + 10 templates de thread.
- Calendário da Semana 2.
