#!/usr/bin/env python3
"""
build_metrics.py — Agrega os JSONs do parse_daily (hoje e ontem) + YoY em cache
+ metas, e emite um JSON pequeno com TODAS as metricas do dashboard.
Deterministico: nenhuma leitura manual de planilha, nenhuma inferencia.

USO:
  python3 build_metrics.py --hoje daily_18.json --ontem daily_17.json \
      --data-ref 2026-11-18 --cache-dir cache --out metrics.json
"""
import json, argparse, calendar
from datetime import date, datetime

ROOMS = {"VB": 152, "VS": 122}
NOMES = {"VB": "Victory Business", "VS": "Victory Suites"}
DOW_PT = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"]


def agg(dias, rooms):
    """Agrega uma lista de dias em occ/adr/revpar/receita."""
    n = len(dias)
    ocup = sum(d["ocupadas"] for d in dias)
    rec = sum(d["rec_total"] for d in dias)
    disp = rooms * n
    return {
        "n_dias": n,
        "ocupadas": ocup,
        "receita": round(rec, 2),
        "disponiveis": disp,
        "occ_pct": round(ocup / disp * 100, 2) if disp else 0.0,
        "adr": round(rec / ocup, 2) if ocup else 0.0,
        "revpar": round(rec / disp, 2) if disp else 0.0,
    }


def var_pct(atual, anterior):
    if not anterior:
        return None
    return round((atual - anterior) / anterior * 100, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hoje", required=True)
    ap.add_argument("--ontem", default=None)
    ap.add_argument("--data-ref", required=True)
    ap.add_argument("--cache-dir", default="cache")
    ap.add_argument("--out", default="metrics.json")
    args = ap.parse_args()

    ref = datetime.strptime(args.data_ref, "%Y-%m-%d").date()
    mes = f"{ref.month:02d}"
    ano = ref.year

    with open(args.hoje, encoding="utf-8") as f:
        hoje = json.load(f)
    ontem = None
    if args.ontem:
        with open(args.ontem, encoding="utf-8") as f:
            ontem = json.load(f)
    with open(f"{args.cache_dir}/metas_2026.json", encoding="utf-8") as f:
        metas = json.load(f)

    # --- alerta de deslocamento de dia da semana (dia 1 do mes) ---
    dow_atual = date(ano, ref.month, 1).weekday()
    dow_ant = date(ano - 1, ref.month, 1).weekday()
    alerta_dow = {
        "deslocado": dow_atual != dow_ant,
        "dow_atual": DOW_PT[dow_atual],
        "dow_anterior": DOW_PT[dow_ant],
        "dias_diff": (dow_atual - dow_ant) % 7,
    }

    out = {
        "data_ref": args.data_ref,
        "data_ref_br": ref.strftime("%d/%m/%Y"),
        "dia": ref.day,
        "mes": mes,
        "mes_nome": ["", "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho", "Julho",
                     "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"][ref.month],
        "ano": ano,
        "dias_no_mes": calendar.monthrange(ano, ref.month)[1],
        "alerta_dow": alerta_dow,
        "pickup_disponivel": ontem is not None,
        "hoteis": {},
    }

    for h in ("VB", "VS"):
        rooms = ROOMS[h]
        H = hoje[h]
        eff = H["dias_efetivo"]
        prev = H["dias_previsao"]

        mtd = agg(eff, rooms)
        otb_total = round(H["totalizacao"]["rec_total"], 2)
        rec_realizada = round(H["subtotal_efetivo"]["rec_total"], 2)
        rec_ef_puro = round(H["subtotal_efetivo"]["rec_efetivo"], 2)
        rec_forecast = round(H["subtotal_previsao"]["rec_total"], 2)

        # mes fechado projetado (occ/adr do mes inteiro OTB)
        mes_full = agg(eff + prev, rooms)

        # --- YoY janela comparavel 01/mes..dia no ano anterior ---
        with open(f"{args.cache_dir}/anual_{h}_{ano-1}.json", encoding="utf-8") as f:
            anual = json.load(f)
        ini = f"{ano-1}-{mes}-01"
        fim = f"{ano-1}-{mes}-{ref.day:02d}"
        dias_ly = [d for d in anual["dias"] if ini <= d["data"] <= fim]
        ly = agg(dias_ly, rooms)
        # mes cheio do ano anterior (para contexto de meta/fechamento)
        ultimo_ly = calendar.monthrange(ano - 1, ref.month)[1]
        dias_ly_full = [d for d in anual["dias"]
                        if f"{ano-1}-{mes}-01" <= d["data"] <= f"{ano-1}-{mes}-{ultimo_ly:02d}"]
        ly_full = agg(dias_ly_full, rooms)

        # --- meta ---
        m = metas[h]["metas"].get(mes)
        if m is None:
            raise SystemExit(f"ERRO: meta do mes {mes} ausente em metas_2026.json para {h}")
        meta_rec = float(m["receita"])
        pct_realizada = round(rec_realizada / meta_rec * 100, 1)
        pct_otb = round(otb_total / meta_rec * 100, 1)
        gap_otb = round(meta_rec - otb_total, 2)
        dias_restantes = out["dias_no_mes"] - ref.day
        meta_batida = (rec_realizada >= meta_rec) or (otb_total >= meta_rec)
        pace = {
            "meta_batida": meta_batida,
            "superavit": round(max(rec_realizada, otb_total) - meta_rec, 2) if meta_batida else None,
            "gap": gap_otb if not meta_batida else None,
            "dias_restantes": dias_restantes,
            "diaria_necessaria": round(gap_otb / dias_restantes, 2) if (not meta_batida and dias_restantes > 0) else None,
            "ritmo_atual_diario": round(rec_realizada / ref.day, 2),
        }

        # --- hoje vs ontem (mesmo mes OTB) ---
        hvo = None
        if ontem:
            O = ontem[h]
            hvo = {
                "otb_ontem": round(O["totalizacao"]["rec_total"], 2),
                "otb_hoje": otb_total,
                "delta_otb": round(otb_total - O["totalizacao"]["rec_total"], 2),
                "realizada_ontem": round(O["subtotal_efetivo"]["rec_total"], 2),
                "realizada_hoje": rec_realizada,
                "delta_realizada": round(rec_realizada - O["subtotal_efetivo"]["rec_total"], 2),
                "ocupadas_otb_ontem": O["totalizacao"]["ocupadas"],
                "ocupadas_otb_hoje": H["totalizacao"]["ocupadas"],
                "delta_ocupadas_otb": H["totalizacao"]["ocupadas"] - O["totalizacao"]["ocupadas"],
            }

        # --- pickup por dia futuro ---
        pickup = []
        if ontem:
            mapa_ontem = {d["data"]: d for d in ontem[h]["dias_previsao"]}
            for d in prev:
                ref_o = mapa_ontem.get(d["data"])
                dt = datetime.strptime(d["data"], "%Y-%m-%d").date()
                pickup.append({
                    "data": d["data"],
                    "data_br": dt.strftime("%d/%m"),
                    "dow": DOW_PT[dt.weekday()][:3],
                    "occ_pct": d["occ_pct"],
                    "adr": d["adr"],
                    "receita": d["rec_total"],
                    "ocupadas": d["ocupadas"],
                    "delta": round(d["rec_total"] - ref_o["rec_total"], 2) if ref_o else None,
                })
        else:
            for d in prev:
                dt = datetime.strptime(d["data"], "%Y-%m-%d").date()
                pickup.append({
                    "data": d["data"], "data_br": dt.strftime("%d/%m"),
                    "dow": DOW_PT[dt.weekday()][:3], "occ_pct": d["occ_pct"],
                    "adr": d["adr"], "receita": d["rec_total"],
                    "ocupadas": d["ocupadas"], "delta": None,
                })

        pickup_total = None
        if ontem:
            vals = [p["delta"] for p in pickup if p["delta"] is not None]
            pickup_total = round(sum(vals), 2) if vals else None

        out["hoteis"][h] = {
            "nome": NOMES[h], "quartos": rooms,
            "mtd": mtd, "mes_otb": mes_full,
            "rec_realizada": rec_realizada, "rec_ef_puro": rec_ef_puro,
            "rec_forecast": rec_forecast, "otb_total": otb_total,
            "ly_mtd": ly, "ly_mes_cheio": ly_full,
            "yoy": {
                "occ_pp": round(mtd["occ_pct"] - ly["occ_pct"], 1),
                "occ_pct_var": var_pct(mtd["occ_pct"], ly["occ_pct"]),
                "adr_pct": var_pct(mtd["adr"], ly["adr"]),
                "revpar_pct": var_pct(mtd["revpar"], ly["revpar"]),
                "receita_pct": var_pct(mtd["receita"], ly["receita"]),
            },
            "meta": {"receita": meta_rec, "adr": m["adr"], "occ": m["occ"],
                     "pct_realizada": pct_realizada, "pct_otb": pct_otb},
            "pace": pace, "hoje_vs_ontem": hvo,
            "pickup": pickup, "pickup_total": pickup_total,
            "validacao_ok": H["validacao"]["ok"],
        }

    # --- combinado (rede) ---
    vb, vs = out["hoteis"]["VB"], out["hoteis"]["VS"]
    tot_rooms_dias = vb["mtd"]["disponiveis"] + vs["mtd"]["disponiveis"]
    tot_ocup = vb["mtd"]["ocupadas"] + vs["mtd"]["ocupadas"]
    tot_rec = vb["mtd"]["receita"] + vs["mtd"]["receita"]
    ly_rooms_dias = vb["ly_mtd"]["disponiveis"] + vs["ly_mtd"]["disponiveis"]
    ly_ocup = vb["ly_mtd"]["ocupadas"] + vs["ly_mtd"]["ocupadas"]
    ly_rec = vb["ly_mtd"]["receita"] + vs["ly_mtd"]["receita"]
    out["combinado"] = {
        "occ_pct": round(tot_ocup / tot_rooms_dias * 100, 2),
        "adr": round(tot_rec / tot_ocup, 2),
        "revpar": round(tot_rec / tot_rooms_dias, 2),
        "receita_mtd": round(tot_rec, 2),
        "otb_total": round(vb["otb_total"] + vs["otb_total"], 2),
        "meta_receita": vb["meta"]["receita"] + vs["meta"]["receita"],
        "ly_occ_pct": round(ly_ocup / ly_rooms_dias * 100, 2),
        "ly_adr": round(ly_rec / ly_ocup, 2),
        "ly_revpar": round(ly_rec / ly_rooms_dias, 2),
        "ly_receita": round(ly_rec, 2),
        "pickup_total": (round((vb["pickup_total"] or 0) + (vs["pickup_total"] or 0), 2)
                         if out["pickup_disponivel"] else None),
    }
    c = out["combinado"]
    c["occ_pp"] = round(c["occ_pct"] - c["ly_occ_pct"], 1)
    c["adr_pct"] = var_pct(c["adr"], c["ly_adr"])
    c["revpar_pct"] = var_pct(c["revpar"], c["ly_revpar"])
    c["receita_pct"] = var_pct(c["receita_mtd"], c["ly_receita"])
    c["pct_otb_meta"] = round(c["otb_total"] / c["meta_receita"] * 100, 1)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"metrics salvo em: {args.out}")


if __name__ == "__main__":
    main()
