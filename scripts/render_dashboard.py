#!/usr/bin/env python3
"""
render_dashboard.py — Renderiza o dashboard e-mail-safe a partir de metrics.json,
usando templates/dashboard_template.html como esqueleto literal.

Regras do template (obrigatorias):
  - Somente tabelas HTML aninhadas, todo estilo inline.
  - PROIBIDO: <style>, class=, display:flex, display:grid, <!DOCTYPE>, <head>, <body>.
  - Saida = apenas o bloco <table> raiz, pronto para colar em e-mail.

USO:
  python3 render_dashboard.py --metrics metrics.json --daily daily_hoje.json --out saida.html
"""
import json, argparse
from datetime import datetime

MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
MESES_CAP = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
             "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
DOW_FULL = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
            "sexta-feira", "sábado", "domingo"]
DOW3 = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

VERDE, VERMELHO, AMBAR, CINZA = "#059669", "#dc2626", "#d97706", "#6b7280"
UP, DOWN = "&#9650;", "&#9660;"


def br(v, dec=0):
    """Numero no formato brasileiro."""
    s = f"{abs(v):,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return ("-" if v < 0 else "") + s


def m0(v):
    return "R$ " + br(round(v), 0)


def m2(v):
    return "R$ " + br(v, 2)


def pc(v, dec=1):
    return br(v, dec) + "%"


def sm0(v):
    """Dinheiro com sinal, usando en-dash para negativo (padrao do template)."""
    return ("+ R$ " if v >= 0 else "&ndash; R$ ") + br(round(abs(v)), 0)


def smc(v):
    """Dinheiro com sinal, compacto (coluna de pickup)."""
    return ("+R$" if v >= 0 else "&ndash;R$") + br(round(abs(v)), 0)


def seta(v, inverter=False):
    """Retorna (seta, cor) conforme o sinal."""
    bom = (v < 0) if inverter else (v > 0)
    if v == 0:
        return (UP, CINZA)
    return (UP if v > 0 else DOWN, VERDE if bom else VERMELHO)


def var_box(valor, sufixo, dec=1):
    """Linha de variacao YoY — MESMO peso visual do valor principal:
    11px, negrito, verde/vermelho, com seta. (exigencia da rotina)"""
    s, cor = seta(valor)
    return (f'<span style="font-size:11px;font-weight:bold;color:{cor};">'
            f'{s} {br(abs(valor), dec)}{sufixo} vs 2025</span>')


def kpi_cell(rotulo, valor, legenda, var_html, largura="33%"):
    return (f'<td width="{largura}" align="center" style="background-color:#f9fafb;'
            f'border:1px solid #e5e7eb;padding:6px 3px;">\n'
            f'<span style="font-size:8px;color:#6b7280;font-weight:bold;text-transform:uppercase;">{rotulo}</span><br>\n'
            f'<span style="font-size:14px;font-weight:800;">{valor}</span><br>\n'
            f'<span style="font-size:7.5px;color:#9ca3af;">{legenda}</span><br>\n'
            f'{var_html}\n</td>')


def barra(pct, cor_preenchida):
    """Barra de progresso em tabela (email-safe). Largura limitada a 100%."""
    w = max(1, min(100, int(round(pct))))
    return (f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="background-color:#e5e7eb;border-radius:3px;"><tr>\n'
            f'<td width="{w}%" style="background-color:{cor_preenchida};font-size:1px;line-height:7px;">&nbsp;</td>'
            f'<td style="font-size:1px;line-height:7px;">&nbsp;</td>\n</tr></table>')


def card_hotel(h, M, dia_cmp, cor_forte, cor_clara):
    """Monta um card de hotel (VB ou VS) na estrutura exata do template."""
    D = M["hoteis"][h]
    mtd, meta, pace, yoy = D["mtd"], D["meta"], D["pace"], D["yoy"]
    jan = f'acum. 1&ndash;{M["dia"]}/{MESES[int(M["mes"])][:3]}'

    # --- KPIs com variacao YoY em 11px bold ---
    kpis = (
        kpi_cell("Ocupação", pc(mtd["occ_pct"]), jan, var_box(yoy["occ_pp"], " p.p.")) + "\n" +
        kpi_cell("ADR", m2(mtd["adr"]), "diária média efetiva", var_box(yoy["adr_pct"], "%")) + "\n" +
        kpi_cell("RevPAR", m2(mtd["revpar"]), "por UH disp./dia", var_box(yoy["revpar_pct"], "%"))
    )

    # --- barra receita realizada ---
    rec_bar = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;"><tr>\n'
        '<td style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">Receita Realizada (até hoje)</td>\n'
        f'<td align="right" style="font-size:10px;font-weight:800;">{m0(D["rec_realizada"])}</td>\n</tr></table>\n'
        + barra(meta["pct_realizada"], cor_forte) + "\n"
        '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>\n'
        f'<td style="font-size:7.5px;color:#6b7280;">{pc(meta["pct_realizada"])} da meta</td>\n'
        f'<td align="right" style="font-size:7.5px;color:#6b7280;">Meta: {m0(meta["receita"])}</td>\n</tr></table>'
    )

    # --- barra OTB ---
    if pace["meta_batida"]:
        rodape_otb = f'<td align="right" style="font-size:7.5px;color:{VERDE};font-weight:bold;">Superávit: + {m0(pace["superavit"])}</td>'
    else:
        rodape_otb = f'<td align="right" style="font-size:7.5px;color:{AMBAR};">Gap: &ndash; {m0(pace["gap"])}</td>'
    otb_bar = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:6px;"><tr>\n'
        '<td style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">Total On the Books (mês)</td>\n'
        f'<td align="right" style="font-size:10px;font-weight:800;">{m0(D["otb_total"])}</td>\n</tr></table>\n'
        + barra(meta["pct_otb"], cor_clara) + "\n"
        '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>\n'
        f'<td style="font-size:7.5px;color:#6b7280;">{pc(meta["pct_otb"])} da meta</td>\n'
        f'{rodape_otb}\n</tr></table>'
    )

    # --- box de pace (ou meta batida) ---
    if pace["meta_batida"]:
        box_pace = (
            '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="background-color:#ecfdf5;border:1px solid #6ee7b7;border-radius:4px;margin-top:8px;">'
            '<tr><td style="padding:6px;" align="center">\n'
            f'<span style="font-size:8px;font-weight:bold;color:#065f46;text-transform:uppercase;">&#10004; Meta já batida</span><br>\n'
            f'<span style="font-size:13px;font-weight:800;color:{VERDE};">+ {m0(pace["superavit"])}</span><br>\n'
            f'<span style="font-size:7.5px;color:#047857;">superávit sobre a meta de {m0(D["meta"]["receita"])}</span>\n'
            '</td></tr></table>')
    else:
        obs = D["pickup_total"]
        nec = pace["diaria_necessaria"]
        cor_obs = VERDE if (obs is not None and obs >= nec) else VERMELHO
        cel_obs = (f'<span style="font-size:10.5px;font-weight:800;color:{cor_obs};">{smc(obs)}</span><br>'
                   f'<span style="font-size:7.5px;color:#6b7280;">Pickup obs. 24h</span>'
                   if obs is not None else
                   '<span style="font-size:10.5px;font-weight:800;color:#9ca3af;">&mdash;</span><br>'
                   '<span style="font-size:7.5px;color:#6b7280;">Pickup obs. (n/d)</span>')
        box_pace = (
            '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="background-color:#f9fafb;border:1px solid #e5e7eb;border-radius:4px;margin-top:8px;">'
            '<tr><td style="padding:6px;">\n'
            f'<span style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">'
            f'Pace para a Meta &middot; {pace["dias_restantes"]} dias restantes</span>\n'
            '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px;"><tr>\n'
            f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{cor_forte};">'
            f'{m0(pace["ritmo_atual_diario"])}</span><br>'
            '<span style="font-size:7.5px;color:#6b7280;">Realizado/dia</span></td>\n'
            f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{AMBAR};">'
            f'{m0(nec)}</span><br>'
            '<span style="font-size:7.5px;color:#6b7280;">Pickup nec./dia</span></td>\n'
            f'<td width="33%" align="center">{cel_obs}</td>\n'
            '</tr></table>\n</td></tr></table>')

    # --- box hoje vs ontem (dia corrente parcial vs dia anterior fechado) ---
    c = dia_cmp
    s_occ, cor_occ = seta(c["d_occ"])
    s_adr, cor_adr = seta(c["d_adr"])
    s_rec, cor_rec = seta(c["d_rec"])
    box_hvo = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background-color:#f9fafb;border:1px solid #e5e7eb;border-radius:4px;margin-top:6px;">'
        '<tr><td style="padding:6px;">\n'
        f'<span style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">'
        f'Hoje ({c["hoje_br"]}, parcial) vs Ontem ({c["ontem_br"]})</span>\n'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px;"><tr>\n'
        f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{cor_occ};">'
        f'{s_occ} {br(abs(c["d_occ"]),2)} p.p.</span><br>'
        f'<span style="font-size:7.5px;color:#6b7280;">Ocup. ({pc(c["occ_h"],2)} vs {pc(c["occ_o"],2)})</span></td>\n'
        f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{cor_adr};">'
        f'{s_adr} R$ {br(abs(c["d_adr"]),2)}</span><br>'
        f'<span style="font-size:7.5px;color:#6b7280;">ADR ({m2(c["adr_h"])} vs {m2(c["adr_o"])})</span></td>\n'
        f'<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{cor_rec};">'
        f'{s_rec} R$ {br(round(abs(c["d_rec"])),0)}</span><br>'
        f'<span style="font-size:7.5px;color:#6b7280;">Receita ({m0(c["rec_h"])} vs {m0(c["rec_o"])})</span></td>\n'
        '</tr></table>\n</td></tr></table>')

    return (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e5e7eb;border-radius:5px;">\n'
        '<tr><td style="padding:10px;">\n'
        '<table cellpadding="0" cellspacing="0" border="0"><tr>\n'
        f'<td style="background-color:{cor_forte};color:#ffffff;font-size:10px;font-weight:800;padding:3px 8px;border-radius:8px;">{h}</td>\n'
        f'<td style="font-size:13px;font-weight:bold;padding-left:6px;">{D["nome"]}</td>\n'
        '</tr></table>\n'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;"><tr>\n'
        f'{kpis}\n</tr></table>\n\n{rec_bar}\n\n{otb_bar}\n\n{box_pace}\n\n{box_hvo}\n\n'
        '</td></tr></table>')


ACENTO_DOW = {"Seg": "Seg", "Ter": "Ter", "Qua": "Qua", "Qui": "Qui",
              "Sex": "Sex", "Sab": "S&aacute;b", "Dom": "Dom"}


def tabela_pickup(h, M, cor_forte):
    D = M["hoteis"][h]
    mes3 = MESES[int(M["mes"])][:3]
    disp = M["pickup_disponivel"]
    prim, ult = D["pickup"][0]["data_br"], D["pickup"][-1]["data_br"]
    titulo = (f'{h} &middot; Pickup por Dia ({prim}&ndash;{ult}) &mdash; análise '
              f'{M["d1_br"]}&rarr;{M["dia"]}/{mes3}') if disp else \
             f'{h} &middot; Previsão por Dia ({prim}&ndash;{ult}) &mdash; sem base D-1'

    cab_delta = ('<td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;'
                 'border-bottom:1px solid #e5e7eb;">&Delta; Pickup</td>') if disp else ''
    linhas = []
    for p in D["pickup"]:
        fds = p["dow"] in ("Sáb", "Dom")
        bg = ' style="background-color:#f0f7ff;"' if fds else ''
        cel = ('<td align="right" style="font-size:9px;color:%s;border-bottom:1px solid #f3f4f6;">%s</td>'
               % ((VERDE if p["delta"] >= 0 else VERMELHO), smc(p["delta"]))) if disp else ''
        linhas.append(
            f'<tr{bg}><td style="font-size:9px;border-bottom:1px solid #f3f4f6;">{ACENTO_DOW.get(p["dow"], p["dow"])} {p["data_br"]}</td>'
            f'<td align="right" style="font-size:9px;border-bottom:1px solid #f3f4f6;">{pc(p["occ_pct"])}</td>'
            f'<td align="right" style="font-size:9px;border-bottom:1px solid #f3f4f6;">{m2(p["adr"])}</td>'
            f'<td align="right" style="font-size:9px;border-bottom:1px solid #f3f4f6;">{m0(p["receita"])}</td>'
            f'{cel}</tr>')

    rec_fut = sum(p["receita"] for p in D["pickup"])
    tot_delta = ('<td align="right" style="font-size:9px;font-weight:800;color:%s;border-top:1.5px solid #d1d5db;">%s</td>'
                 % ((VERDE if D["pickup_total"] >= 0 else VERMELHO), smc(D["pickup_total"]))) if disp else ''
    linhas.append(
        f'<tr style="background-color:#f3f4f6;">'
        f'<td style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">TOTAL {prim}&ndash;{ult}</td>'
        f'<td align="right" style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">&mdash;</td>'
        f'<td align="right" style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">&mdash;</td>'
        f'<td align="right" style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">{m0(rec_fut)}</td>'
        f'{tot_delta}</tr>')

    nota = ('' if disp else
            '\n<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="background-color:#fef3c7;border:1px solid #f59e0b;border-radius:4px;margin-top:4px;">'
            '<tr><td style="padding:6px;font-size:8.5px;color:#92400e;">'
            '<strong>Coluna &Delta; Pickup omitida:</strong> o relatório do dia útil anterior não está '
            'disponível na pasta, então não há base D-1 para comparar as mesmas datas futuras. '
            'Nenhum valor foi estimado.</td></tr></table>')

    return (f'<span style="font-size:9.5px;font-weight:bold;text-transform:uppercase;color:#6b7280;">{titulo}</span>\n'
            '<table width="100%" cellpadding="3" cellspacing="0" border="0" style="border-collapse:collapse;margin-top:4px;">\n'
            '<tr style="background-color:#f3f4f6;">'
            '<td style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">Data</td>'
            '<td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">Occ%</td>'
            '<td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">DM</td>'
            '<td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">Receita</td>'
            f'{cab_delta}</tr>\n' + "\n".join(linhas) + '\n</table>' + nota)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--daily", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.metrics, encoding="utf-8") as f:
        M = json.load(f)
    with open(args.daily, encoding="utf-8") as f:
        DAILY = json.load(f)

    ref = datetime.strptime(M["data_ref"], "%Y-%m-%d").date()
    mes_i = int(M["mes"])
    mes3 = MESES[mes_i][:3]
    M["d1_br"] = f'{ref.day - 1}/{mes3}'
    jan = f'1&ndash;{M["dia"]}/{mes3}'
    rest_ini, rest_fim = M["dia"] + 1, M["dias_no_mes"]

    # comparativo dia corrente (parcial) vs dia anterior, por hotel
    cmps = {}
    for h in ("VB", "VS"):
        eff = DAILY[h]["dias_efetivo"]
        dh, do = eff[-1], eff[-2]
        cmps[h] = {
            "hoje_br": datetime.strptime(dh["data"], "%Y-%m-%d").strftime("%d/%m"),
            "ontem_br": datetime.strptime(do["data"], "%Y-%m-%d").strftime("%d/%m"),
            "occ_h": dh["occ_pct"], "occ_o": do["occ_pct"], "d_occ": round(dh["occ_pct"] - do["occ_pct"], 2),
            "adr_h": dh["adr"], "adr_o": do["adr"], "d_adr": round(dh["adr"] - do["adr"], 2),
            "rec_h": dh["rec_total"], "rec_o": do["rec_total"], "d_rec": round(dh["rec_total"] - do["rec_total"], 2),
        }

    C = M["combinado"]
    gap_comb = C["meta_receita"] - C["otb_total"]
    bateu_comb = gap_comb <= 0
    vb, vs = M["hoteis"]["VB"], M["hoteis"]["VS"]

    # atingimento de meta (mes inteiro, OTB)
    def ating(D):
        mo, mt = D["mes_otb"], D["meta"]
        meta_revpar = mt["occ"] / 100.0 * mt["adr"]
        return {
            "occ": round(mo["occ_pct"] / mt["occ"] * 100, 1),
            "adr": round(mo["adr"] / mt["adr"] * 100, 1),
            "revpar": round(mo["revpar"] / meta_revpar * 100, 1),
            "rec": mt["pct_otb"],
        }
    at = {"VB": ating(vb), "VS": ating(vs)}

    def cor_at(v):
        return VERDE if v >= 100 else (AMBAR if v >= 85 else VERMELHO)

    P = []
    A = P.append

    A('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:820px;margin:0 auto;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#111827;">')

    # ---- cabecalho escuro + badge ----
    A('<tr><td style="background-color:#111827;color:#ffffff;padding:12px 16px;border-radius:5px;">')
    A('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>')
    A(f'<td style="font-size:16px;font-weight:bold;color:#ffffff;">Dashboard Comercial &mdash; {MESES_CAP[mes_i]} {M["ano"]}</td>')
    A(f'<td align="right" style="font-size:11px;font-weight:bold;color:#fcd34d;background-color:#374151;padding:4px 10px;border-radius:10px;">'
      f'{ref.day} de {MESES[mes_i]} de {M["ano"]} ({DOW_FULL[ref.weekday()]})</td>')
    A('</tr></table>')
    A('')
    A('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td style="font-size:10px;color:#9ca3af;padding-top:2px;">Receita Realizada &middot; On the Books &middot; Pace para Meta</td></tr></table>')
    A('</td></tr>')
    A('')
    A('<tr><td style="height:8px;font-size:1px;line-height:8px;">&nbsp;</td></tr>')
    A('')

    # ---- nota de fonte (caixa azul) ----
    pickup_frase = (f'Pickup {rest_ini}&ndash;{rest_fim}/{mes3} calculado comparando a seção '
                    f'&ldquo;Previsão&rdquo; do relatório de hoje contra a de ontem '
                    f'({M["d1_br"]} &rarr; {M["dia"]}/{mes3}), para as mesmas datas futuras.'
                    if M["pickup_disponivel"] else
                    'Pickup não calculado: relatório do dia útil anterior indisponível na pasta.')
    A('<tr><td style="background-color:#eff6ff;border:1px solid #93c5fd;border-radius:4px;padding:8px 12px;font-size:10.5px;color:#1e40af;">')
    A(f'<strong>&#9873; Nota de fonte:</strong> Occ/ADR/RevPAR/Receita extraídos diretamente de '
      f'RELATÓRIO VB {M["dia"]}-{M["mes"]}.xls e RELATÓRIO VS {M["dia"]}-{M["mes"]}.xls '
      f'(fonte oficial FrontOffice). Validação aritmética: Subtotal Efetivo + Subtotal Previsão = TOTALIZAÇÃO '
      f'(confere em VB e VS). {pickup_frase} Metas lidas de metas_2026.json (Budget 2026 rev01). '
      f'YoY contra o relatório oficial anual 2025, janela comparável de {M["dia"]} dias ({jan}).')
    A('</td></tr>')
    A('')
    A('<tr><td style="height:6px;font-size:1px;line-height:6px;">&nbsp;</td></tr>')
    A('')

    # ---- alerta de deslocamento de dia da semana (caixa ambar) ----
    if M["alerta_dow"]["deslocado"]:
        ad = M["alerta_dow"]
        d_at = DOW_FULL[["Segunda","Terca","Quarta","Quinta","Sexta","Sabado","Domingo"].index(ad["dow_atual"])]
        d_an = DOW_FULL[["Segunda","Terca","Quarta","Quinta","Sexta","Sabado","Domingo"].index(ad["dow_anterior"])]
        A('<tr><td style="background-color:#fef3c7;border:1px solid #f59e0b;border-radius:4px;padding:8px 12px;font-size:10.5px;color:#92400e;">')
        A(f'<strong>&#9888; Atenção YoY:</strong> a janela {M["ano"]} ({jan.replace("&ndash;","&ndash;")}) começa num {d_at}; '
          f'a janela {M["ano"]-1} equivalente começa num {d_an} &mdash; período deslocado em '
          f'{ad["dias_diff"]} dia de semana. Leia a comparação YoY como direcional.')
        A('</td></tr>')
        A('')
        A('<tr><td style="height:10px;font-size:1px;line-height:10px;">&nbsp;</td></tr>')
        A('')

    # ---- faixa de KPIs combinados ----
    A('<tr><td style="background-color:#1f2937;border-radius:5px;padding:10px 8px;">')
    A('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>')
    faixa = [
        (m0(C["receita_mtd"]), f'Receita Realiz. (VB+VS) {jan}', "#fcd34d"),
        (m0(C["otb_total"]), "Total On the Books (mês)", "#ffffff"),
        (m0(C["meta_receita"]), "Meta Combinada", "#ffffff"),
        (pc(C["pct_otb_meta"]), "% da Meta (OB/Meta)", "#fcd34d"),
        ((("+ " + m0(abs(gap_comb))) if bateu_comb else ("&ndash; " + m0(abs(gap_comb)))),
         ("Superávit sobre a Meta" if bateu_comb else "Gap para Meta"),
         (VERDE if bateu_comb else "#f87171")),
        (f'{M["dias_no_mes"] - M["dia"]} dias', f'Restantes ({rest_ini}&ndash;{rest_fim}/{mes3})', "#ffffff"),
    ]
    for val, leg, cor in faixa:
        A(f'<td align="center" style="color:#ffffff;padding:4px;">'
          f'<span style="font-size:15px;font-weight:800;color:{cor};">{val}</span><br>'
          f'<span style="font-size:8.5px;color:#9ca3af;text-transform:uppercase;">{leg}</span></td>')
    A('</tr></table>')
    A('</td></tr>')
    A('')
    A('<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>')
    A('')

    # ---- cards VB / VS lado a lado ----
    A('<!-- VB / VS KPI cards side by side -->')
    A('<tr><td>')
    A('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr valign="top">')
    A('<td width="50%" style="padding-right:6px;">')
    A(card_hotel("VB", M, cmps["VB"], "#1a56db", "#93c5fd"))
    A('</td>')
    A('')
    A('<td width="50%" style="padding-left:6px;">')
    A(card_hotel("VS", M, cmps["VS"], "#7e3af2", "#c4b5fd"))
    A('</td>')
    A('</tr></table>')
    A('</td></tr>')
    A('')
    A('<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>')
    A('')

    # ---- tabela de atingimento de meta ----
    A('<!-- Meta attainment table -->')
    A('<tr><td>')
    A('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e5e7eb;border-radius:5px;"><tr><td style="padding:10px;">')
    A(f'<span style="font-size:10.5px;font-weight:bold;text-transform:uppercase;color:#6b7280;">'
      f'Atingimento de Meta &middot; {MESES_CAP[mes_i]} {M["ano"]} (mês inteiro, OTB)</span>')
    A('<table width="100%" cellpadding="6" cellspacing="0" border="0" style="margin-top:6px;border-collapse:collapse;">')
    A('<tr style="background-color:#f3f4f6;">')
    for cab, al in (("Hotel", "left"), ("Occ%", "right"), ("ADR", "right"), ("RevPAR", "right"), ("Receita", "right")):
        algn = '' if al == "left" else ' align="right"'
        A(f'<td{algn} style="font-size:9px;font-weight:bold;color:#6b7280;text-transform:uppercase;border-bottom:1px solid #e5e7eb;">{cab}</td>')
    A('</tr>')
    for h, cor_h, borda in (("VB", "#1a56db", "border-bottom:1px solid #f3f4f6;"), ("VS", "#7e3af2", "")):
        a = at[h]
        A('<tr>')
        A(f'<td style="font-weight:bold;color:{cor_h};{borda}">{h}</td>')
        for k in ("occ", "adr", "revpar", "rec"):
            A(f'<td align="right" style="font-weight:bold;color:{cor_at(a[k])};{borda}">{pc(a[k])}</td>')
        A('</tr>')
    A('</table>')
    A('</td></tr></table>')
    A('</td></tr>')
    A('')
    A('<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>')
    A('')

    # ---- tabelas de pickup lado a lado ----
    A('<!-- Pickup tables side by side -->')
    A('<tr><td>')
    A('<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr valign="top">')
    A('<td width="50%" style="padding-right:6px;">')
    A(tabela_pickup("VB", M, "#1a56db"))
    A('</td>')
    A('<td width="50%" style="padding-left:6px;">')
    A(tabela_pickup("VS", M, "#7e3af2"))
    A('</td>')
    A('</tr></table>')
    A('</td></tr>')
    A('')
    A('<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>')
    A('')

    # ---- observacoes ----
    neg_vb = [p["data_br"] for p in vb["pickup"] if p["delta"] is not None and p["delta"] < 0]
    neg_vs = [p["data_br"] for p in vs["pickup"] if p["delta"] is not None and p["delta"] < 0]

    def frase_pace(h, D):
        p = D["pace"]
        if p["meta_batida"]:
            return (f'<strong>{h}</strong> já bateu a meta do mês: superávit de {m0(p["superavit"])} '
                    f'sobre {m0(D["meta"]["receita"])}.')
        obs = D["pickup_total"]
        folga = "acima" if (obs is not None and obs >= p["diaria_necessaria"]) else "abaixo"
        extra = (f' O pickup observado nas últimas 24h ({m0(obs)}) está <strong>{folga}</strong> '
                 f'do necessário por dia ({m0(p["diaria_necessaria"])}).') if obs is not None else ''
        return (f'<strong>{h}</strong> está a {pc(D["meta"]["pct_otb"])} da meta no OTB '
                f'(gap de {m0(p["gap"])} em {p["dias_restantes"]} dias).{extra}')

    A('<tr><td style="font-size:9px;color:#6b7280;line-height:1.6;">')
    A('<strong style="color:#374151;">Observações:</strong><br>')
    A(f'&middot; <strong>Fonte:</strong> relatório oficial FrontOffice (RELATÓRIO VB/VS {M["dia"]}-{M["mes"]}.xls), '
      f'validado aritmeticamente (Subtotal Efetivo + Previsão = TOTALIZAÇÃO confere em ambos os hotéis).<br>')
    A(f'&middot; <strong>Metas (Budget 2026 rev01, metas_2026.json):</strong> '
      f'VB {m0(vb["meta"]["receita"])} &middot; {pc(vb["meta"]["occ"],1)} &middot; ADR {m0(vb["meta"]["adr"])} '
      f'| VS {m0(vs["meta"]["receita"])} &middot; {pc(vs["meta"]["occ"],1)} &middot; ADR {m0(vs["meta"]["adr"])}.<br>')
    A(f'&middot; {frase_pace("VB", vb)}<br>')
    A(f'&middot; {frase_pace("VS", vs)}<br>')
    if M["pickup_disponivel"]:
        A(f'&middot; <strong>Pickup 24h ({M["d1_br"]} &rarr; {M["dia"]}/{mes3}):</strong> '
          f'VB {smc(vb["pickup_total"])} &middot; VS {smc(vs["pickup_total"])} &middot; '
          f'combinado {smc(C["pickup_total"])} na janela {rest_ini}&ndash;{rest_fim}/{mes3}. '
          + (f'Datas com pickup negativo: VB {", ".join(neg_vb) if neg_vb else "nenhuma"}; '
             f'VS {", ".join(neg_vs) if neg_vs else "nenhuma"}.<br>'))
    else:
        A('&middot; <strong>Pickup:</strong> não disponível hoje &mdash; sem relatório do dia útil anterior '
          'na pasta. Nenhum valor estimado.<br>')
    A(f'&middot; <strong>YoY ({jan}, base comparável de {M["dia"]} dias):</strong> '
      f'VB ocupação {br(vb["yoy"]["occ_pp"],1)} p.p., ADR {"+" if vb["yoy"]["adr_pct"]>=0 else ""}{br(vb["yoy"]["adr_pct"],1)}%, '
      f'RevPAR {"+" if vb["yoy"]["revpar_pct"]>=0 else ""}{br(vb["yoy"]["revpar_pct"],1)}%; '
      f'VS ocupação {"+" if vs["yoy"]["occ_pp"]>=0 else ""}{br(vs["yoy"]["occ_pp"],1)} p.p., '
      f'ADR {"+" if vs["yoy"]["adr_pct"]>=0 else ""}{br(vs["yoy"]["adr_pct"],1)}%, '
      f'RevPAR {"+" if vs["yoy"]["revpar_pct"]>=0 else ""}{br(vs["yoy"]["revpar_pct"],1)}%. '
      f'Rede: RevPAR {"+" if C["revpar_pct"]>=0 else ""}{br(C["revpar_pct"],1)}% '
      f'e ADR {"+" if C["adr_pct"]>=0 else ""}{br(C["adr_pct"],1)}% sobre 2025'
      + (' &mdash; ver nota de deslocamento de dia de semana acima.' if M["alerta_dow"]["deslocado"] else '.')
      + '<br>')
    A('</td></tr>')
    A('')
    A('<tr><td style="height:10px;font-size:1px;line-height:10px;">&nbsp;</td></tr>')
    A('')

    # ---- rodape ----
    fontes = (f'RELATÓRIO VB {M["dia"]}-{M["mes"]}.xls &middot; RELATÓRIO VS {M["dia"]}-{M["mes"]}.xls (fonte oficial)')
    if M["pickup_disponivel"]:
        d1 = ref.day - 1
        fontes += f' &middot; RELATÓRIO VB/VS {d1:02d}-{M["mes"]}.xls (base de pickup D-1)'
    fontes += ' &middot; metas_2026.json &middot; anual_VB/VS_2025.json'
    A('<tr><td align="center" style="font-size:9px;color:#9ca3af;border-top:1px solid #e5e7eb;padding-top:8px;">')
    A(f'{fontes} &nbsp;|&nbsp; Gerado em {M["data_ref_br"]} &nbsp;&middot;&nbsp; '
      f'Período: {MESES[mes_i]} {M["ano"]} &nbsp;&middot;&nbsp; {M["dias_no_mes"] - M["dia"]} dias restantes')
    A('</td></tr>')
    A('</table>')

    html = "\n".join(P) + "\n"

    # ---- guarda-corpo: nada proibido pode passar ----
    import re
    proibidos = [("<style", r"<style"), ("class=", r"class\s*="), ("display:flex", r"display:\s*flex"),
                 ("display:grid", r"display:\s*grid"), ("<!DOCTYPE", r"<!DOCTYPE"),
                 ("<head", r"<head[ >]"), ("<body", r"<body[ >]")]
    erros = [nome for nome, pat in proibidos if re.search(pat, html, re.I)]
    if erros:
        raise SystemExit("ERRO: construcoes proibidas no HTML: " + ", ".join(erros))
    if not html.lstrip().startswith("<table"):
        raise SystemExit("ERRO: HTML nao comeca com <table>")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML salvo em: {args.out} ({len(html)} bytes) | checagem de proibidos: OK")


if __name__ == "__main__":
    main()
