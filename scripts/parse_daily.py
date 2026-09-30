#!/usr/bin/env python3
"""
parse_daily.py — Parser determinístico dos relatórios diários FrontOffice
(TOTVS VHF, formato .xls legado BIFF) para Victory Business (VB) e Victory Suítes (VS).

USO:
    python3 parse_daily.py <caminho_VB.xls> <caminho_VS.xls> [--out saida.json]

NÃO usa LLM, não abre sub-agentes, não imprime dados brutos de célula.
Saída: um único JSON pequeno e limpo, pronto para o dashboard.

Layout do relatório (idêntico em VB e VS, confirmado em 28/07/2026):
  Linha 6  -> cabeçalhos. Colunas relevantes:
              0=Data(serial excel) 1=Sem. 3=%(occ) 4=Ocupadas
              20=Rec.Ef. 21=Rec.Prev. 22=Tot.Rec. 23=Média(ADR, string "1234,56")
  Linha 8  -> marcador "Efetivo"
  N linhas -> uma por dia já fechado do mês
  1 linha  -> col0="Subtotal", col1="Efetivo"  -> subtotal do mês até hoje (MTD real)
  1 linha  -> col0="Previsão"                   -> marcador
  N linhas -> uma por dia futuro (forecast/OTB)
  1 linha  -> col0="Subtotal", col1="Previsão"  -> subtotal do restante do mês (forecast)
  1 linha  -> col0="TOTALIZAÇÃO"                -> total do mês (deve = subtotal_efetivo + subtotal_previsao)
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

EXCEL_EPOCH = datetime(1899, 12, 30)  # xlrd/Excel serial date epoch


def excel_serial_to_iso(serial):
    return (EXCEL_EPOCH + timedelta(days=int(serial))).strftime("%Y-%m-%d")


def to_float(v):
    """Converte valor de célula (pode vir como string 'xxx,yy' com vírgula BR) em float."""
    if v == "" or v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(".", "").replace(",", ".") if "," in str(v) else str(v).strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _summary_from_days(days, room_count, n_dias):
    """Subtotal calculado a partir das linhas de dia (usado no layout sem marcadores)."""
    ocup = sum(d["ocupadas"] for d in days)
    ef = round(sum(d["rec_efetivo"] for d in days), 2)
    prev = round(sum(d["rec_previsto"] for d in days), 2)
    tot = round(sum(d["rec_total"] for d in days), 2)
    return {
        "occ_pct": round(ocup / (room_count * n_dias) * 100, 2) if n_dias else 0.0,
        "ocupadas": ocup,
        "rec_efetivo": ef,
        "rec_previsto": prev,
        "rec_total": tot,
        "adr": round(tot / ocup, 2) if ocup else 0.0,
    }


def parse_report(path, room_count, hoje=None):
    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)

    dias_efetivo = []
    dias_previsao = []
    subtotal_efetivo = None
    subtotal_previsao = None
    totalizacao = None

    section = None  # "efetivo" | "previsao"

    for r in range(sh.nrows):
        col0 = sh.cell_value(r, COL_DATA)
        col1 = sh.cell_value(r, 1) if sh.ncols > 1 else ""

        if col0 == "Efetivo":
            section = "efetivo"
            continue
        if col0 == "Previsão":
            section = "previsao"
            continue
        if col0 == "Subtotal" and col1 == "Efetivo":
            subtotal_efetivo = _row_to_dict(sh, r, is_summary=True)
            continue
        if col0 == "Subtotal" and col1 == "Previsão":
            subtotal_previsao = _row_to_dict(sh, r, is_summary=True)
            continue
        if col0 == "TOTALIZAÇÃO":
            totalizacao = _row_to_dict(sh, r, is_summary=True)
            continue

        # linha de dia: col0 é um serial de data (número)
        if isinstance(col0, float) and section in ("efetivo", "previsao"):
            day = {
                "data": excel_serial_to_iso(col0),
                "dow": sh.cell_value(r, 1),
                "occ_pct": round(to_float(sh.cell_value(r, COL_PCT_OCC)), 2),
                "ocupadas": int(to_float(sh.cell_value(r, COL_OCUPADAS))),
                "rec_efetivo": round(to_float(sh.cell_value(r, COL_REC_EF)), 2),
                "rec_previsto": round(to_float(sh.cell_value(r, COL_REC_PREV)), 2),
                "rec_total": round(to_float(sh.cell_value(r, COL_TOT_REC)), 2),
                "adr": round(to_float(sh.cell_value(r, COL_ADR)), 2),
            }
            if section == "efetivo":
                dias_efetivo.append(day)
            else:
                dias_previsao.append(day)

    # Layout sem marcadores "Efetivo"/"Previsão" (ex.: relatório emitido no último dia do mês,
    # onde só existe a linha TOTALIZAÇÃO). Com --hoje, o dia de hoje e os seguintes contam como
    # previsão (relatório emitido de manhã, o dia ainda vai crescer); os anteriores como efetivo.
    if not dias_efetivo and not dias_previsao and hoje:
        todos = []
        for r in range(sh.nrows):
            c0 = sh.cell_value(r, COL_DATA)
            if isinstance(c0, float):
                todos.append((r, c0))
        for r, c0 in todos:
            day = {
                "data": excel_serial_to_iso(c0),
                "dow": sh.cell_value(r, 1),
                "occ_pct": round(to_float(sh.cell_value(r, COL_PCT_OCC)), 2),
                "ocupadas": int(to_float(sh.cell_value(r, COL_OCUPADAS))),
                "rec_efetivo": round(to_float(sh.cell_value(r, COL_REC_EF)), 2),
                "rec_previsto": round(to_float(sh.cell_value(r, COL_REC_PREV)), 2),
                "rec_total": round(to_float(sh.cell_value(r, COL_TOT_REC)), 2),
                "adr": round(to_float(sh.cell_value(r, COL_ADR)), 2),
            }
            (dias_previsao if day["data"] >= hoje else dias_efetivo).append(day)
        subtotal_efetivo = _summary_from_days(dias_efetivo, room_count, len(dias_efetivo))
        subtotal_previsao = _summary_from_days(dias_previsao, room_count, len(dias_previsao))

    # validação cruzada: subtotal_efetivo + subtotal_previsao deve bater com totalizacao
    validacao = {"ok": None, "detalhe": None}
    if subtotal_efetivo and subtotal_previsao and totalizacao:
        soma_receita = round(subtotal_efetivo["rec_total"] + subtotal_previsao["rec_total"], 2)
        diff = round(soma_receita - totalizacao["rec_total"], 2)
        validacao["ok"] = abs(diff) < 1.0  # tolerância de R$1 por arredondamento
        validacao["detalhe"] = (
            f"Subtotal Ef. ({subtotal_efetivo['rec_total']:.2f}) + "
            f"Subtotal Prev. ({subtotal_previsao['rec_total']:.2f}) = {soma_receita:.2f} "
            f"vs TOTALIZAÇÃO ({totalizacao['rec_total']:.2f}) | diff={diff:.2f}"
        )

    return {
        "room_count": room_count,
        "dias_efetivo": dias_efetivo,
        "dias_previsao": dias_previsao,
        "subtotal_efetivo": subtotal_efetivo,
        "subtotal_previsao": subtotal_previsao,
        "totalizacao": totalizacao,
        "validacao": validacao,
    }


def _row_to_dict(sh, r, is_summary=False):
    pct_raw = sh.cell_value(r, COL_PCT_OCC)
    return {
        "occ_pct": round(to_float(pct_raw), 2),
        "ocupadas": int(to_float(sh.cell_value(r, COL_OCUPADAS))),
        "rec_efetivo": round(to_float(sh.cell_value(r, COL_REC_EF)), 2),
        "rec_previsto": round(to_float(sh.cell_value(r, COL_REC_PREV)), 2),
        "rec_total": round(to_float(sh.cell_value(r, COL_TOT_REC)), 2),
        "adr": round(to_float(sh.cell_value(r, COL_ADR)), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vb_path")
    ap.add_argument("vs_path")
    ap.add_argument("--out", default="daily_data.json")
    ap.add_argument("--hoje", default=None,
                    help="YYYY-MM-DD; só para relatórios sem marcadores Efetivo/Previsão: "
                         "dias >= hoje contam como previsão")
    args = ap.parse_args()

    result = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "VB": parse_report(args.vb_path, room_count=152, hoje=args.hoje),
        "VS": parse_report(args.vs_path, room_count=122, hoje=args.hoje),
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # resumo curto no stdout (não despeja dados brutos)
    for hotel in ("VB", "VS"):
        v = result[hotel]["validacao"]
        te = result[hotel]["subtotal_efetivo"]
        tp = result[hotel]["subtotal_previsao"]
        print(f"{hotel}: {len(result[hotel]['dias_efetivo'])} dias efetivo, "
              f"{len(result[hotel]['dias_previsao'])} dias previsão | "
              f"validação={'OK' if v['ok'] else 'FALHOU'}")
        if not v["ok"]:
            print(f"  -> {v['detalhe']}")

    print(f"\nJSON salvo em: {args.out}")


if __name__ == "__main__":
    main()
