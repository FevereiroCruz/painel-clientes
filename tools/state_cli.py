#!/usr/bin/env python3
"""Abre e fecha o estado criptografado de um cliente.

  python3 tools/state_cli.py abrir  --config CONFIG.json --cliente grupo-shark --saida estado.json
  python3 tools/state_cli.py fechar --config CONFIG.json --cliente grupo-shark --entrada estado.json
  python3 tools/state_cli.py prova  --entrada estado.json --img print.jpg --occ DIG-2026-010 --marca agrotrator \
        --legenda "..." --url "..." --quando "28/10/2026, 07h12"

O arquivo aberto (estado.json) contém dados confidenciais: mantenha-o só na área temporária da sessão.
"""
import argparse, base64, io, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_panel as bp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def client(cfg, cid):
    return next(c for c in cfg['clients'] if c['id'] == cid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('acao', choices=['abrir', 'fechar', 'prova'])
    ap.add_argument('--config'); ap.add_argument('--cliente')
    ap.add_argument('--saida'); ap.add_argument('--entrada')
    ap.add_argument('--img'); ap.add_argument('--occ', nargs='*', default=[]); ap.add_argument('--marca', nargs='*', default=[])
    ap.add_argument('--legenda'); ap.add_argument('--url', default=''); ap.add_argument('--quando')
    a = ap.parse_args()
    if a.acao in ('abrir', 'fechar'):
        cfg = json.load(open(a.config)); c = client(cfg, a.cliente)
        path = os.path.join(ROOT, 'state', c['id'] + '.enc')
        if a.acao == 'abrir':
            json.dump(bp.load_state(path, c['stateKey']), open(a.saida, 'w'), ensure_ascii=False, indent=1)
        else:
            bp.save_state(path, c['stateKey'], json.load(open(a.entrada)))
        print('ok'); return
    # prova: comprime a captura e anexa ao estado
    from PIL import Image
    st = json.load(open(a.entrada))
    im = Image.open(a.img).convert('RGB')
    if im.width > 1229: im = im.resize((1229, int(im.height * 1229 / im.width)))
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=72, optimize=True)
    n = max([int(p['id'][1:]) for p in st['provas']] + [0]) + 1
    st['provas'].append(dict(id=f'P{n:02d}', occ=a.occ, f=a.marca, cap=a.legenda, url=a.url, quando=a.quando,
                             w=im.width, h=im.height, img='data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()))
    json.dump(st, open(a.entrada, 'w'), ensure_ascii=False, indent=1)
    print(f'P{n:02d}')


if __name__ == '__main__':
    main()
