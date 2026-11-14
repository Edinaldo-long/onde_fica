# 📍 Onde Fica? — Consulta de Matéria-Prima por Dispositivo Móvel

> Uma solução web leve, rápida e segura desenvolvida em **Python (Flask)** para consulta de localização, lotes, saldos e validades de matérias-primas diretamente pelo celular na rede local da farmácia.

---

## 🚀 Sobre o Projeto

Em ambientes farmacêuticos e de manipulação, otimizar o tempo de localização de insumos e garantir o rigor no controle de prazos de validade e lotes é essencial. O **"Onde Fica?"** foi criado para preencher essa lacuna: um aplicativo web responsivo, de **somente leitura**, acessível via QR Code por qualquer smartphone conectado à rede Wi-Fi interna da empresa.

O sistema faz consultas diretas e otimizadas em um banco de dados **Firebird**, filtrando rigorosamente apenas os locais de estoque autorizados e garantindo que o operador visualize o status de validade em tempo real.

---

## ✨ Principais Funcionalidades

* **Busca Instantânea por Nome ou Código:** Conforme o usuário digita (a partir de 2 caracteres), a interface busca dinamicamente no banco de dados.
* **Filtro Estrito por Locais Permitidos:** Restringe os resultados estritamente aos locais de estoque cadastrados no escopo operacional (como armários, cubos, geladeiras termolábeis e bancadas de laboratório).
* **Alertas Inteligentes de Validade:** 
  * 🔴 **Vencido:** Alerta em destaque com o tempo de vencimento.
  * 🟠 **Atenção:** Destaca lotes próximos ao vencimento (configurável para N dias).
  * 🟢 **OK / Sem Data:** Itens dentro da normalidade.
* **Indicadores Operacionais:** Identificação visual imediata de lotes marcados como "em uso" e conversão/normalização automática de unidades de medida (Quilos, Gramas, Litros, Mililitros, Unidades, UI).
* **Geração de QR Code Integrada:** Comando interno via script para gerar rapidamente um arquivo `qr.png` apontando para o endereço IP do servidor na rede local.

---

## 🔒 Segurança e Boas Práticas

* **Isolamento de Rede:** O middleware de segurança valida cada requisição, bloqueando acessos externos e permitindo conexões exclusivamente oriundas da sub-rede local configurada (`REDE_PERMITIDA`) ou de loopback (`localhost`).
* **Segurança de Banco de Dados:** Operação restrita a comandos de leitura (`SELECT`). Recomenda-se o uso de uma credencial de banco com privilégios limitados.
* **Ambiente Isento de Bloqueios de Concorrência:** Otimizado com o servidor WSGI **Waitress** para alta estabilidade em ambiente de produção local.

---

## 🛠️ Tecnologias Utilizadas

* **Backend:** Python, Flask, FirebirdSQL (`firebirdsql`), Waitress
* **Utilitários:** QRCode (`qrcode[pil]`), IPAddress, Unidecode
* **Frontend:** HTML5, CSS3 Nativo (com suporte a *Dark/Light mode* automático via `color-scheme`), JavaScript Puro (Vanilla JS com *debounce* de busca para otimizar requisições)

---

## ⚙️ Como Instalar e Executar

### 1. Pré-requisitos
Certifique-se de ter o **Python** instalado em sua máquina e acesso ao banco de dados Firebird da sua estrutura.

### 2. Instalação das Dependências
Abra o terminal na pasta do projeto e execute:
```bash
pip install flask firebirdsql waitress "qrcode[pil]"
