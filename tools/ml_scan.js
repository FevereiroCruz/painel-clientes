// Mercado Livre: coleta os anúncios da página aberta (loja oficial ou resultado de busca) com a
// "impressão digital" visual (dHash, 64 bits) da foto principal, já normalizada para a versão original
// da imagem (o ML serve a mesma foto em recortes diferentes; sem normalizar, a comparação falha).
// Uso: colar inteiro no javascript_tool com a aba do Mercado Livre aberta. Retorna JSON.
// Comparação: distância de Hamming entre os bits. 0 a 10 = mesma foto (cópia provável); acima de 20 = foto diferente.
// Validado em 27/10/2026: anúncio oficial x ele mesmo = 0; anúncios de outras lojas do mesmo produto = 22 a 36.
await (async () => {
  await new Promise(r => setTimeout(r, 2500));
  const canon = u => { const m = u.match(/(\d+-ML[A-Z]\d+_\d+)/); return m ? `https://http2.mlstatic.com/D_NQ_NP_${m[1]}-O.webp` : u; };
  async function dhash(u) {
    const r = await fetch(canon(u), { mode: 'cors' }); if (!r.ok) throw new Error(String(r.status));
    const bm = await createImageBitmap(await r.blob());
    const cv = new OffscreenCanvas(9, 8), x = cv.getContext('2d'); x.drawImage(bm, 0, 0, 9, 8);
    const d = x.getImageData(0, 0, 9, 8).data; let bits = '';
    for (let y = 0; y < 8; y++) for (let i = 0; i < 8; i++) { const p = (y * 9 + i) * 4, q = p + 4; bits += (d[p] + d[p + 1] + d[p + 2]) > (d[q] + d[q + 1] + d[q + 2]) ? '1' : '0'; }
    return bits;
  }
  const cards = [...document.querySelectorAll('li.ui-search-layout__item, div.poly-card')];
  const out = new Map();
  for (const c of cards) {
    const a = c.querySelector('a.poly-component__title, a[href*="mercadolivre.com.br/"]'); const i = c.querySelector('img');
    if (!a || !i) continue;
    const img = i.currentSrc || i.getAttribute('data-src') || i.src; const id = (img.match(/(\d+-ML[A-Z]\d+_\d+)/) || [])[1];
    if (!id || out.has(id)) continue;
    const s = c.querySelector('.poly-component__seller, .ui-search-official-store-label');
    const p = c.querySelector('.andes-money-amount__fraction');
    out.set(id, { titulo: (c.querySelector('.poly-component__title, h2, h3') || a).textContent.trim(), url: a.href.split('#')[0],
                  vendedor: s ? s.textContent.replace(/^por\s+/i, '').trim() : '', preco: p ? p.textContent.trim() : '', fotoId: id, foto: canon(img) });
    if (out.size >= 50) break;
  }
  const items = [...out.values()];
  for (const it of items) { try { it.hash = await dhash(it.foto); } catch (e) { it.hash = null; } }
  return JSON.stringify(items);
})();
