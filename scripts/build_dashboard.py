#!/usr/bin/env python3
"""
build_dashboard.py — Monta o dashboard comercial diario (HTML e-mail-safe)
usando templates/dashboard_template.html como esqueleto literal.

USO:
  python3 build_dashboard.py --hoje <daily_hoje.json> --data YYYY-MM-DD \
      [--ontem <daily_ontem.json>] --out <saida.html>

Regras travadas no codigo (nao inferir de dashboards anteriores):
  - metas sempre de cache/metas_2026.json
  - YoY sempre de cache/anual_{VB,VS}_2025.json, janela 01..N do mes (N = dias efetivo)
  - pickup = rec_total(hoje, data futura) - rec_total(ontem, mesma data futura)
  - sem <style>, sem class=, sem flex/grid, sem <html>/<head>/<body>: so o bloco <table>
"""
import argparse
import json
import os
import calendar
from datetime import date, datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
MES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DIA_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
              "sexta-feira", "sábado", "domingo"]
DOW_FIX = {"Sab": "Sáb", "Sabado": "Sáb"}

VERDE, AMBAR, VERMELHO, CINZA = "#059669", "#d97706", "#dc2626", "#6b7280"
HOTEL_CFG = {
    "VB": {"nome": "Victory Business", "cor": "#1a56db", "cor_clara": "#93c5fd"},
    "VS": {"nome": "Victory Suites",  "cor": "#7e3af2", "cor_clara": "#c4b5fd"},
}


# ---------------- formatacao pt-BR ----------------
def _milhar(n):
    return f"{n:,.0f}".replace(",", ".")


def brl0(v):
    return ("&ndash; R$ " if v < 0 else "R$ ") + _milhar(abs(v))


def brl0c(v):
    """compacto, sem espaco (usado nas tabelas de pickup)"""
    return ("&ndash;R$" if v < 0 else "R$") + _milhar(abs(v))


def brl2(v):
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("&ndash;R$" if v < 0 else "R$") + s


def brl2sp(v):
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("&ndash; R$ " if v < 0 else "R$ ") + s


def pct(v, d=1):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".") + "%"


def num(v, d=2):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def sinal_brl0(v):
    return ("+" if v >= 0 else "&ndash;") + "R$" + _milhar(abs(v))


def dm(d):
    """'2026-11-12' -> '12/11'"""
    y, m, dd = d.split("-")
    return f"{dd}/{m}"


def dmes(d):
    y, m, dd = d.split("-")
    return f"{int(dd)}/{MES_ABREV[int(m) - 1]}"


# ---------------- agregacoes ----------------
def agrega(ocupadas, rec, rooms, ndias):
    base = rooms * ndias
    return {
        "ocupadas": ocupadas,
        "rec": round(rec, 2),
        "occ": (ocupadas / base * 100) if base else 0.0,
        "adr": (rec / ocupadas) if ocupadas else 0.0,
        "revpar": (rec / base) if base else 0.0,
        "ndias": ndias,
    }


def yoy_2025(hotel, mes, ndias, rooms):
    p = os.path.join(REPO, "cache", f"anual_{hotel}_2025.json")
    dias = json.load(open(p, encoding="utf-8"))["dias"]
    ini = f"2025-{mes:02d}-01"
    fim = f"2025-{mes:02d}-{ndias:02d}"
    sel = [x for x in dias if ini <= x["data"] <= fim]
    if len(sel) != ndias:
        raise SystemExit(f"YoY {hotel}: esperava {ndias} dias em 2025, achei {len(sel)}")
    return agrega(sum(x["ocupadas"] for x in sel),
                  sum(x["rec_total"] for x in sel), rooms, ndias)


def var_span(valor, sufixo, inverter=False, tamanho="11px"):
    """Variacao YoY com o mesmo peso visual do valor principal (min 11px, negrito)."""
    sobe = valor > 0 if not inverter else valor < 0
    cor = VERDE if sobe else (VERMELHO if valor != 0 else CINZA)
    seta = "&#9650;" if valor > 0 else ("&#9660;" if valor < 0 else "&middot;")
    return (f'<span style="font-size:{tamanho};font-weight:bold;color:{cor};">'
            f'{seta} {sufixo} vs 2025</span>')


def cor_ating(p):
    return VERDE if p >= 100 else (AMBAR if p >= 85 else VERMELHO)


# ---------------- blocos do template ----------------
def barra(pctv, cor_barra):
    w = max(1, min(100, int(round(pctv))))
    out = ['<table width="100%" cellpadding="0" cellspacing="0" border="0" '
           'style="background-color:#e5e7eb;border-radius:3px;"><tr>']
    if w >= 100:
        out.append(f'<td style="background-color:{cor_barra};font-size:1px;line-height:7px;">&nbsp;</td>')
    else:
        out.append(f'<td width="{w}%" style="background-color:{cor_barra};font-size:1px;line-height:7px;">&nbsp;</td>'
                   f'<td style="font-size:1px;line-height:7px;">&nbsp;</td>')
    out.append("</tr></table>")
    return "\n".join(out)


def kpi_cell(label, valor, legenda, variacao):
    return (
        '<td width="33%" align="center" style="background-color:#f9fafb;border:1px solid #e5e7eb;padding:6px 3px;">\n'
        f'<span style="font-size:8px;color:#6b7280;font-weight:bold;text-transform:uppercase;">{label}</span><br>\n'
        f'<span style="font-size:14px;font-weight:800;">{valor}</span><br>\n'
        f'<span style="font-size:7.5px;color:#9ca3af;">{legenda}</span><br>\n'
        f'{variacao}\n'
        '</td>'
    )


def card_hotel(h, d, lado):
    cfg = HOTEL_CFG[h]
    pad = "padding-right:6px;" if lado == "esq" else "padding-left:6px;"
    L = []
    L.append(f'<td width="50%" style="{pad}">')
    L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e5e7eb;border-radius:5px;">')
    L.append('<tr><td style="padding:10px;">')
    L.append('<table cellpadding="0" cellspacing="0" border="0"><tr>')
    L.append(f'<td style="background-color:{cfg["cor"]};color:#ffffff;font-size:10px;font-weight:800;padding:3px 8px;border-radius:8px;">{h}</td>')
    L.append(f'<td style="font-size:13px;font-weight:bold;padding-left:6px;">{cfg["nome"]}</td>')
    L.append('</tr></table>')

    # Occ / ADR / RevPAR + variacao YoY
    L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;"><tr>')
    L.append(kpi_cell("Ocupação", pct(d["mtd"]["occ"]), f'acum. 1&ndash;{d["dia_ate"]}',
                      var_span(d["v_occ"], f'{num(abs(d["v_occ"]), 1)} p.p.')))
    L.append(kpi_cell("ADR", brl2sp(d["mtd"]["adr"]), "diária média efetiva",
                      var_span(d["v_adr"], pct(abs(d["v_adr"])))))
    L.append(kpi_cell("RevPAR", brl2sp(d["mtd"]["revpar"]), "por UH disp./dia",
                      var_span(d["v_revpar"], pct(abs(d["v_revpar"])))))
    L.append('</tr></table>')

    # Receita Realizada vs meta
    L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;"><tr>')
    L.append('<td style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">Receita Realizada (até hoje)</td>')
    L.append(f'<td align="right" style="font-size:10px;font-weight:800;">{brl0(d["rec_ef"])}</td>')
    L.append('</tr></table>')
    L.append(barra(d["p_real"], cfg["cor"]))
    L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>')
    L.append(f'<td style="font-size:7.5px;color:#6b7280;">{pct(d["p_real"])} da meta</td>')
    L.append(f'<td align="right" style="font-size:7.5px;color:#6b7280;">Meta: {brl0(d["meta_rec"])}</td>')
    L.append('</tr></table>')

    # Total On the Books vs meta
    L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:6px;"><tr>')
    L.append('<td style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">Total On the Books (mês)</td>')
    L.append(f'<td align="right" style="font-size:10px;font-weight:800;">{brl0(d["otb"]["rec"])}</td>')
    L.append('</tr></table>')
    L.append(barra(d["p_otb"], cfg["cor_clara"]))
    L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>')
    L.append(f'<td style="font-size:7.5px;color:#6b7280;">{pct(d["p_otb"])} da meta</td>')
    if d["gap"] > 0:
        L.append(f'<td align="right" style="font-size:7.5px;color:{AMBAR};">Gap: &ndash; {brl0(d["gap"])}</td>')
    else:
        L.append(f'<td align="right" style="font-size:7.5px;color:{VERDE};">Superávit: + {brl0(-d["gap"])}</td>')
    L.append('</tr></table>')

    # Pace OU meta batida
    if d["meta_batida"]:
        L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#ecfdf5;border:1px solid #6ee7b7;border-radius:4px;margin-top:8px;"><tr><td style="padding:6px;">')
        L.append(f'<span style="font-size:8px;font-weight:bold;color:#065f46;text-transform:uppercase;">&#10004; Meta já batida &middot; {d["dias_rest"]} dias restantes</span>')
        L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px;"><tr>')
        L.append(f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{VERDE};">+ {brl0(d["superavit"])}</span><br><span style="font-size:7.5px;color:#6b7280;">Superávit sobre a meta</span></td>')
        L.append(f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:#065f46;">{pct(d["p_otb"])}</span><br><span style="font-size:7.5px;color:#6b7280;">da meta (OTB)</span></td>')
        L.append(f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{HOTEL_CFG[h]["cor"]};">{brl0(d["ob_dia"])}</span><br><span style="font-size:7.5px;color:#6b7280;">OB atual/dia</span></td>')
        L.append('</tr></table>')
        L.append('</td></tr></table>')
    else:
        L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f9fafb;border:1px solid #e5e7eb;border-radius:4px;margin-top:8px;"><tr><td style="padding:6px;">')
        L.append(f'<span style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">Pace para a Meta &middot; {d["dias_rest"]} dias restantes</span>')
        L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px;"><tr>')
        L.append(f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{cfg["cor"]};">{brl0(d["ob_dia"])}</span><br><span style="font-size:7.5px;color:#6b7280;">OB atual/dia</span></td>')
        L.append(f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{AMBAR};">{brl0(d["nec_dia"])}</span><br><span style="font-size:7.5px;color:#6b7280;">Necessário/dia</span></td>')
        gcor = VERMELHO if d["gap_dia"] > 0 else VERDE
        gsin = "+ " if d["gap_dia"] > 0 else "&ndash; "
        L.append(f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{gcor};">{gsin}{brl0(abs(d["gap_dia"]))}</span><br><span style="font-size:7.5px;color:#6b7280;">Gap adicional/dia</span></td>')
        L.append('</tr></table>')
        L.append('</td></tr></table>')

    # Hoje vs Ontem
    hv = d["hoje_vs_ontem"]
    L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f9fafb;border:1px solid #e5e7eb;border-radius:4px;margin-top:6px;"><tr><td style="padding:6px;">')
    L.append(f'<span style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">Hoje ({hv["rot_hoje"]}, parcial) vs Ontem ({hv["rot_ontem"]})</span>')
    L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px;"><tr>')
    for v, txt, fmt in (
        (hv["d_occ"], f'Ocup. ({pct(hv["occ_h"], 2)} vs {pct(hv["occ_o"], 2)})', "pp"),
        (hv["d_adr"], f'ADR ({brl2(hv["adr_h"])} vs {brl2(hv["adr_o"])})', "brl2"),
        (hv["d_rec"], f'Receita ({brl0c(hv["rec_h"])} vs {brl0c(hv["rec_o"])})', "brl0"),
    ):
        cor = VERDE if v > 0 else (VERMELHO if v < 0 else CINZA)
        seta = "&#9650;" if v > 0 else ("&#9660;" if v < 0 else "&middot;")
        if fmt == "pp":
            val = f'{num(abs(v), 2)} p.p.'
        elif fmt == "brl2":
            val = brl2sp(abs(v))
        else:
            val = brl0(abs(v))
        L.append(f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{cor};">{seta} {val}</span><br><span style="font-size:7.5px;color:#6b7280;">{txt}</span></td>')
    L.append('</tr></table>')
    L.append('</td></tr></table>')

    L.append('</td></tr></table>')
    L.append('</td>')
    return "\n".join(L)


def tabela_pickup(h, d, lado, tem_pickup, rot_pickup, janela):
    cfg = HOTEL_CFG[h]
    pad = "padding-right:6px;" if lado == "esq" else "padding-left:6px;"
    L = [f'<td width="50%" style="{pad}">']
    L.append(f'<span style="font-size:9.5px;font-weight:bold;text-transform:uppercase;color:#6b7280;">{h} &middot; Pickup por Dia ({janela}){rot_pickup}</span>')
    L.append('<table width="100%" cellpadding="3" cellspacing="0" border="0" style="border-collapse:collapse;margin-top:4px;">')
    hdr = ('<tr style="background-color:#f3f4f6;">'
           '<td style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">Data</td>'
           '<td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">Occ%</td>'
           '<td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">DM</td>'
           '<td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">Receita</td>')
    if tem_pickup:
        hdr += '<td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">&Delta; Pickup</td>'
    hdr += "</tr>"
    L.append(hdr)

    for r in d["pickup"]:
        fds = r["dow"] in ("Sáb", "Dom")
        tr = '<tr style="background-color:#f0f7ff;">' if fds else "<tr>"
        row = (tr +
               f'<td style="font-size:9px;border-bottom:1px solid #f3f4f6;">{r["dow"]} {dm(r["data"])}</td>'
               f'<td align="right" style="font-size:9px;border-bottom:1px solid #f3f4f6;">{pct(r["occ"])}</td>'
               f'<td align="right" style="font-size:9px;border-bottom:1px solid #f3f4f6;">{brl2(r["adr"])}</td>'
               f'<td align="right" style="font-size:9px;border-bottom:1px solid #f3f4f6;">{brl0c(r["rec"])}</td>')
        if tem_pickup:
            dv = r["delta"]
            if dv is None:
                row += ('<td align="right" style="font-size:9px;color:#9ca3af;'
                        'border-bottom:1px solid #f3f4f6;" title="data sem par no relatório de ontem">&mdash;</td>')
            else:
                cor = VERDE if dv > 0 else (VERMELHO if dv < 0 else CINZA)
                row += f'<td align="right" style="font-size:9px;color:{cor};border-bottom:1px solid #f3f4f6;">{sinal_brl0(dv)}</td>'
        row += "</tr>"
        L.append(row)

    t = d["pickup_total"]
    tot = ('<tr style="background-color:#f3f4f6;">'
           f'<td style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">TOTAL {janela}</td>'
           f'<td align="right" style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">{pct(t["occ"])}</td>'
           f'<td align="right" style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">{brl2(t["adr"])}</td>'
           f'<td align="right" style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">{brl0c(t["rec"])}</td>')
    if tem_pickup:
        dv = t["delta"]
        cor = VERDE if dv > 0 else (VERMELHO if dv < 0 else CINZA)
        tot += f'<td align="right" style="font-size:9px;font-weight:800;color:{cor};border-top:1.5px solid #d1d5db;">{sinal_brl0(dv)}</td>'
    tot += "</tr>"
    L.append(tot)
    L.append("</table>")
    if not tem_pickup:
        L.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px;"><tr>'
                 '<td style="font-size:8px;color:#92400e;background-color:#fef3c7;border:1px solid #f59e0b;border-radius:3px;padding:4px 6px;">'
                 'Coluna &Delta; Pickup omitida: relatório do dia útil anterior não disponível na pasta. '
                 'Nenhum valor de pickup foi estimado.</td></tr></table>')
    L.append("</td>")
    return "\n".join(L)


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hoje", required=True)
    ap.add_argument("--ontem", default=None)
    ap.add_argument("--data", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    hoje_dt = datetime.strptime(a.data, "%Y-%m-%d").date()
    mes, ano = hoje_dt.month, hoje_dt.year
    dias_mes = calendar.monthrange(ano, mes)[1]
    mes_nome = MESES[mes - 1]
    mes_ab = MES_ABREV[mes - 1]

    dh = json.load(open(a.hoje, encoding="utf-8"))
    do = json.load(open(a.ontem, encoding="utf-8")) if a.ontem else None
    tem_pickup = do is not None
    ontem_dt = None
    if tem_pickup:
        ontem_dt = datetime.strptime(do["VB"]["dias_efetivo"][-1]["data"], "%Y-%m-%d").date()
    metas = json.load(open(os.path.join(REPO, "cache", "metas_2026.json"), encoding="utf-8"))
    mk = f"{mes:02d}"

    dados = {}
    for h in ("VB", "VS"):
        src = dh[h]
        rooms = src["room_count"]
        if not src["validacao"]["ok"]:
            raise SystemExit(f"{h}: validacao do relatorio de hoje FALHOU — abortando")
        if mk not in metas[h]["metas"]:
            raise SystemExit(f"metas_2026.json nao tem o mes {mk} para {h} — abortando")
        meta = metas[h]["metas"][mk]

        ef = src["dias_efetivo"]
        prev = src["dias_previsao"]
        n_ef = len(ef)
        se, sp, tz = src["subtotal_efetivo"], src["subtotal_previsao"], src["totalizacao"]

        mtd = agrega(se["ocupadas"], se["rec_total"], rooms, n_ef)
        otb = agrega(tz["ocupadas"], tz["rec_total"], rooms, dias_mes)
        y = yoy_2025(h, mes, n_ef, rooms)

        rec_ef = se["rec_efetivo"] if se["rec_efetivo"] else se["rec_total"]
        meta_rec = meta["receita"]
        meta_revpar = meta["occ"] / 100.0 * meta["adr"]
        dias_rest = dias_mes - n_ef

        meta_batida = (rec_ef >= meta_rec) or (otb["rec"] >= meta_rec)
        gap = meta_rec - otb["rec"]
        ob_dia = sp["rec_total"] / dias_rest if dias_rest else 0.0
        nec_dia = max(0.0, (meta_rec - rec_ef)) / dias_rest if dias_rest else 0.0

        # Hoje (parcial) vs Ontem — ambos do relatorio de hoje
        hj, on = ef[-1], ef[-2]
        hv = {
            "rot_hoje": dmes(hj["data"]), "rot_ontem": dmes(on["data"]),
            "occ_h": hj["occ_pct"], "occ_o": on["occ_pct"],
            "adr_h": hj["adr"], "adr_o": on["adr"],
            "rec_h": hj["rec_total"], "rec_o": on["rec_total"],
            "d_occ": hj["occ_pct"] - on["occ_pct"],
            "d_adr": hj["adr"] - on["adr"],
            "d_rec": hj["rec_total"] - on["rec_total"],
        }

        # Pickup por dia
        prev_ont = {}
        if tem_pickup:
            prev_ont = {x["data"]: x for x in do[h]["dias_previsao"]}
        linhas, soma_d, soma_oc, soma_rec, faltando = [], 0.0, 0, 0.0, []
        for x in prev:
            dow = DOW_FIX.get(x["dow"], x["dow"])
            delta = None
            if tem_pickup:
                if x["data"] in prev_ont:
                    delta = round(x["rec_total"] - prev_ont[x["data"]]["rec_total"], 2)
                else:
                    faltando.append(x["data"])
            linhas.append({"data": x["data"], "dow": dow, "occ": x["occ_pct"],
                           "adr": x["adr"], "rec": x["rec_total"], "delta": delta})
            if delta is not None:
                soma_d += delta
            soma_oc += x["ocupadas"]
            soma_rec += x["rec_total"]
        n_prev = len(prev)
        ptot = {"occ": soma_oc / (rooms * n_prev) * 100 if n_prev else 0.0,
                "adr": soma_rec / soma_oc if soma_oc else 0.0,
                "rec": soma_rec, "delta": round(soma_d, 2)}

        dados[h] = {
            "rooms": rooms, "n_ef": n_ef, "mtd": mtd, "otb": otb, "yoy": y,
            "rec_ef": rec_ef, "meta_rec": meta_rec, "meta": meta, "meta_revpar": meta_revpar,
            "p_real": rec_ef / meta_rec * 100, "p_otb": otb["rec"] / meta_rec * 100,
            "gap": gap, "meta_batida": meta_batida, "superavit": max(0.0, otb["rec"] - meta_rec),
            "dias_rest": dias_rest, "ob_dia": ob_dia, "nec_dia": nec_dia,
            "gap_dia": nec_dia - ob_dia,
            "v_occ": mtd["occ"] - y["occ"],
            "v_adr": (mtd["adr"] / y["adr"] - 1) * 100 if y["adr"] else 0.0,
            "v_revpar": (mtd["revpar"] / y["revpar"] - 1) * 100 if y["revpar"] else 0.0,
            "dia_ate": f'{dmes(ef[-1]["data"])}',
            "hoje_vs_ontem": hv, "pickup": linhas, "pickup_total": ptot,
            "pickup_faltando": faltando,
            "at_occ": otb["occ"] / meta["occ"] * 100,
            "at_adr": otb["adr"] / meta["adr"] * 100,
            "at_revpar": otb["revpar"] / meta_revpar * 100,
            "at_rec": otb["rec"] / meta_rec * 100,
            "prev_ini": prev[0]["data"], "prev_fim": prev[-1]["data"],
        }

    vb, vs = dados["VB"], dados["VS"]
    n_ef = vb["n_ef"]
    janela_mtd = f'01&ndash;{n_ef:02d}/{mes_ab}'
    janela_prev = f'{dm(vb["prev_ini"])[:2]}&ndash;{dm(vb["prev_fim"])[:2]}/{mes_ab}'
    data_badge = f'{hoje_dt.day} de {mes_nome} de {ano} ({DIA_SEMANA[hoje_dt.weekday()]})'
    rel_hoje = f'{hoje_dt.day:02d}-{mes:02d}'

    # combinados
    c_rec_ef = vb["rec_ef"] + vs["rec_ef"]
    c_otb = vb["otb"]["rec"] + vs["otb"]["rec"]
    c_meta = vb["meta_rec"] + vs["meta_rec"]
    c_p = c_otb / c_meta * 100
    c_gap = c_meta - c_otb

    # deslocamento de dia da semana 2026 vs 2025
    d26 = date(ano, mes, 1).weekday()
    d25 = date(ano - 1, mes, 1).weekday()
    deslocado = d26 != d25

    H = []
    H.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:820px;margin:0 auto;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#111827;">')
    # cabecalho
    H.append('<tr><td style="background-color:#111827;color:#ffffff;padding:12px 16px;border-radius:5px;">')
    H.append('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>')
    H.append(f'<td style="font-size:16px;font-weight:bold;color:#ffffff;">Dashboard Comercial &mdash; {mes_nome.capitalize()} {ano}</td>')
    H.append(f'<td align="right" style="font-size:11px;font-weight:bold;color:#fcd34d;background-color:#374151;padding:4px 10px;border-radius:10px;">{data_badge}</td>')
    H.append('</tr></table>')
    H.append('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td style="font-size:10px;color:#9ca3af;padding-top:2px;">Receita Realizada &middot; On the Books &middot; Pace para Meta</td></tr></table>')
    H.append('</td></tr>')
    H.append('<tr><td style="height:8px;font-size:1px;line-height:8px;">&nbsp;</td></tr>')

    # nota de fonte
    if tem_pickup:
        nota_pick = (f'Pickup {janela_prev} calculado comparando a seção Previsão do relatório de hoje '
                     f'contra a do relatório do dia anterior ({dm(vb["prev_ini"])} em diante), para as mesmas datas futuras.')
    else:
        nota_pick = ('Coluna &Delta; Pickup omitida nesta edição: o relatório do dia útil anterior não estava '
                     'disponível na pasta. Nenhum valor de pickup foi estimado.')
    H.append('<tr><td style="background-color:#eff6ff;border:1px solid #93c5fd;border-radius:4px;padding:8px 12px;font-size:10.5px;color:#1e40af;">')
    H.append(f'<strong>&#9873; Nota de fonte:</strong> Occ/ADR/RevPAR/Receita extraídos diretamente de '
             f'Relatório VB/VS {rel_hoje}.xls (fonte oficial FrontOffice). Validação aritmética: '
             f'Subtotal Efetivo + Subtotal Previsão = TOTALIZAÇÃO (confere nos dois hotéis). '
             f'Metas lidas de metas_2026.json (Budget 2026 rev01). YoY contra o relatório anual oficial 2025. {nota_pick}')
    H.append('</td></tr>')
    H.append('<tr><td style="height:6px;font-size:1px;line-height:6px;">&nbsp;</td></tr>')

    # alerta de deslocamento
    if deslocado:
        H.append('<tr><td style="background-color:#fef3c7;border:1px solid #f59e0b;border-radius:4px;padding:8px 12px;font-size:10.5px;color:#92400e;">')
        H.append(f'<strong>&#9888; Atenção YoY:</strong> a janela {ano} ({janela_mtd}) começa num '
                 f'{DIA_SEMANA[d26]}; a janela {ano-1} equivalente começa num {DIA_SEMANA[d25]} &mdash; '
                 f'período deslocado em dia de semana. Leia a comparação YoY como direcional.')
        H.append('</td></tr>')
        H.append('<tr><td style="height:6px;font-size:1px;line-height:6px;">&nbsp;</td></tr>')

    H.append('<tr><td style="height:10px;font-size:1px;line-height:10px;">&nbsp;</td></tr>')

    # faixa de KPIs combinados
    H.append('<tr><td style="background-color:#1f2937;border-radius:5px;padding:10px 8px;">')
    H.append('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>')

    def band(valor, legenda, cor="#ffffff"):
        return (f'<td align="center" style="color:#ffffff;padding:4px;">'
                f'<span style="font-size:15px;font-weight:800;color:{cor};">{valor}</span><br>'
                f'<span style="font-size:8.5px;color:#9ca3af;text-transform:uppercase;">{legenda}</span></td>')

    H.append(band(brl0(c_rec_ef), f'Receita Realiz. (VB+VS) {janela_mtd}', "#fcd34d"))
    H.append(band(brl0(c_otb), "Total On the Books (mês)"))
    H.append(band(brl0(c_meta), "Meta Combinada"))
    H.append(band(pct(c_p), "% da Meta (OB/Meta)", "#fcd34d" if c_p < 100 else "#34d399"))
    if c_gap > 0:
        H.append(band(f'&ndash; {brl0(c_gap)}', "Gap para Meta", "#f87171"))
    else:
        H.append(band(f'+ {brl0(-c_gap)}', "Superávit sobre a Meta", "#34d399"))
    H.append(band(f'{vb["dias_rest"]} dias', f'Restantes ({janela_prev})'))
    H.append('</tr></table>')
    H.append('</td></tr>')
    H.append('<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>')

    # cards VB / VS
    H.append('<!-- VB / VS KPI cards side by side -->')
    H.append('<tr><td>')
    H.append('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr valign="top">')
    H.append(card_hotel("VB", vb, "esq"))
    H.append("")
    H.append(card_hotel("VS", vs, "dir"))
    H.append('</tr></table>')
    H.append('</td></tr>')
    H.append('<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>')

    # tabela de atingimento de meta
    H.append('<!-- Meta attainment table -->')
    H.append('<tr><td>')
    H.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e5e7eb;border-radius:5px;"><tr><td style="padding:10px;">')
    H.append(f'<span style="font-size:10.5px;font-weight:bold;text-transform:uppercase;color:#6b7280;">Atingimento de Meta &middot; {mes_nome.capitalize()} {ano} (mês inteiro, OTB)</span>')
    H.append('<table width="100%" cellpadding="6" cellspacing="0" border="0" style="margin-top:6px;border-collapse:collapse;">')
    H.append('<tr style="background-color:#f3f4f6;">')
    H.append('<td style="font-size:9px;font-weight:bold;color:#6b7280;text-transform:uppercase;border-bottom:1px solid #e5e7eb;">Hotel</td>')
    for col in ("Occ%", "ADR", "RevPAR", "Receita"):
        H.append(f'<td align="right" style="font-size:9px;font-weight:bold;color:#6b7280;text-transform:uppercase;border-bottom:1px solid #e5e7eb;">{col}</td>')
    H.append('</tr>')
    for i, h in enumerate(("VB", "VS")):
        d = dados[h]
        bb = "border-bottom:1px solid #f3f4f6;" if i == 0 else ""
        H.append('<tr>')
        H.append(f'<td style="font-weight:bold;color:{HOTEL_CFG[h]["cor"]};{bb}">{h}</td>')
        for key in ("at_occ", "at_adr", "at_revpar", "at_rec"):
            H.append(f'<td align="right" style="font-weight:bold;color:{cor_ating(d[key])};{bb}">{pct(d[key])}</td>')
        H.append('</tr>')
    H.append('</table>')
    H.append('</td></tr></table>')
    H.append('</td></tr>')
    H.append('<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>')

    # tabelas de pickup
    if tem_pickup:
        rot_pick = f' &mdash; análise {dm(ontem_dt.isoformat())}&rarr;{dm(hoje_dt.isoformat())}'
    else:
        rot_pick = ' &mdash; sem base de comparação'
    H.append('<!-- Pickup tables side by side -->')
    H.append('<tr><td>')
    H.append('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr valign="top">')
    H.append(tabela_pickup("VB", vb, "esq", tem_pickup, rot_pick, janela_prev))
    H.append(tabela_pickup("VS", vs, "dir", tem_pickup, rot_pick, janela_prev))
    H.append('</tr></table>')
    H.append('</td></tr>')
    H.append('<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>')

    # observacoes
    obs = []
    obs.append(f'&middot; <strong>Fonte:</strong> Occ/ADR/RevPAR/Receita vêm do relatório oficial FrontOffice '
               f'(Relatório VB/VS {rel_hoje}.xls) &mdash; validados aritmeticamente '
               f'(Subtotal Efetivo + Previsão = TOTALIZAÇÃO confere nos dois hotéis).<br>')
    obs.append(f'&middot; Metas do mês lidas de <strong>cache/metas_2026.json</strong> (Budget 2026 rev01): '
               f'VB {brl0(vb["meta_rec"])} / {pct(vb["meta"]["occ"])} / {brl0(vb["meta"]["adr"])} &middot; '
               f'VS {brl0(vs["meta_rec"])} / {pct(vs["meta"]["occ"])} / {brl0(vs["meta"]["adr"])}.<br>')
    for h in ("VB", "VS"):
        d = dados[h]
        if d["meta_batida"]:
            obs.append(f'&middot; <strong>{h}</strong> já bateu a meta de receita: OTB em {pct(d["p_otb"])} '
                       f'da meta, superávit de {brl0(d["superavit"])}.<br>')
        else:
            obs.append(f'&middot; <strong>{h}</strong> está a {pct(d["p_otb"])} da meta mensal (OTB); '
                       f'faltam {brl0(d["gap"])} e são necessários {brl0(d["nec_dia"])}/dia nos '
                       f'{d["dias_rest"]} dias restantes ({brl0(d["gap_dia"])}/dia acima do OB atual).<br>')
    if tem_pickup:
        for h in ("VB", "VS"):
            d = dados[h]
            neg = [dm(r["data"]) for r in d["pickup"] if r["delta"] is not None and r["delta"] < 0]
            pos = [r for r in d["pickup"] if r["delta"] is not None and r["delta"] > 0]
            txt = (f'&middot; <strong>Pickup {h}</strong> ({janela_prev}): total '
                   f'{sinal_brl0(d["pickup_total"]["delta"])} em {len(pos)} data(s) com ganho')
            txt += (f'; pickup negativo em {len(neg)} data(s) ({", ".join(neg)})' if neg else '; nenhuma data com pickup negativo')
            if d["pickup_faltando"]:
                txt += (f'. {len(d["pickup_faltando"])} data(s) sem par no relatório de ontem '
                        f'({", ".join(dm(x) for x in d["pickup_faltando"])}) aparecem como &mdash; &mdash; '
                        f'nenhum valor foi estimado')
            txt += '.<br>'
            obs.append(txt)
    else:
        obs.append('&middot; <strong>Pickup não calculado</strong> nesta edição: relatório do dia útil anterior '
                   'ausente na pasta. Nenhum valor foi estimado.<br>')
    obs.append(f'&middot; <strong>YoY</strong> contra o relatório anual oficial 2025 (base comparável: {n_ef} dias, {janela_mtd}): '
               f'VB Occ {num(vb["v_occ"], 1)} p.p. / ADR {pct(vb["v_adr"])} / RevPAR {pct(vb["v_revpar"])} &middot; '
               f'VS Occ {num(vs["v_occ"], 1)} p.p. / ADR {pct(vs["v_adr"])} / RevPAR {pct(vs["v_revpar"])}.'
               + (' Ver nota de deslocamento de dia de semana acima.' if deslocado else ''))
    H.append('<tr><td style="font-size:9px;color:#6b7280;line-height:1.6;">')
    H.append('<strong style="color:#374151;">Observações:</strong><br>')
    H.extend(obs)
    H.append('</td></tr>')
    H.append('<tr><td style="height:10px;font-size:1px;line-height:10px;">&nbsp;</td></tr>')

    # rodape
    H.append('<tr><td align="center" style="font-size:9px;color:#9ca3af;border-top:1px solid #e5e7eb;padding-top:8px;">')
    H.append(f'Relatório VB {rel_hoje}.xls &middot; Relatório VS {rel_hoje}.xls (fonte oficial) &nbsp;|&nbsp; '
             f'metas_2026.json &middot; anual_VB/VS_2025.json &nbsp;|&nbsp; '
             f'Gerado em {hoje_dt.strftime("%d/%m/%Y")} &nbsp;&middot;&nbsp; Período: {mes_nome} {ano} '
             f'&nbsp;&middot;&nbsp; {vb["dias_rest"]} dias restantes')
    H.append('</td></tr>')
    H.append('</table>')

    html = "\n".join(H) + "\n"
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(html)

    # resumo curto no stdout
    print(f"HTML: {a.out} ({len(html)} bytes)")
    for h in ("VB", "VS"):
        d = dados[h]
        print(f"{h}: MTD occ {pct(d['mtd']['occ'])} adr {brl2sp(d['mtd']['adr'])} revpar {brl2sp(d['mtd']['revpar'])} "
              f"| rec_ef {brl0(d['rec_ef'])} ({pct(d['p_real'])} meta) | OTB {brl0(d['otb']['rec'])} ({pct(d['p_otb'])} meta) "
              f"| meta_batida={d['meta_batida']} | pickup {sinal_brl0(d['pickup_total']['delta'])}")
        if d["pickup_faltando"]:
            print(f"  AVISO {h}: datas futuras sem par em ontem: {d['pickup_faltando']}")
    print(f"combinado: rec_ef {brl0(c_rec_ef)} | OTB {brl0(c_otb)} | meta {brl0(c_meta)} ({pct(c_p)})")
    print(f"deslocamento dia de semana: {deslocado}")


if __name__ == "__main__":
    main()
