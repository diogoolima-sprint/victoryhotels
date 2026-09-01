#!/usr/bin/env python3
"""
build_dashboard_data.py — Agrega todos os números necessários para o
dashboard (KPIs, YoY, meta, pace, atingimento, pickup) a partir dos JSONs
já parseados. Não interpreta planilhas — só faz aritmética sobre JSON.
"""
import json
import argparse
import datetime
import calendar

ROOMS = {"VB": 152, "VS": 122}
DOW_PT_FULL = {"Seg": "segunda-feira", "Ter": "terça-feira", "Qua": "quarta-feira",
               "Qui": "quinta-feira", "Sex": "sexta-feira", "Sab": "sábado", "Dom": "domingo"}


def agg(days, room_count, n_dias):
    ocup = sum(d["ocupadas"] for d in days)
    rec_total = round(sum(d["rec_total"] for d in days), 2)
    occ_pct = round(ocup / (room_count * n_dias) * 100, 2) if n_dias else 0.0
    adr = round(rec_total / ocup, 2) if ocup else 0.0
    revpar = round(rec_total / (room_count * n_dias), 2) if n_dias else 0.0
    return {"ocupadas": ocup, "rec_total": rec_total, "occ_pct": occ_pct, "adr": adr, "revpar": revpar}


def pct_delta(new, old):
    if old == 0:
        return None
    return round((new - old) / old * 100, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", required=True, help="daily_data.json de hoje (formato xlsx novo)")
    ap.add_argument("--yesterday", required=True, help="daily_data.json de ontem (formato xls antigo)")
    ap.add_argument("--yoy-vb", required=True)
    ap.add_argument("--yoy-vs", required=True)
    ap.add_argument("--metas", required=True)
    ap.add_argument("--hoje", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    today_data = json.load(open(args.today))
    yesterday_data = json.load(open(args.yesterday))
    yoy = {"VB": json.load(open(args.yoy_vb)), "VS": json.load(open(args.yoy_vs))}
    metas = json.load(open(args.metas))

    hoje = datetime.date.fromisoformat(args.hoje)
    mes = f"{hoje.month:02d}"
    ano = hoje.year
    dias_no_mes = calendar.monthrange(ano, hoje.month)[1]
    n_dias_decorridos = hoje.day
    dias_restantes = dias_no_mes - hoje.day

    hoje_2025 = hoje.replace(year=ano - 1)
    dow_shift = None

    out = {
        "hoje": args.hoje,
        "hoje_dow": None,
        "mes_nome": hoje.strftime("%B"),
        "dias_no_mes": dias_no_mes,
        "n_dias_decorridos": n_dias_decorridos,
        "dias_restantes": dias_restantes,
        "hotels": {},
    }

    for hotel in ("VB", "VS"):
        room_count = ROOMS[hotel]
        td = today_data[hotel]
        yd = yesterday_data[hotel]
        cache = yoy[hotel]
        m = metas[hotel]["metas"][mes]

        out["hoje_dow"] = td["dias_efetivo"][0]["dow"] if td["dias_efetivo"] else None

        # janela comparável: dia 1 do mes até hoje, 2026 vs 2025
        janela_2026 = td["dias_efetivo"]  # já é exatamente dias <= hoje dentro do mês corrente
        janela_2025 = [d for d in cache["dias"] if d["data"] >= f"{ano-1}-{mes}-01" and d["data"] <= hoje_2025.isoformat()]

        agg_2026 = agg(janela_2026, room_count, n_dias_decorridos)
        agg_2025 = agg(janela_2025, room_count, len(janela_2025))

        dow_2025 = janela_2025[0]["dow"] if janela_2025 else None
        dow_2026 = janela_2026[0]["dow"] if janela_2026 else None
        if dow_2025 and dow_2026 and dow_2025 != dow_2026:
            dow_shift = {"dow_2026": dow_2026, "dow_2025": dow_2025,
                         "dow_2026_full": DOW_PT_FULL.get(dow_2026), "dow_2025_full": DOW_PT_FULL.get(dow_2025)}

        # receita realizada (Rec. Ef. acumulado) e Total OTB
        receita_realizada = td["subtotal_efetivo"]["rec_efetivo"] if td["subtotal_efetivo"] else 0.0
        total_otb = td["totalizacao"]["rec_total"]
        subtotal_efetivo_rec_total = td["subtotal_efetivo"]["rec_total"] if td["subtotal_efetivo"] else 0.0
        prev_rec_total = td["subtotal_previsao"]["rec_total"] if td["subtotal_previsao"] else 0.0

        meta_receita = m["receita"]
        meta_adr = m["adr"]
        meta_occ = m["occ"]
        meta_revpar = round(meta_adr * meta_occ / 100, 2)

        pct_meta_realizada = round(receita_realizada / meta_receita * 100, 1)
        pct_meta_otb = round(total_otb / meta_receita * 100, 1)
        meta_batida = receita_realizada >= meta_receita or total_otb >= meta_receita

        ob_atual_dia = round(prev_rec_total / dias_restantes, 2) if dias_restantes else 0.0
        necessario_dia = round((meta_receita - subtotal_efetivo_rec_total) / dias_restantes, 2) if dias_restantes else 0.0
        gap_adicional_dia = round((meta_receita - total_otb) / dias_restantes, 2) if dias_restantes else 0.0

        # atingimento de meta (mes inteiro, OTB)
        tot = td["totalizacao"]
        occ_otb = round(tot["ocupadas"] / (room_count * dias_no_mes) * 100, 2)
        adr_otb = round(tot["rec_total"] / tot["ocupadas"], 2) if tot["ocupadas"] else 0.0
        revpar_otb = round(tot["rec_total"] / (room_count * dias_no_mes), 2)
        ating_occ = round(occ_otb / meta_occ * 100, 1)
        ating_adr = round(adr_otb / meta_adr * 100, 1)
        ating_revpar = round(revpar_otb / meta_revpar * 100, 1) if meta_revpar else None
        ating_receita = round(total_otb / meta_receita * 100, 1)

        # hoje vs ontem (ontem = ultimo dia do relatorio de ontem)
        ontem_row = yd["dias_efetivo"][-1] if yd["dias_efetivo"] else None
        hoje_row = td["dias_efetivo"][0] if td["dias_efetivo"] else None

        out["hotels"][hotel] = {
            "room_count": room_count,
            "janela_2026": {"n_dias": n_dias_decorridos, **agg_2026},
            "janela_2025": {"n_dias": len(janela_2025), **agg_2025, "dow": dow_2025},
            "delta_occ_pp": round(agg_2026["occ_pct"] - agg_2025["occ_pct"], 1) if agg_2025["occ_pct"] else None,
            "delta_adr_pct": pct_delta(agg_2026["adr"], agg_2025["adr"]),
            "delta_revpar_pct": pct_delta(agg_2026["revpar"], agg_2025["revpar"]),
            "receita_realizada": receita_realizada,
            "total_otb": total_otb,
            "meta_receita": meta_receita,
            "meta_adr": meta_adr,
            "meta_occ": meta_occ,
            "meta_revpar": meta_revpar,
            "pct_meta_realizada": pct_meta_realizada,
            "pct_meta_otb": pct_meta_otb,
            "gap_meta_otb": round(meta_receita - total_otb, 2),
            "meta_batida": meta_batida,
            "superavit": round(max(receita_realizada, total_otb) - meta_receita, 2) if meta_batida else None,
            "pace": {"ob_atual_dia": ob_atual_dia, "necessario_dia": necessario_dia, "gap_adicional_dia": gap_adicional_dia},
            "atingimento": {"occ_otb": occ_otb, "adr_otb": adr_otb, "revpar_otb": revpar_otb,
                             "pct_occ": ating_occ, "pct_adr": ating_adr, "pct_revpar": ating_revpar, "pct_receita": ating_receita},
            "hoje_row": hoje_row,
            "ontem_row": ontem_row,
            "pickup_dias": td["dias_previsao"],
            "totalizacao": tot,
        }

    out["dow_shift"] = dow_shift
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
