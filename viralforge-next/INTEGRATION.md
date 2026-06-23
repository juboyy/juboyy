# Integrar o ViralForge no aumi-content-engine (Next.js)

Pacote drop-in. Copie estas pastas para dentro do projeto `aumi-content-engine` e pronto.
Não precisa portar pra React — a UI roda como app estático servido pelo Next, e as rotas
de API são route handlers do App Router.

## 1. Copiar os arquivos

```
viralforge-next/public/viralforge/*      →  <aumi-content-engine>/public/viralforge/*
viralforge-next/app/api/viralforge/*     →  <aumi-content-engine>/app/api/viralforge/*
```

Resultado dentro do aumi-content-engine:

```
public/viralforge/
├── index.html
├── styles.css
├── app.js
├── viralEngine.js
└── library.js
app/api/viralforge/
├── generate/route.ts
└── health/route.ts
```

> **Se o projeto usa Pages Router** (tem `pages/` em vez de `app/`): mova as rotas para
> `pages/api/viralforge/generate.ts` e `health.ts` e troque a assinatura
> `export async function POST(req)` por `export default function handler(req, res)`
> (a lógica interna é a mesma). Avise que eu gero essa variante.

## 2. Dependência e env

```bash
npm i @anthropic-ai/sdk
```

Variáveis de ambiente (Vercel → Settings → Environment Variables):

- `ANTHROPIC_API_KEY` = sua chave (obrigatória para a aba *Gerar*)
- `VIRAL_MODEL` = `claude-opus-4-8` (opcional)

## 3. Acessar

`https://aumi-content-engine.vercel.app/viralforge/index.html`

(Opcional) para servir em `/viralforge`, adicione um rewrite no `next.config.js`:

```js
async rewrites() {
  return [{ source: "/viralforge", destination: "/viralforge/index.html" }];
}
```

## Notas

- As rotas usam `runtime = "nodejs"` e `maxDuration = 60` (a geração com thinking leva alguns segundos).
- O **analisador** (Viral Score) roda 100% no browser, sem API — funciona mesmo sem a chave.
- Sem `ANTHROPIC_API_KEY`, a aba *Gerar* responde 503; o resto funciona.
- Em produção serverless **não** dá pra usar o provider `claude-code` (sem CLI). Aqui é só `anthropic`.
