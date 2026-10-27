// Biblioteca de Anúncios da Meta: resume os anúncios da página de resultados aberta (ativos e inativos).
// Uso: colar inteiro no javascript_tool com a busca aberta (active_status=all). Retorna JSON com
// [status, id da biblioteca, período, página anunciante, início do texto].
await (async () => {
  for (let i = 0; i < 3; i++) { window.scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, 1000)); }
  const txt = document.body.innerText;
  const total = (txt.match(/~?([\d.]+) resultados?/) || [])[0] || '';
  const parts = txt.split(/\n(?=(?:Ativo|Inativo)\nIdentificação da biblioteca:)/).slice(1);
  return JSON.stringify({ total, ads: parts.map(p => {
    const l = p.split('\n').map(s => s.trim()).filter(s => s && s !== '​'); const k = l.indexOf('Patrocinado');
    return [l[0], (p.match(/biblioteca: (\d+)/) || [])[1], (p.match(/(Veiculação iniciada em [^\n]+|\d+ de \w+ de \d{4} a [^\n]+)/) || [])[1],
            k > 0 ? l[k - 1] : '', k > 0 ? l.slice(k + 1).join(' ').slice(0, 140) : ''];
  }) });
})();
