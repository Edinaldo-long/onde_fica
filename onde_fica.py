"""
ONDE FICA? - consulta de local de matéria-prima pelo celular (somente leitura).

Como usar:
    pip install flask firebirdsql waitress "qrcode[pil]"
    python onde_fica.py          -> sobe o site na rede local
    python onde_fica.py qr       -> gera qr.png apontando para o site

Só aceita acessos da rede local (REDE_PERMITIDA). Só faz SELECT no banco.
Só mostra itens dos locais de estoque listados em LOCAIS_PERMITIDOS.
"""
import ipaddress
import os
import sys
import unicodedata
from datetime import date, datetime

import firebirdsql
from flask import Flask, Response, abort, jsonify, request

# ---------- CONFIGURAÇÃO (troque por variáveis de ambiente quando puder) ----------
DB_HOST = os.getenv("DB_HOST", "192.168.100.108")
DB_NAME = os.getenv("DB_NAME", "3")
DB_USER = os.getenv("DB_USER", "SYSDBA")  # ideal: usuário só com SELECT
DB_PASS = os.getenv("DB_PASSWORD", "masterkey")  # ideal: trocar a senha padrão

REDE_PERMITIDA = ipaddress.ip_network(os.getenv("REDE_PERMITIDA", "192.168.100.0/24"))
PORTA_WEB = int(os.getenv("PORTA_WEB", "5000"))
URL_SITE = os.getenv("URL_SITE", f"http://192.168.100.121:{PORTA_WEB}")
DIAS_ATENCAO = 30  # lote que vence em até N dias fica amarelo
MAX_PRODUTOS = 20

# Só estes locais de estoque aparecem nas buscas.
LOCAIS_PERMITIDOS = [
    "ARMARIO DERMATO",
    "ARMARIO SUPERIOR",
    "ARMÁRIO CONTROLADOS",
    "CAIXA 1",
    "CAIXA 2",
    "CAIXA 3",
    "CAIXA 4",
    "CAIXA HOMEOPATIA 1",
    "CAIXA HOMEOPATIA 2",
    "CUBO 1",
    "CUBO 2",
    "GAVETA 1",
    "GAVETA 2",
    "GAVETA 3",
    "GELADEIRA TERMOLÁBEIS",
    "LABORATORIO CAPSULAS",
    "LABORATORIO LÍQUIDOS E SEMI-SÓLIDOS",
]


def _norm(txt):
    """Maiúsculo, sem acento e sem espaços: 'Armário Dermato ' -> 'ARMARIODERMATO'."""
    s = unicodedata.normalize("NFD", str(txt or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return "".join(s.upper().split())


LOCAIS_NORM = {_norm(x) for x in LOCAIS_PERMITIDOS}

app = Flask(__name__)


@app.before_request
def somente_rede_local():
    try:
        ip = ipaddress.ip_address(request.remote_addr)
    except ValueError:
        abort(403)
    if not (ip in REDE_PERMITIDA or ip.is_loopback):
        abort(403)


def conectar():
    return firebirdsql.connect(
        host=DB_HOST,
        port=3050,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        charset="WIN1252",
        auth_plugin_name="Legacy_Auth",
    )


def codigos_locais_permitidos(cur):
    """Códigos (no banco) dos locais cujo nome está em LOCAIS_PERMITIDOS."""
    cur.execute("SELECT CD_LOCALIZACAO_LOTE, DS_LOCALIZACAO_LOTE FROM T_LOCALIZACAO_LOTE")
    return [cd for cd, ds in cur.fetchall() if _norm(ds) in LOCAIS_NORM]


def normalizar_unidade(tp):
    chave = str(tp).strip().upper() if tp is not None else ""
    if chave in ("1", "KILO", "KG", "QUILO"):
        return "kg", 1000000.0
    if chave in ("2", "L", "LITRO"):
        return "L", 1000000.0
    if chave in ("3", "ML"):
        return "ml", 1000.0
    if chave in ("4", "UI"):
        return "UI", 1.0
    if chave in ("5", "UN", "CAPS", "UNIDADE"):
        return "un", 1.0
    return "g", 1000.0


def formatar_quantidade(valor, tp):
    sigla, divisor = normalizar_unidade(tp)
    num = float(valor or 0.0) / divisor
    if num.is_integer():
        return f"{int(num)} {sigla}"
    return f"{num:.3f}".rstrip("0").rstrip(".").replace(".", ",") + f" {sigla}"


def status_validade(dt_val):
    """Devolve (status, aviso): vencido / atencao / ok / sem-data."""
    if dt_val is None:
        return "sem-data", ""
    d = dt_val.date() if isinstance(dt_val, datetime) else dt_val
    dias = (d - date.today()).days
    if dias < 0:
        return "vencido", f"vencido há {-dias} d"
    if dias == 0:
        return "atencao", "vence hoje"
    if dias <= DIAS_ATENCAO:
        return "atencao", f"vence em {dias} d"
    return "ok", ""


@app.route("/api/buscar")
def buscar():
    termo = request.args.get("q", "").strip()
    if len(termo) < 2:
        return jsonify([])
    try:
        con = conectar()
    except Exception:
        return jsonify({"erro": "Não consegui conectar ao banco."}), 503
    try:
        cur = con.cursor()

        locais = codigos_locais_permitidos(cur)
        if not locais:
            return jsonify([])
        marcas_loc = ",".join("?" * len(locais))

        cur.execute(
            f"""
            SELECT FIRST {MAX_PRODUTOS} CD_PRODUTO, DS_PRODUTO, COALESCE(TP_UNIDADE, '0')
            FROM T_PRODUTO p
            WHERE (UPPER(DS_PRODUTO) LIKE UPPER(?)
                   OR TRIM(CAST(CD_PRODUTO AS VARCHAR(20))) LIKE ?)
              AND EXISTS (SELECT 1 FROM T_PRODUTO_LOTE x
                          WHERE x.CD_PRODUTO = p.CD_PRODUTO
                            AND x.QT_ESTOQUE > 0
                            AND x.CD_LOCALIZACAO_LOTE IN ({marcas_loc}))
            ORDER BY DS_PRODUTO
            """,
            (f"%{termo}%", f"%{termo}%", *locais),
        )
        produtos = cur.fetchall()
        if not produtos:
            return jsonify([])

        ids = [p[0] for p in produtos]
        marcas = ",".join("?" * len(ids))
        cur.execute(
            f"""
            SELECT l.CD_PRODUTO, l.NR_LOTE, l.QT_ESTOQUE, l.DT_VALIDADE,
                   COALESCE(loc.DS_LOCALIZACAO_LOTE, 'SEM LOCAL'),
                   COALESCE(l.ID_LOTE_USO, 'N')
            FROM T_PRODUTO_LOTE l
            LEFT JOIN T_LOCALIZACAO_LOTE loc
                   ON loc.CD_LOCALIZACAO_LOTE = l.CD_LOCALIZACAO_LOTE
            WHERE l.CD_PRODUTO IN ({marcas}) AND l.QT_ESTOQUE > 0
              AND l.CD_LOCALIZACAO_LOTE IN ({marcas_loc})
            ORDER BY l.DT_VALIDADE
            """,
            [*ids, *locais],
        )
        lotes = cur.fetchall()
    except Exception:
        return jsonify({"erro": "Erro ao consultar o banco."}), 500
    finally:
        con.close()

    por_produto = {}
    for cd, nr_lote, saldo, dt_val, local, em_uso in lotes:
        st, aviso = status_validade(dt_val)
        por_produto.setdefault(cd, []).append(
            {
                "lote": str(nr_lote).strip(),
                "local": str(local).strip(),
                "saldo": saldo,
                "validade": dt_val.strftime("%d/%m/%y") if dt_val else "--/--/--",
                "status": st,
                "aviso": aviso,
                "em_uso": str(em_uso).strip().upper() == "S",
            }
        )

    resposta = []
    for cd, nome, tp in produtos:
        itens = por_produto.get(cd, [])
        for it in itens:
            it["saldo"] = formatar_quantidade(it["saldo"], tp)
        resposta.append(
            {"codigo": str(int(float(cd))), "nome": str(nome).strip(), "lotes": itens}
        )
    return jsonify(resposta)


PAGINA = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Onde fica?</title>
<style>
  :root {
    color-scheme: light dark;
    --fundo:#eef2f4; --card:#ffffff; --tinta:#14202b; --suave:#5b6b78; --linha:#d5dde2;
    --local:#0b5c63; --ok:#1d7a46; --atencao:#a86400; --vencido:#b3261e;
  }
  @media (prefers-color-scheme: dark) {
    :root { --fundo:#0f171c; --card:#18232a; --tinta:#e8eef1; --suave:#93a4af; --linha:#2b3a43;
            --local:#6fd3da; --ok:#6fcf97; --atencao:#f2b34d; --vencido:#ff8a80; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--fundo); color:var(--tinta);
         font:16px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  header { position:sticky; top:0; background:var(--fundo); padding:14px 14px 10px;
           border-bottom:1px solid var(--linha); }
  h1 { margin:0 0 10px; font-size:20px; }
  input { width:100%; padding:14px; font-size:18px; border-radius:10px;
          border:2px solid var(--linha); background:var(--card); color:var(--tinta); }
  input:focus-visible { outline:3px solid var(--local); border-color:var(--local); }
  main { padding:14px; max-width:640px; margin:0 auto; }
  .aviso { color:var(--suave); text-align:center; margin:32px 8px; }
  .produto { background:var(--card); border:1px solid var(--linha); border-radius:12px;
             padding:14px; margin-bottom:14px; }
  .produto h2 { margin:0 0 2px; font-size:17px; }
  .cod { color:var(--suave); font-size:14px; margin-bottom:10px; }
  .lote { border-top:1px solid var(--linha); padding:10px 0 2px; }
  .local { font-size:24px; font-weight:700; color:var(--local); line-height:1.15; }
  .detalhe { color:var(--suave); font-size:14px; margin-top:4px; }
  .ok { color:var(--ok); } .atencao { color:var(--atencao); } .vencido { color:var(--vencido); font-weight:700; }
  .uso { font-size:13px; font-weight:600; }
</style>
</head>
<body>
<header>
  <h1>Onde fica?</h1>
  <input id="q" type="search" inputmode="search" autocomplete="off" autofocus
         placeholder="Nome ou código da matéria-prima" aria-label="Buscar matéria-prima">
</header>
<main id="res"><p class="aviso">Digite o nome ou o código para ver onde a matéria-prima está guardada.</p></main>
<script>
  const q = document.getElementById("q"), res = document.getElementById("res");
  let timer, atual = 0;

  function el(tag, cls, txt) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined) e.textContent = txt;
    return e;
  }
  function msg(txt) { res.replaceChildren(el("p", "aviso", txt)); }

  function desenhar(lista) {
    if (!lista.length) return msg("Nenhuma matéria-prima encontrada.");
    res.replaceChildren();
    for (const p of lista) {
      const card = el("section", "produto");
      card.append(el("h2", "", p.nome), el("div", "cod", "Código " + p.codigo));
      if (!p.lotes.length) card.append(el("div", "detalhe", "Sem saldo em estoque."));
      for (const l of p.lotes) {
        const box = el("div", "lote");
        box.append(el("div", "local", l.local));
        const d1 = el("div", "detalhe", "Lote " + l.lote + " · Saldo " + l.saldo);
        const d2 = el("div", "detalhe " + l.status, "Validade " + l.validade + (l.aviso ? " (" + l.aviso + ")" : ""));
        box.append(d1, d2);
        if (l.em_uso) box.append(el("div", "detalhe uso", "Lote em uso"));
        card.append(box);
      }
      res.append(card);
    }
  }

  async function buscar() {
    const termo = q.value.trim();
    if (termo.length < 2) return msg("Digite pelo menos 2 letras ou números.");
    const minha = ++atual;
    try {
      const r = await fetch("/api/buscar?q=" + encodeURIComponent(termo));
      const dados = await r.json();
      if (minha !== atual) return;
      if (dados.erro) return msg(dados.erro);
      desenhar(dados);
    } catch (e) { msg("Sem conexão com o servidor. Confira se está no Wi-Fi da empresa."); }
  }
  q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(buscar, 350); });
</script>
</body>
</html>
"""


@app.route("/")
def pagina():
    return Response(PAGINA, mimetype="text/html")


def gerar_qr():
    import qrcode

    qrcode.make(URL_SITE).save("qr.png")
    print(f"qr.png gerado para {URL_SITE}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "qr":
        gerar_qr()
    else:
        print(f"Site no ar em {URL_SITE} (aceita só {REDE_PERMITIDA})")
        try:
            from waitress import serve

            serve(app, host="0.0.0.0", port=PORTA_WEB)
        except ImportError:
            app.run(host="0.0.0.0", port=PORTA_WEB)