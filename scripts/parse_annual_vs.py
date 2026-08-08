#!/usr/bin/env python3
"""
parse_annual_vs.py — Parser determinístico do relatório ANUAL de referência
do Victory Suítes. Apesar da extensão .pdf no nome original do arquivo, o
conteúdo é um .xls legado (BIFF/OLE) — mesma estrutura de colunas dos
relatórios diários, só que cobrindo o ano inteiro (sem seções
Efetivo/Previsão, já que é histórico fechado).

USO:
    python3 parse_annual_vs.py <relatorio_anual_VS.xls> [--out anual_VS.json]
"""
import sys
import json
import argparse
import xlrd
from datetime import datetime, timedelta

COL_DATA = 0
COL_PCT_OCC = 3
COL_OCUPADAS = 4
COL_REC_EF = 20
COL_REC_PREV = 21
COL_TOT_REC = 22
COL_ADR = 23

EXCEL_EPOCH = datetime(1899, 12, 30)


def excel_serial_to_iso(serial):
    return (EXCEL_EPOCH + timedelta(days=int(serial))).strftime("%Y-%m-%d")


def to_float(v):
    if v == "" or v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_annual(path):
    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)

    dias = []
    totalizacao = None

    for r in range(sh.nrows):
        col0 = sh.cell_value(r, COL_DATA)

        if col0 == "TOTALIZAÇÃO":
            totalizacao = {
                "occ_pct": round(to_float(sh.cell_value(r, COL_PCT_OCC)), 2),
                "ocupadas": int(to_float(sh.cell_value(r, COL_OCUPADAS))),
                "rec_efetivo": round(to_float(sh.cell_value(r, COL_REC_EF)), 2),
                "rec_previsto": round(to_float(sh.cell_value(r, COL_REC_PREV)), 2),
                "rec_total": round(to_float(sh.cell_value(r, COL_TOT_REC)), 2),
                "adr": round(to_float(sh.cell_value(r, COL_ADR)), 2),
            }
            continue

        if isinstance(col0, float):
            dias.append(
                {
                    "data": excel_serial_to_iso(col0),
                    "dow": sh.cell_value(r, 1),
                    "occ_pct": round(to_float(sh.cell_value(r, COL_PCT_OCC)), 2),
                    "ocupadas": int(to_float(sh.cell_value(r, COL_OCUPADAS))),
                    "rec_efetivo": round(to_float(sh.cell_value(r, COL_REC_EF)), 2),
                    "rec_previsto": round(to_float(sh.cell_value(r, COL_REC_PREV)), 2),
                    "rec_total": round(to_float(sh.cell_value(r, COL_TOT_REC)), 2),
                    "adr": round(to_float(sh.cell_value(r, COL_ADR)), 2),
                }
            )

    validacao = {"ok": None, "detalhe": None}
    if totalizacao and dias:
        soma = round(sum(d["rec_total"] for d in dias), 2)
        diff = round(soma - totalizacao["rec_total"], 2)
        validacao["ok"] = abs(diff) < 5.0
        validacao["detalhe"] = (
            f"Soma diária ({soma:.2f}) vs TOTALIZAÇÃO ({totalizacao['rec_total']:.2f}) | diff={diff:.2f}"
        )

    return {"dias": dias, "totalizacao": totalizacao, "validacao": validacao}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xls_path")
    ap.add_argument("--out", default="anual_VS.json")
    args = ap.parse_args()

    result = parse_annual(args.xls_path)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Dias parseados: {len(result['dias'])}")
    print(f"Validação: {'OK' if result['validacao']['ok'] else 'FALHOU'}")
    print(f"  -> {result['validacao']['detalhe']}")
    print(f"JSON salvo em: {args.out}")


if __name__ == "__main__":
    main()
