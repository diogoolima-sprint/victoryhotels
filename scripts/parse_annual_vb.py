#!/usr/bin/env python3
"""
parse_annual_vb.py — Parser determinístico do relatório ANUAL de referência
do Victory Business (formato: PDF verdadeiro, colunas fixas por coordenada x).

Usado para o comparativo YoY. NÃO usa LLM — 100% baseado em posição (x,y) de
palavras extraídas via pdfplumber, sem heurística de "interpretação".

USO:
    python3 parse_annual_vb.py <relatorio_anual_VB.pdf> [--out anual_VB.json]

Layout (colunas por x0 aproximado, em pontos):
    Data      -> x ~30   (dd/mm/aa)
    Sem.      -> x ~72   (Qua, Qui, ...)
    %  (occ)  -> x ~116  (decimal com vírgula, ex: "22,37")
    Ocupadas  -> x ~151  (inteiro)
    ... (colunas de UH/hóspedes no meio, não usadas no dashboard) ...
    Bloco de receita no fim da linha (2 a 4 tokens no formato "N.NNN,NN"):
        - 4 tokens -> Rec.Ef, Rec.Prev, Tot.Rec, Média(ADR)
        - 3 tokens -> Rec.Ef, Tot.Rec, Média   (Rec.Prev=0, célula vazia)
        - 2 tokens -> Tot.Rec, Média            (fallback raro)
    Linha TOTALIZAÇÃO: mesmo padrão, mas sem coluna "Sem." (offset dos
    campos iniciais muda: label, %, Ocupadas direto).
"""
import sys
import re
import json
import argparse
import pdfplumber

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
MONEY_RE = re.compile(r"^-?[\d.]+,\d{2}$")
ROW_TOLERANCE = 3.0  # pontos de tolerância vertical para agrupar palavras na mesma linha


def to_float_br(s):
    """Converte 'N.NNN,NN' (formato BR) em float."""
    if s is None:
        return 0.0
    s = s.strip()
    if s == "":
        return 0.0
    return float(s.replace(".", "").replace(",", "."))


def group_rows(words):
    """Agrupa palavras em linhas por proximidade vertical (coordenada 'top')."""
    rows = []
    current = []
    last_top = None
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if last_top is not None and abs(w["top"] - last_top) > ROW_TOLERANCE:
            rows.append(current)
            current = []
        current.append(w)
        last_top = w["top"]
    if current:
        rows.append(current)
    return rows


def parse_revenue_block(tokens_money):
    """tokens_money: lista de strings no formato monetário, em ordem, no fim da linha.
    Retorna (rec_ef, rec_prev, tot_rec, adr)."""
    vals = [to_float_br(t) for t in tokens_money]
    if len(vals) == 4:
        return vals[0], vals[1], vals[2], vals[3]
    if len(vals) == 3:
        # Rec.Prev ausente (célula vazia = 0)
        return vals[0], 0.0, vals[1], vals[2]
    if len(vals) == 2:
        # fallback: só Tot.Rec e ADR
        return vals[0], 0.0, vals[0], vals[1]
    return 0.0, 0.0, 0.0, 0.0


def parse_annual_pdf(path):
    dias = []
    totalizacao = None

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            for row in group_rows(words):
                row_sorted = sorted(row, key=lambda w: w["x0"])
                texts = [w["text"] for w in row_sorted]
                if not texts:
                    continue

                label = texts[0]

                if DATE_RE.match(label):
                    # linha de dia: Data, Sem., %, Ocupadas, [colunas meio...], bloco receita
                    if len(texts) < 4:
                        continue
                    data = label
                    sem = texts[1]
                    occ_pct = to_float_br(texts[2])
                    try:
                        ocupadas = int(texts[3])
                    except ValueError:
                        ocupadas = 0

                    money_tokens = [t for t in texts if MONEY_RE.match(t)]
                    # os primeiros dois tokens monetários podem coincidir com
                    # %/ocupadas se mal filtrados; garantimos que vêm depois do índice 3
                    money_tokens_tail = [
                        w["text"] for w in row_sorted[4:] if MONEY_RE.match(w["text"])
                    ]
                    rec_ef, rec_prev, tot_rec, adr = parse_revenue_block(money_tokens_tail)

                    dias.append(
                        {
                            "data": "20" + data[6:8] + "-" + data[3:5] + "-" + data[0:2],
                            "dow": sem,
                            "occ_pct": round(occ_pct, 2),
                            "ocupadas": ocupadas,
                            "rec_efetivo": round(rec_ef, 2),
                            "rec_previsto": round(rec_prev, 2),
                            "rec_total": round(tot_rec, 2),
                            "adr": round(adr, 2),
                        }
                    )

                elif label == "TOTALIZAÇÃO":
                    # sem coluna "Sem.": label, %, Ocupadas, ... , bloco receita
                    if len(texts) < 3:
                        continue
                    occ_pct = to_float_br(texts[1])
                    try:
                        ocupadas = int(texts[2])
                    except ValueError:
                        ocupadas = 0
                    money_tokens_tail = [
                        w["text"] for w in row_sorted[3:] if MONEY_RE.match(w["text"])
                    ]
                    rec_ef, rec_prev, tot_rec, adr = parse_revenue_block(money_tokens_tail)
                    totalizacao = {
                        "occ_pct": round(occ_pct, 2),
                        "ocupadas": ocupadas,
                        "rec_efetivo": round(rec_ef, 2),
                        "rec_previsto": round(rec_prev, 2),
                        "rec_total": round(tot_rec, 2),
                        "adr": round(adr, 2),
                    }

    # validação: soma das receitas diárias deve bater com TOTALIZAÇÃO
    validacao = {"ok": None, "detalhe": None}
    if totalizacao and dias:
        soma = round(sum(d["rec_total"] for d in dias), 2)
        diff = round(soma - totalizacao["rec_total"], 2)
        validacao["ok"] = abs(diff) < 5.0  # tolerância de arredondamento
        validacao["detalhe"] = (
            f"Soma diária ({soma:.2f}) vs TOTALIZAÇÃO ({totalizacao['rec_total']:.2f}) | diff={diff:.2f}"
        )

    return {"dias": dias, "totalizacao": totalizacao, "validacao": validacao}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf_path")
    ap.add_argument("--out", default="anual_VB.json")
    args = ap.parse_args()

    result = parse_annual_pdf(args.pdf_path)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Dias parseados: {len(result['dias'])}")
    print(f"Validação: {'OK' if result['validacao']['ok'] else 'FALHOU'}")
    print(f"  -> {result['validacao']['detalhe']}")
    print(f"JSON salvo em: {args.out}")


if __name__ == "__main__":
    main()
