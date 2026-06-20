# Deploy do ViralForge (produção)

O app já está pronto para a Vercel: estático em `public/` + funções serverless em `api/`.
Falta apenas o publish, que exige a sua conta Vercel.

## Opção A — Git integration (recomendada, sem CLI)

1. [vercel.com](https://vercel.com) → **Add New… → Project** → importe o repo `juboyy/juboyy`.
2. Em **Root Directory**, selecione **`viralforge`**.  ← passo crítico (o app está no subdiretório)
3. Framework Preset: **Other** (sem build; `public/` é servido estático e `api/` vira funções).
4. **Environment Variables**:
   - `ANTHROPIC_API_KEY` = sua chave (obrigatória para a aba *Gerar*)
   - `VIRAL_MODEL` = `claude-opus-4-8` (opcional)
5. **Deploy**. Depois, cada push para a branch configurada redeploya.

## Opção B — Vercel CLI

```bash
cd viralforge
npx vercel deploy --prod        # faz login interativo na 1ª vez
# depois adicione a env var:
npx vercel env add ANTHROPIC_API_KEY production
```

## Observações

- **Sem `ANTHROPIC_API_KEY`** o site sobe e o **analisador determinístico funciona**;
  só a geração por IA retorna 503 até a chave ser configurada.
- `vercel.json` já define `maxDuration: 60s` para as funções (a geração com thinking
  pode levar alguns segundos).
- A chave fica como secret na Vercel — nunca commite `.env`.
