#!/usr/bin/env python3
"""
render_dashboard.py — Monta o HTML final do dashboard (e-mail-safe, tabelas
aninhadas, estilo inline) a partir do JSON já agregado por
build_dashboard_data.py. Segue literalmente a mesma estrutura/tags do
templates/dashboard_template.html. Não interpreta planilhas.
"""
import json
import argparse
import locale

MESES_PT = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
            "agosto", "setembro", "outubro", "novembro", "dezembro"]
MESES_PT_ABREV = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DOW_FULL = {"Seg": "segunda-feira", "Ter": "terça-feira", "Qua": "quarta-feira", "Qui": "quinta-feira",
            "Sex": "sexta-feira", "Sab": "sábado", "Dom": "domingo"}


def brl(v, decimals=0):
    v = round(v, decimals)
    neg = v < 0
    v = abs(v)
    if decimals == 0:
        s = f"{v:,.0f}"
    else:
        s = f"{v:,.{decimals}f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return ("-" if neg else "") + s


def money(v, decimals=0):
    return f"R$ {brl(v, decimals)}"


def pct(v, decimals=1):
    return f"{brl(v, decimals)}%"


def pp(v, decimals=1):
    sign = "+" if v >= 0 else ""
    return f"{sign}{brl(v, decimals)} p.p."


def arrow_span(value, is_pct_points=False, decimals=1, invert=False):
    """Retorna span colorido com seta para uma variação (positivo=verde/alta, negativo=vermelho/queda)."""
    up = value >= 0
    if invert:
        up = not up
    color = "#059669" if up else "#dc2626"
    arrow = "&#9650;" if up else "&#9660;"
    if is_pct_points:
        txt = pp(abs(value) if False else value, decimals).replace("+", "")
        txt = pp(value, decimals)
        # remove sign duplication, keep just number + p.p.
        txt = f"{brl(abs(value), decimals)} p.p."
    else:
        txt = f"{brl(abs(value), decimals)}%"
    return f'<span style="font-size:7.5px;font-weight:bold;color:{color};">{arrow} {txt} vs 2025</span>'


def hoje_ontem_arrow(value, decimals, suffix, invert=False):
    up = value >= 0
    if invert:
        up = not up
    color = "#059669" if up else "#dc2626"
    arrow = "&#9650;" if up else "&#9660;"
    return arrow, color, f"{brl(abs(value), decimals)}{suffix}"


def bar_row(pct_value, color_full, color_bg, label_left, label_right):
    w = max(0, min(100, round(pct_value)))
    return f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#e5e7eb;border-radius:3px;"><tr>
<td width="{w}%" style="background-color:{color_full};font-size:1px;line-height:7px;">&nbsp;</td><td style="font-size:1px;line-height:7px;">&nbsp;</td>
</tr></table>
<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="font-size:7.5px;color:#6b7280;">{label_left}</td>
<td align="right" style="font-size:7.5px;color:{color_bg};">{label_right}</td>
</tr></table>'''


def pickup_rows(dias, alt_every=1):
    rows = []
    for i, d in enumerate(dias):
        dd, mm, _ = d["data"].split("-")[::-1]
        bg = ' style="background-color:#f0f7ff;"' if d["dow"] in ("Sab", "Dom") else ""
        rows.append(f'''<tr{bg}><td style="font-size:9px;border-bottom:1px solid #f3f4f6;">{d["dow"]} {dd}/{mm}</td>'''
                    f'''<td align="right" style="font-size:9px;border-bottom:1px solid #f3f4f6;">{brl(d["occ_pct"],2)}%</td>'''
                    f'''<td align="right" style="font-size:9px;border-bottom:1px solid #f3f4f6;">R${brl(d["adr"],2)}</td>'''
                    f'''<td align="right" style="font-size:9px;border-bottom:1px solid #f3f4f6;">R${brl(d["rec_total"],0)}</td></tr>''')
    return "\n".join(rows)


def hotel_card(hotel, x, color, mes_abrev, dia_str, dias_restantes):
    delta_occ = arrow_span(x["delta_occ_pp"], is_pct_points=True)
    delta_adr = arrow_span(x["delta_adr_pct"])
    delta_revpar = arrow_span(x["delta_revpar_pct"])

    bar_realizada = bar_row(x["pct_meta_realizada"], color, "#6b7280",
                             f'{brl(x["pct_meta_realizada"],1)}% da meta',
                             f'Meta: {money(x["meta_receita"])}')
    bar_otb = bar_row(x["pct_meta_otb"], "#93c5fd" if hotel == "VB" else "#c4b5fd", "#d97706",
                       f'{brl(x["pct_meta_otb"],1)}% da meta',
                       f'Gap: &ndash; {money(x["gap_meta_otb"])}')

    pace = x["pace"]
    hoje_row, ontem_row = x["hoje_row"], x["ontem_row"]
    d_occ = hoje_row["occ_pct"] - ontem_row["occ_pct"]
    d_adr = hoje_row["adr"] - ontem_row["adr"]
    d_adr_pct = (hoje_row["adr"] - ontem_row["adr"]) / ontem_row["adr"] * 100 if ontem_row["adr"] else 0
    d_rec = hoje_row["rec_total"] - ontem_row["rec_total"]
    d_rec_pct = (hoje_row["rec_total"] - ontem_row["rec_total"]) / ontem_row["rec_total"] * 100 if ontem_row["rec_total"] else 0

    a1, c1, t1 = hoje_ontem_arrow(d_occ, 2, " p.p.")
    a2, c2, t2 = hoje_ontem_arrow(d_adr_pct, 2, "%")
    a3, c3, t3 = hoje_ontem_arrow(d_rec_pct, 1, "%")

    nome = "Victory Business" if hotel == "VB" else "Victory Suites"
    ontem_dia, ontem_mes, _ = ontem_row["data"].split("-")[::-1]

    return f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e5e7eb;border-radius:5px;">
<tr><td style="padding:10px;">
<table cellpadding="0" cellspacing="0" border="0"><tr>
<td style="background-color:{color};color:#ffffff;font-size:10px;font-weight:800;padding:3px 8px;border-radius:8px;">{hotel}</td>
<td style="font-size:13px;font-weight:bold;padding-left:6px;">{nome}</td>
</tr></table>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;"><tr>
<td width="33%" align="center" style="background-color:#f9fafb;border:1px solid #e5e7eb;padding:6px 3px;">
<span style="font-size:8px;color:#6b7280;font-weight:bold;text-transform:uppercase;">Ocupação</span><br>
<span style="font-size:14px;font-weight:800;">{brl(x["janela_2026"]["occ_pct"],2)}%</span><br>
<span style="font-size:7.5px;color:#9ca3af;">acum. 01&ndash;{dia_str}/{mes_abrev}</span><br>
{delta_occ}
</td>
<td width="33%" align="center" style="background-color:#f9fafb;border:1px solid #e5e7eb;padding:6px 3px;">
<span style="font-size:8px;color:#6b7280;font-weight:bold;text-transform:uppercase;">ADR</span><br>
<span style="font-size:14px;font-weight:800;">{money(x["janela_2026"]["adr"],2)}</span><br>
<span style="font-size:7.5px;color:#9ca3af;">diária média efetiva</span><br>
{delta_adr}
</td>
<td width="33%" align="center" style="background-color:#f9fafb;border:1px solid #e5e7eb;padding:6px 3px;">
<span style="font-size:8px;color:#6b7280;font-weight:bold;text-transform:uppercase;">RevPAR</span><br>
<span style="font-size:14px;font-weight:800;">{money(x["janela_2026"]["revpar"],2)}</span><br>
<span style="font-size:7.5px;color:#9ca3af;">por UH disp./dia</span><br>
{delta_revpar}
</td>
</tr></table>

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;"><tr>
<td style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">Receita Realizada (até hoje)</td>
<td align="right" style="font-size:10px;font-weight:800;">{money(x["receita_realizada"])}</td>
</tr></table>
{bar_realizada}

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:6px;"><tr>
<td style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">Total On the Books (mês)</td>
<td align="right" style="font-size:10px;font-weight:800;">{money(x["total_otb"])}</td>
</tr></table>
{bar_otb}

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f9fafb;border:1px solid #e5e7eb;border-radius:4px;margin-top:8px;"><tr><td style="padding:6px;">
<span style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">Pace para a Meta &middot; {dias_restantes} dias restantes</span>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px;"><tr>
<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{color};">{money(pace["ob_atual_dia"])}</span><br><span style="font-size:7.5px;color:#6b7280;">OB atual/dia</span></td>
<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:#d97706;">{money(pace["necessario_dia"])}</span><br><span style="font-size:7.5px;color:#6b7280;">Necessário/dia</span></td>
<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:#dc2626;">+ {money(pace["gap_adicional_dia"])}</span><br><span style="font-size:7.5px;color:#6b7280;">Gap adicional/dia</span></td>
</tr></table>
</td></tr></table>

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f9fafb;border:1px solid #e5e7eb;border-radius:4px;margin-top:6px;"><tr><td style="padding:6px;">
<span style="font-size:8px;font-weight:bold;color:#6b7280;text-transform:uppercase;">Hoje ({dia_str}/{mes_abrev}, parcial) vs Ontem ({ontem_dia}/{ontem_mes})</span>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px;"><tr>
<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{c1};">{a1} {t1}</span><br><span style="font-size:7.5px;color:#6b7280;">Ocup. ({brl(hoje_row["occ_pct"],2)}% vs {brl(ontem_row["occ_pct"],2)}%)</span></td>
<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{c2};">{a2} {t2}</span><br><span style="font-size:7.5px;color:#6b7280;">ADR ({money(hoje_row["adr"],2)} vs {money(ontem_row["adr"],2)})</span></td>
<td width="33%" align="center"><span style="font-size:10.5px;font-weight:800;color:{c3};">{a3} {t3}</span><br><span style="font-size:7.5px;color:#6b7280;">Receita ({money(hoje_row["rec_total"])} vs {money(ontem_row["rec_total"])})</span></td>
</tr></table>
</td></tr></table>

</td></tr></table>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    d = json.load(open(args.data))
    hoje_iso = d["hoje"]
    ano, mes, dia = hoje_iso.split("-")
    mes_i = int(mes)
    mes_nome = MESES_PT[mes_i]
    mes_abrev = MESES_PT_ABREV[mes_i]
    dia_str = dia
    dow_full = DOW_FULL.get(d["hoje_dow"], "")

    vb, vs = d["hotels"]["VB"], d["hotels"]["VS"]

    receita_comb = vb["receita_realizada"] + vs["receita_realizada"]
    otb_comb = vb["total_otb"] + vs["total_otb"]
    meta_comb = vb["meta_receita"] + vs["meta_receita"]
    pct_comb = round(otb_comb / meta_comb * 100, 1)
    gap_comb = meta_comb - otb_comb

    dow_alert = ""
    if d.get("dow_shift"):
        ds = d["dow_shift"]
        dow_alert = f'''<tr><td style="background-color:#fef3c7;border:1px solid #f59e0b;border-radius:4px;padding:8px 12px;font-size:10.5px;color:#92400e;">
<strong>&#9888; Atenção YoY:</strong> 01/{mes_abrev}/{ano} cai numa {ds["dow_2026_full"]}; o mesmo dia em {int(ano)-1} caiu numa {ds["dow_2025_full"]} &mdash; janela comparável deslocada em 1 dia de semana. Leia a comparação YoY como direcional.
</td></tr>

<tr><td style="height:10px;font-size:1px;line-height:10px;">&nbsp;</td></tr>
'''

    vb_card = hotel_card("VB", vb, "#1a56db", mes_abrev, dia_str, d["dias_restantes"])
    vs_card = hotel_card("VS", vs, "#7e3af2", mes_abrev, dia_str, d["dias_restantes"])

    def ating_row(hotel, x, color):
        def cell(v, meta_ok_is_high=True):
            c = "#059669" if v >= 100 else "#d97706"
            return f'<td align="right" style="font-weight:bold;color:{c};border-bottom:1px solid #f3f4f6;">{brl(v,1)}%</td>'
        a = x["atingimento"]
        return f'''<tr>
<td style="font-weight:bold;color:{color};border-bottom:1px solid #f3f4f6;">{hotel}</td>
{cell(a["pct_occ"])}
{cell(a["pct_adr"])}
{cell(a["pct_revpar"]) if a["pct_revpar"] is not None else '<td align="right" style="border-bottom:1px solid #f3f4f6;">&mdash;</td>'}
{cell(a["pct_receita"])}
</tr>'''

    ating_table = f'''<tr><td>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e5e7eb;border-radius:5px;"><tr><td style="padding:10px;">
<span style="font-size:10.5px;font-weight:bold;text-transform:uppercase;color:#6b7280;">Atingimento de Meta &middot; {mes_nome.capitalize()} {ano} (mês inteiro, OTB)</span>
<table width="100%" cellpadding="6" cellspacing="0" border="0" style="margin-top:6px;border-collapse:collapse;">
<tr style="background-color:#f3f4f6;">
<td style="font-size:9px;font-weight:bold;color:#6b7280;text-transform:uppercase;border-bottom:1px solid #e5e7eb;">Hotel</td>
<td align="right" style="font-size:9px;font-weight:bold;color:#6b7280;text-transform:uppercase;border-bottom:1px solid #e5e7eb;">Occ%</td>
<td align="right" style="font-size:9px;font-weight:bold;color:#6b7280;text-transform:uppercase;border-bottom:1px solid #e5e7eb;">ADR</td>
<td align="right" style="font-size:9px;font-weight:bold;color:#6b7280;text-transform:uppercase;border-bottom:1px solid #e5e7eb;">RevPAR</td>
<td align="right" style="font-size:9px;font-weight:bold;color:#6b7280;text-transform:uppercase;border-bottom:1px solid #e5e7eb;">Receita</td>
</tr>
{ating_row("VB", vb, "#1a56db")}
{ating_row("VS", vs, "#7e3af2")}
</table>
</td></tr></table>
</td></tr>'''

    def pickup_table(hotel, x):
        rows = pickup_rows(x["pickup_dias"])
        tot_rec = sum(dd["rec_total"] for dd in x["pickup_dias"])
        return f'''<span style="font-size:9.5px;font-weight:bold;text-transform:uppercase;color:#6b7280;">{hotel} &middot; Pickup por Dia (02&ndash;{d["dias_no_mes"]}/{mes_abrev}) &mdash; sem base de comparação (ver observações)</span>
<table width="100%" cellpadding="3" cellspacing="0" border="0" style="border-collapse:collapse;margin-top:4px;">
<tr style="background-color:#f3f4f6;"><td style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">Data</td><td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">Occ%</td><td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">DM</td><td align="right" style="font-size:8px;font-weight:bold;color:#6b7280;border-bottom:1px solid #e5e7eb;">Receita</td></tr>
{rows}
<tr style="background-color:#f3f4f6;"><td style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">TOTAL 02&ndash;{d["dias_no_mes"]}/{mes_abrev}</td><td align="right" style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">&mdash;</td><td align="right" style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">&mdash;</td><td align="right" style="font-size:9px;font-weight:800;border-top:1.5px solid #d1d5db;">{money(tot_rec)}</td></tr>
</table>'''

    html = f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:820px;margin:0 auto;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#111827;">
<tr><td style="background-color:#111827;color:#ffffff;padding:12px 16px;border-radius:5px;">
<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="font-size:16px;font-weight:bold;color:#ffffff;">Dashboard Comercial &mdash; {mes_nome.capitalize()} {ano}</td>
<td align="right" style="font-size:11px;font-weight:bold;color:#fcd34d;background-color:#374151;padding:4px 10px;border-radius:10px;">{dia_str} de {mes_nome} de {ano} ({dow_full})</td>
</tr></table>

<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td style="font-size:10px;color:#9ca3af;padding-top:2px;">Receita Realizada &middot; On the Books &middot; Pace para Meta</td></tr></table>
</td></tr>

<tr><td style="height:8px;font-size:1px;line-height:8px;">&nbsp;</td></tr>

<tr><td style="background-color:#eff6ff;border:1px solid #93c5fd;border-radius:4px;padding:8px 12px;font-size:10.5px;color:#1e40af;">
<strong>&#9873; Nota de fonte:</strong> Dados de hoje ({dia_str}/{mes_abrev}) extraídos de "VBH.xlsx"/"VS.xlsx" (relatório oficial FrontOffice, layout novo em Excel 2007+, mesmas colunas do relatório .xls anterior, sem seções de texto "Efetivo"/"Previsão" &mdash; dias classificados por data (&le; hoje = já em andamento, &gt; hoje = futuro/OTB) usando a data de geração embutida no rodapé da planilha). Validação aritmética (bucket Efetivo + bucket Previsão = TOTALIZAÇÃO) confere para VB e VS. Dados de ontem (31/08) vêm do Relatório VB/VS 31-08.xls oficial (formato legado), também validados (Subtotal Efetivo = TOTALIZAÇÃO, sem seção Previsão remanescente por ser o último dia do mês). Pickup de amanhã em diante não tem base de comparação hoje (ver observações).
</td></tr>

<tr><td style="height:6px;font-size:1px;line-height:6px;">&nbsp;</td></tr>

{dow_alert}<tr><td style="background-color:#1f2937;border-radius:5px;padding:10px 8px;">
<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td align="center" style="color:#ffffff;padding:4px;"><span style="font-size:15px;font-weight:800;color:#fcd34d;">{money(receita_comb)}</span><br><span style="font-size:8.5px;color:#9ca3af;text-transform:uppercase;">Receita Realiz. (VB+VS) 01/{mes_abrev}</span></td>
<td align="center" style="color:#ffffff;padding:4px;"><span style="font-size:15px;font-weight:800;color:#ffffff;">{money(otb_comb)}</span><br><span style="font-size:8.5px;color:#9ca3af;text-transform:uppercase;">Total On the Books (mês)</span></td>
<td align="center" style="color:#ffffff;padding:4px;"><span style="font-size:15px;font-weight:800;color:#ffffff;">{money(meta_comb)}</span><br><span style="font-size:8.5px;color:#9ca3af;text-transform:uppercase;">Meta Combinada</span></td>
<td align="center" style="color:#ffffff;padding:4px;"><span style="font-size:15px;font-weight:800;color:#fcd34d;">{brl(pct_comb,1)}%</span><br><span style="font-size:8.5px;color:#9ca3af;text-transform:uppercase;">% da Meta (OB/Meta)</span></td>
<td align="center" style="color:#ffffff;padding:4px;"><span style="font-size:15px;font-weight:800;color:#f87171;">&ndash; {money(gap_comb)}</span><br><span style="font-size:8.5px;color:#9ca3af;text-transform:uppercase;">Gap para Meta</span></td>
<td align="center" style="color:#ffffff;padding:4px;"><span style="font-size:15px;font-weight:800;color:#ffffff;">{d["dias_restantes"]} dias</span><br><span style="font-size:8.5px;color:#9ca3af;text-transform:uppercase;">Restantes (02&ndash;{d["dias_no_mes"]}/{mes_abrev})</span></td>
</tr></table>
</td></tr>

<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>

<!-- VB / VS KPI cards side by side -->
<tr><td>
<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr valign="top">
<td width="50%" style="padding-right:6px;">
{vb_card}
</td>
<td width="50%" style="padding-left:6px;">
{vs_card}
</td>
</tr></table>
</td></tr>

<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>

<!-- Meta attainment table -->
{ating_table}

<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>

<!-- Pickup tables side by side -->
<tr><td>
<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr valign="top">
<td width="50%" style="padding-right:6px;">
{pickup_table("VB", vb)}
</td>
<td width="50%" style="padding-left:6px;">
{pickup_table("VS", vs)}
</td>
</tr></table>
</td></tr>

<tr><td style="height:12px;font-size:1px;line-height:12px;">&nbsp;</td></tr>

<tr><td style="font-size:9px;color:#6b7280;line-height:1.6;">
<strong style="color:#374151;">Observações:</strong><br>
&middot; <strong>Fonte:</strong> hoje ({dia_str}/{mes_abrev}) vem de VBH.xlsx/VS.xlsx (layout novo do FrontOffice, mesmas colunas do formato anterior); ontem (31/{MESES_PT_ABREV[8]}) vem do Relatório VB/VS 31-08.xls oficial (formato legado) &mdash; ambos validados aritmeticamente.<br>
&middot; <strong>Δ Pickup indisponível:</strong> hoje é o 1&ordm; dia de {mes_nome}; o relatório de ontem (31/{MESES_PT_ABREV[8]}) cobre só até 31/{MESES_PT_ABREV[8]} e não tem previsão para nenhuma data de {mes_nome}, então não há uma base do dia anterior para calcular o pickup das datas futuras deste mês. As tabelas abaixo mostram os valores em carteira de hoje (Occ/ADR/Receita), sem a coluna de variação.<br>
&middot; Metas do mês (Budget 2026 rev01, cache/metas_2026.json): VB {money(vb["meta_receita"])} / ADR {money(vb["meta_adr"],0)} / Occ {brl(vb["meta_occ"],1)}% &middot; VS {money(vs["meta_receita"])} / ADR {money(vs["meta_adr"],0)} / Occ {brl(vs["meta_occ"],1)}%.<br>
&middot; Sendo o 1&ordm; dia do mês, "Receita Realizada" e "% da meta" ainda refletem só uma fração do dia 01 (relatório gerado pela manhã) &mdash; a maior parte da receita do mês está em "Total On the Books" (reservas já confirmadas para os próximos {d["dias_restantes"]} dias).<br>
&middot; <strong>YoY validado</strong> contra o relatório oficial anual 2025 (base comparável: 1 dia, 01/{mes_abrev}): {"VS recua em ocupação" if vs["delta_occ_pp"] and vs["delta_occ_pp"]<0 else "VS cresce em ocupação"} ({pp(vs["delta_occ_pp"])}) mas ADR (+{brl(vs["delta_adr_pct"],1)}%) e RevPAR (+{brl(vs["delta_revpar_pct"],1)}%) seguem acima do ano anterior; VB cresce em todos os indicadores (Occ {pp(vb["delta_occ_pp"])}, ADR +{brl(vb["delta_adr_pct"],1)}%, RevPAR +{brl(vb["delta_revpar_pct"],1)}%). Ver nota de deslocamento de dia de semana acima &mdash; com base de apenas 1 dia, leia a comparação como direcional, não estatisticamente robusta.
</td></tr>

<tr><td style="height:10px;font-size:1px;line-height:10px;">&nbsp;</td></tr>

<tr><td align="center" style="font-size:9px;color:#9ca3af;border-top:1px solid #e5e7eb;padding-top:8px;">
VBH.xlsx &middot; VS.xlsx (fonte oficial, hoje) &nbsp;|&nbsp; Relatório VB/VS 31-08.xls (fonte oficial, ontem) &nbsp;|&nbsp; Gerado em {dia_str}/{mes_abrev}/{ano} &nbsp;&middot;&nbsp; Período: {mes_nome} {ano} &nbsp;&middot;&nbsp; {d["dias_restantes"]} dias restantes
</td></tr>
</table>'''

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML salvo em:", args.out, "| tamanho:", len(html), "bytes")


if __name__ == "__main__":
    main()
