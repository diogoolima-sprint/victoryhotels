#!/usr/bin/env python3
"""
parse_daily_xlsx.py — Parser determinístico dos relatórios diários FrontOffice
(TOTVS VHF, formato .xlsx novo) para Victory Business (VB) e Victory Suítes (VS).

Este é o layout NOVO (Excel 2007+, uma única tabela contínua cobrindo o mês
corrente inteiro, sem marcadores de texto "Efetivo"/"Previsão" e sem linhas
de Subtotal — apenas uma linha final "TOTALIZAÇÃO").

Colunas (linha de cabeçalho contém "Data" na coluna A), mesmos índices do
layout .xls antigo:
  0=Data 1=Sem. 3=%(occ) 4=Ocupadas 20=Rec.Ef. 21=Rec.Prev. 22=Tot.Rec. 23=Média(ADR)

Como não há mais o marcador de seção "Efetivo"/"Previsão" por linha, cada
dia é classificado comparando sua data com a data de geração do relatório
(embutida no rodapé da planilha, coluna X da última linha): dias <= hoje
entram no "bucket" efetivo (já ocorrido/em andamento), dias > hoje entram
no "bucket" previsão (futuro). É a mesma semântica do layout antigo.

NÃO usa LLM, não abre sub-agentes, não imprime dados brutos de célula.
Saída: um único JSON pequeno e limpo, no mesmo formato de parse_daily.py.
"""
import sys
import json
import argparse
import datetime
import openpyxl

COL_DATA = 0
COL_PCT_OCC = 3
COL_OCUPADAS = 4
COL_REC_EF = 20
COL_REC_PREV = 21
COL_TOT_REC = 22
COL_ADR = 23

DOW_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]


def to_float(v):
    if v == "" or v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(".", "").replace(",", ".") if "," in str(v) else str(v).strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def find_report_today(sh):
    """Data de geração do relatório, embutida no rodapé (última linha, coluna X)."""
    for r in range(sh.max_row, 0, -1):
        v = sh.cell(row=r, column=24).value
        if isinstance(v, datetime.datetime):
            return v.date()
    raise ValueError("Não foi possível localizar a data de geração no rodapé do relatório")


def _row_to_day(sh, r):
    date_val = sh.cell(row=r, column=1).value
    if isinstance(date_val, datetime.datetime):
        date_val = date_val.date()
    return {
        "data": date_val.strftime("%Y-%m-%d"),
        "dow": sh.cell(row=r, column=2).value,
        "occ_pct": round(to_float(sh.cell(row=r, column=COL_PCT_OCC + 1).value), 2),
        "ocupadas": int(to_float(sh.cell(row=r, column=COL_OCUPADAS + 1).value)),
        "rec_efetivo": round(to_float(sh.cell(row=r, column=COL_REC_EF + 1).value), 2),
        "rec_previsto": round(to_float(sh.cell(row=r, column=COL_REC_PREV + 1).value), 2),
        "rec_total": round(to_float(sh.cell(row=r, column=COL_TOT_REC + 1).value), 2),
        "adr": round(to_float(sh.cell(row=r, column=COL_ADR + 1).value), 2),
    }, date_val


def _sum_bucket(days):
    if not days:
        return None
    ocupadas = sum(d["ocupadas"] for d in days)
    rec_ef = round(sum(d["rec_efetivo"] for d in days), 2)
    rec_prev = round(sum(d["rec_previsto"] for d in days), 2)
    rec_tot = round(sum(d["rec_total"] for d in days), 2)
    return {
        "occ_pct": None,
        "ocupadas": ocupadas,
        "rec_efetivo": rec_ef,
        "rec_previsto": rec_prev,
        "rec_total": rec_tot,
        "adr": round(rec_tot / ocupadas, 2) if ocupadas else 0.0,
    }


def _row_to_dict_totals(sh, r):
    return {
        "occ_pct": round(to_float(sh.cell(row=r, column=COL_PCT_OCC + 1).value), 2),
        "ocupadas": int(to_float(sh.cell(row=r, column=COL_OCUPADAS + 1).value)),
        "rec_efetivo": round(to_float(sh.cell(row=r, column=COL_REC_EF + 1).value), 2),
        "rec_previsto": round(to_float(sh.cell(row=r, column=COL_REC_PREV + 1).value), 2),
        "rec_total": round(to_float(sh.cell(row=r, column=COL_TOT_REC + 1).value), 2),
        "adr": round(to_float(sh.cell(row=r, column=COL_ADR + 1).value), 2),
    }


def parse_report(path, room_count):
    wb = openpyxl.load_workbook(path, data_only=True)
    sh = wb[wb.sheetnames[0]]

    hoje = find_report_today(sh)

    header_row = None
    for r in range(1, sh.max_row + 1):
        if sh.cell(row=r, column=1).value == "Data":
            header_row = r
            break
    if header_row is None:
        raise ValueError("Linha de cabeçalho ('Data') não encontrada")

    dias_efetivo = []
    dias_previsao = []
    totalizacao = None

    r = header_row + 1
    while r <= sh.max_row:
        col0 = sh.cell(row=r, column=1).value
        if col0 == "TOTALIZAÇÃO":
            totalizacao = _row_to_dict_totals(sh, r)
            break
        if isinstance(col0, datetime.datetime):
            day, date_val = _row_to_day(sh, r)
            if date_val <= hoje:
                dias_efetivo.append(day)
            else:
                dias_previsao.append(day)
        r += 1

    subtotal_efetivo = _sum_bucket(dias_efetivo)
    subtotal_previsao = _sum_bucket(dias_previsao)

    validacao = {"ok": None, "detalhe": None}
    if totalizacao is not None:
        soma_receita = round(
            (subtotal_efetivo["rec_total"] if subtotal_efetivo else 0.0)
            + (subtotal_previsao["rec_total"] if subtotal_previsao else 0.0),
            2,
        )
        diff = round(soma_receita - totalizacao["rec_total"], 2)
        validacao["ok"] = abs(diff) < 1.0
        validacao["detalhe"] = (
            f"Bucket Efetivo ({(subtotal_efetivo or {}).get('rec_total', 0.0):.2f}) + "
            f"Bucket Previsão ({(subtotal_previsao or {}).get('rec_total', 0.0):.2f}) = {soma_receita:.2f} "
            f"vs TOTALIZAÇÃO ({totalizacao['rec_total']:.2f}) | diff={diff:.2f}"
        )

    return {
        "room_count": room_count,
        "relatorio_gerado_em": hoje.strftime("%Y-%m-%d"),
        "dias_efetivo": dias_efetivo,
        "dias_previsao": dias_previsao,
        "subtotal_efetivo": subtotal_efetivo,
        "subtotal_previsao": subtotal_previsao,
        "totalizacao": totalizacao,
        "validacao": validacao,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vb_path")
    ap.add_argument("vs_path")
    ap.add_argument("--out", default="daily_data.json")
    args = ap.parse_args()

    result = {
        "gerado_em": datetime.datetime.now().isoformat(timespec="seconds"),
        "VB": parse_report(args.vb_path, room_count=152),
        "VS": parse_report(args.vs_path, room_count=122),
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    for hotel in ("VB", "VS"):
        v = result[hotel]["validacao"]
        print(f"{hotel}: {len(result[hotel]['dias_efetivo'])} dias efetivo, "
              f"{len(result[hotel]['dias_previsao'])} dias previsão | "
              f"validação={'OK' if v['ok'] else 'FALHOU'}")
        if not v["ok"]:
            print(f"  -> {v['detalhe']}")

    print(f"\nJSON salvo em: {args.out}")


if __name__ == "__main__":
    main()
