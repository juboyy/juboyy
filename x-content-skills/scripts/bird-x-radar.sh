#!/usr/bin/env bash
# bird-x-radar.sh — radar de oportunidades no X para mineração de conteúdo.
#
# Template. Pré-requisitos:
#   - Bird CLI instalado e autenticado (https://github.com/... — ajuste ao seu setup)
#   - jq instalado
#
# Objetivo: encontrar (a) founders de IA com conteúdo "morto" para prospecção e
# (b) notícias/temas quentes para news-jack. Salva um radar em markdown por dia.
#
# Uso:
#   ./bird-x-radar.sh "agentes de IA"
#
set -euo pipefail

QUERY="${1:-agentes de IA}"
OUT_DIR="$(dirname "$0")/../calendar"
STAMP="$(date +%Y-%m-%d)"
OUT="$OUT_DIR/radar-$STAMP.md"

mkdir -p "$OUT_DIR"

if ! command -v bird >/dev/null 2>&1; then
  echo "AVISO: 'bird' CLI não encontrado. Este script é um template."
  echo "Instale/autentique o Bird CLI ou troque a chamada abaixo pela sua ferramenta."
fi

{
  echo "# Radar X — $STAMP"
  echo
  echo "> Query: \`$QUERY\`"
  echo

  echo "## 🔥 Temas quentes (potencial de news-jack)"
  # Ajuste os flags conforme sua CLI. Exemplo defensivo:
  if command -v bird >/dev/null 2>&1; then
    bird search "$QUERY" --sort top --limit 20 --json 2>/dev/null \
      | jq -r '.[] | "- [\(.metrics.likes // 0) ❤] @\(.author): \(.text | gsub("\n";" ") | .[0:160])"' \
      || echo "- (sem resultados / ajuste os flags da CLI)"
  else
    echo "- (Bird CLI ausente — preencha manualmente os 3 temas mais comentados hoje)"
  fi
  echo

  echo "## 🎯 Prospects (founders com conteúdo para minerar)"
  if command -v bird >/dev/null 2>&1; then
    bird search "$QUERY (podcast OR live OR call OR episódio)" --sort latest --limit 20 --json 2>/dev/null \
      | jq -r '.[] | "- @\(.author): \(.text | gsub("\n";" ") | .[0:140])"' \
      || echo "- (sem resultados / ajuste os flags da CLI)"
  else
    echo "- (Bird CLI ausente — busque manualmente 'podcast IA' e liste 5 founders)"
  fi
  echo

  echo "## ✅ Próximas ações"
  echo "- [ ] Escolher 1 tema quente para news-jack hoje"
  echo "- [ ] Adicionar 5 novos prospects em data/leads.csv"
  echo "- [ ] Enviar 5 DMs com oferta de 1 corte grátis"
} > "$OUT"

echo "Radar gerado em: $OUT"
