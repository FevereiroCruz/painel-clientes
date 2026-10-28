#!/usr/bin/env python3
"""Gera os painéis de clientes da Fevereiro & Cruz.

Uso:
  python3 tools/build_panel.py --config CONFIG.json --work DIR_COM_PLANILHAS --out RAIZ_DO_REPOSITORIO

- CONFIG.json fica no computador do escritório (nunca no repositório): códigos de acesso,
  chave do estado e nomes das planilhas de cada cliente.
- O estado de cada cliente (ocorrências digitais, provas, registro de anúncios vistos) fica em
  state/<cliente>.enc, criptografado com a chave do CONFIG.
- As planilhas (processos, notificações, ocorrências) são copiadas do computador para DIR_COM_PLANILHAS.
"""
import argparse, base64, datetime, json, os, re, secrets, sys
import openpyxl
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
TZ = datetime.timezone(datetime.timedelta(hours=-3))
ITER = 600000


# ---------- estado criptografado ----------
def load_state(path, key_b64):
    blob = json.load(open(path))
    key = base64.b64decode(key_b64)
    pt = AESGCM(key).decrypt(base64.b64decode(blob['iv']), base64.b64decode(blob['ct']), None)
    return json.loads(pt)


def save_state(path, key_b64, state):
    key = base64.b64decode(key_b64)
    iv = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(iv, json.dumps(state, ensure_ascii=False).encode(), None)
    json.dump({'iv': base64.b64encode(iv).decode(), 'ct': base64.b64encode(ct).decode()}, open(path, 'w'))


def encrypt_payload(data, code):
    salt = secrets.token_bytes(16); iv = secrets.token_bytes(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(code.encode())
    ct = AESGCM(key).encrypt(iv, json.dumps(data, ensure_ascii=False).encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return json.dumps({'salt': b(salt), 'iv': b(iv), 'it': ITER, 'ct': b(ct)})


# ---------- leitura das planilhas ----------
def d_iso(v):
    return v.strftime('%Y-%m-%d') if hasattr(v, 'strftime') else (str(v).strip() if v is not None else '')


def d_br(v):
    if v is None: return ''
    if hasattr(v, 'strftime'): return v.strftime('%d/%m/%Y')
    return str(v).strip()


def read_processos(path, fam_map):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb['PROCESSOS']
    mod = wb.properties.modified
    out, unmapped = [], set()
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None: continue
        marca = str(r[3]).strip()
        fam = fam_map.get(marca)
        if not fam:
            unmapped.add(marca); continue
        out.append({'n': str(r[0]).strip(), 'dep': d_iso(r[1]), 'tit': str(r[2]).strip(), 'marca': marca,
                    'apr': str(r[4]).strip().capitalize(), 'cls': str(r[6]).strip(), 'esp': (r[7] or '').strip(),
                    'st': str(r[8]).strip(), 'vig': d_iso(r[9]), 'f': fam})
    return out, sorted(unmapped), (mod.strftime('%d/%m/%Y') if mod else '')


def clean_site(s):
    out = []
    for part in re.split(r'\s+-\s+|\s+e\s+', s or ''):
        part = part.strip()
        if part: out.append(part.split('?')[0].rstrip('#'))
    return out


def read_notificacoes(path, cnpj_map):
    wb = openpyxl.load_workbook(path, data_only=True)
    out = []
    for sh in ['NOTIFICAÇÕES', 'CONCLUÍDAS', 'VIOLAÇÕES ANÚNCIOS']:
        if sh not in wb.sheetnames: continue
        for r in wb[sh].iter_rows(min_row=2, values_only=True):
            fam = cnpj_map.get(d_br(r[4]))
            if not fam: continue
            out.append(dict(ref=d_br(r[2]), envio=d_br(r[1]), cliente=d_br(r[3]).rstrip('.'), marca=d_br(r[5]),
                            notificado=d_br(r[6]), cnpjNot=d_br(r[7]), sites=clean_site(d_br(r[8])),
                            momento=d_br(r[10]) or 'SEM STATUS', hist=d_br(r[11]),
                            concluida=(d_br(r[12]).upper() == 'SIM' or sh == 'CONCLUÍDAS'), f=fam,
                            origem=('Anúncios e redes' if sh == 'VIOLAÇÕES ANÚNCIOS' else 'Nome empresarial e marca')))
    return out


def apply_notif_ajustes(notifs, ajustes):
    """Ajustes vindos do Reggente (CRM do escritório), guardados no estado.

    Cada ajuste tem `notificado` (trecho do nome do notificado, sem diferenciar maiúsculas) e, se quiser,
    `ref`. Se casar com uma linha da planilha, os campos do ajuste substituem os da planilha; senão, o
    ajuste entra como notificação nova (precisa de `f`, `marca`, `cliente`, `momento`).
    """
    out = [dict(n) for n in notifs]
    for a in ajustes:
        alvo = a['notificado'].lower()
        hit = next((n for n in out if alvo in n['notificado'].lower() and (not a.get('refPlanilha') or n['ref'] == a['refPlanilha'])), None)
        campos = {k: v for k, v in a.items() if k not in ('notificado', 'refPlanilha', 'fonte')}
        if hit:
            hit.update(campos)
        else:
            base = dict(ref='', envio='', cliente='', marca='', notificado=a['notificado'], cnpjNot='', sites=[],
                        momento='SEM STATUS', hist='', concluida=False, f='', origem='Nome empresarial e marca')
            base.update(campos); out.append(base)
    return out


def read_ocorrencias(path):
    """Planilha CONTROLE OCORRÊNCIAS DIGITAIS: a equipe atualiza status, preservação, denúncia e remoção."""
    if not path or not os.path.exists(path): return {}
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb['OCORRÊNCIAS']
    head = [c.value for c in ws[1]]
    rows = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r[0]: continue
        rows[str(r[0]).strip()] = {h: r[i] for i, h in enumerate(head)}
    return rows


def acoes_from_row(row, notifs):
    parts = []
    if str(row.get('PROVA PRESERVADA?') or '').upper() == 'SIM':
        extra = [x for x in [row.get('FORMA DE PRESERVAÇÃO'), d_br(row.get('DATA PRESERVAÇÃO'))] if x]
        parts.append('Prova preservada' + (f" ({', '.join(extra)})" if extra else '') + '.')
    if str(row.get('DENÚNCIA ABERTA?') or '').upper() == 'SIM':
        extra = [x for x in [row.get('CANAL DA DENÚNCIA') and f"canal: {row.get('CANAL DA DENÚNCIA')}",
                             row.get('PROTOCOLO DA DENÚNCIA') and f"protocolo {row.get('PROTOCOLO DA DENÚNCIA')}",
                             d_br(row.get('DATA DENÚNCIA'))] if x]
        parts.append('Denúncia aberta' + (f" ({', '.join(extra)})" if extra else '') + '.')
    ref = d_br(row.get('N° REF NOTIFICAÇÃO'))
    if ref:
        n = next((x for x in notifs if x['ref'] == ref), None)
        parts.append(f"Notificação extrajudicial enviada{(' em ' + n['envio']) if n and n['envio'] else ''} (ref. {ref}).")
    if row.get('DATA REMOÇÃO'):
        parts.append(f"Conteúdo removido em {d_br(row.get('DATA REMOÇÃO'))}.")
    return ' '.join(parts)


def merge_occ(state_occ, rows, notifs):
    occ = [dict(o) for o in state_occ]
    for o in occ:
        row = rows.get(o['id'])
        if not row: continue
        if row.get('STATUS'): o['status'] = str(row['STATUS']).strip()
        if row.get('RISCO'): o['risco'] = str(row['RISCO']).strip()
        a = acoes_from_row(row, notifs)
        if a: o['acoes'] = a
        if row.get('MOMENTO / ANDAMENTO'): o['proximo'] = str(row['MOMENTO / ANDAMENTO']).strip()
        ref = d_br(row.get('N° REF NOTIFICAÇÃO'))
        if ref: o['notif'] = ref
        if str(row.get('CONCLUÍDA?') or '').upper() == 'SIM' and o['status'] not in ('Removido', 'Arquivado'):
            o['status'] = 'Removido'
    return occ


# ---------- montagem ----------
def build_client(cfg_client, work, out_root, now):
    state_path = os.path.join(ROOT, 'state', cfg_client['id'] + '.enc')
    st = load_state(state_path, cfg_client['stateKey'])
    procs, unmapped, carteira = read_processos(os.path.join(work, cfg_client['processos']), st['famMap'])
    notifs = read_notificacoes(os.path.join(work, cfg_client['notificacoes']), st['cnpjMap'])
    notifs = apply_notif_ajustes(notifs, st.get('notifsAjustes', []))
    rows = read_ocorrencias(os.path.join(work, cfg_client.get('ocorrencias', '')) if cfg_client.get('ocorrencias') else '')
    occ = merge_occ(st['occ'], rows, notifs)
    data = dict(atualizado=now.strftime('%d/%m/%Y, %Hh%M'), varredura=st['varredura'],
                carteiraAtualizada=carteira,
                families=st['families'], variantes=st.get('variantes', {}), procs=procs, occ=occ, plano=st['plano'], notifs=notifs, provas=st['provas'])
    tpl = open(os.path.join(TOOLS, 'site_template.html')).read()
    av = open(os.path.join(TOOLS, 'avatar.b64')).read().strip()
    html = tpl.replace('__AVATAR__', av).replace('__CLIENTE__', cfg_client['nome']).replace('__PAYLOAD__', encrypt_payload(data, cfg_client['code']))
    d = os.path.join(out_root, cfg_client['slug']); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'index.html'), 'w').write(html)
    summary = dict(cliente=cfg_client['nome'], contato=cfg_client.get('contato', ''), marcas=len(st['families']),
                   processos=len(procs), link=cfg_client['link'], codigo=cfg_client['code'],
                   ultima=now.strftime('%d/%m/%Y'), varredura=st['varredura'].split(',')[0],
                   ocorrencias=len(occ), criticas=sum(1 for o in occ if o['risco'] == 'Crítico' and o['status'] not in ('Removido', 'Arquivado')),
                   altas=sum(1 for o in occ if o['risco'] == 'Alto' and o['status'] not in ('Removido', 'Arquivado')),
                   notifAbertas=sum(1 for n in notifs if not n['concluida']),
                   rotina=cfg_client.get('rotina', ''), obs=cfg_client.get('obs', ''),
                   fontes=[cfg_client['processos'], cfg_client['notificacoes']] + ([cfg_client['ocorrencias']] if rows else []))
    if cfg_client.get('alt'): summary['alt'] = cfg_client['alt']
    return summary, dict(procs=len(procs), notifs=len(notifs), occ=len(occ), provas=len(st['provas']),
                         planilhaOcorrencias=bool(rows), unmapped=unmapped)


def build_office(cfg, summaries, out_root, now):
    tpl = open(os.path.join(TOOLS, 'office_template.html')).read()
    av = open(os.path.join(TOOLS, 'avatar.b64')).read().strip()
    data = {'atualizado': now.strftime('%d/%m/%Y, %Hh%M'), 'paineis': summaries}
    html = tpl.replace('__AV__', av).replace('__P__', encrypt_payload(data, cfg['master']))
    d = os.path.join(out_root, cfg['officeSlug']); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'index.html'), 'w').write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--out', default=ROOT)
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    now = datetime.datetime.now(TZ)
    summaries, report = [], {}
    for c in cfg['clients']:
        s, r = build_client(c, a.work, a.out, now)
        summaries.append(s); report[c['id']] = r
    build_office(cfg, summaries, a.out, now)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
