# 🧪 化学品インテリジェンス (chem-intel)

新規化学品の **特徴・規制・貿易・市場** を自動で網羅調査し、商社営業がそのまま
顧客提案に使える「分厚いレポート」をアプリ上に表示・PDF出力するツール。
クラウド完結（Streamlit Community Cloud）で、ブラウザからどこでも利用できます。

## 何ができるか
- 🔍 **検索**：化学品名 / CAS番号 / HSコード で調査開始
- 🧬 **同定**：PubChem で CAS・分子式・別名・構造を自動解決
- 📚 **ディープリサーチ**（Claude + ウェブ検索、出典付き）
  - 概要・性状・用途 / 世界市場・需給 / 主要メーカー・ユーザー / 価格・トレンド・商機
- 🌐 **世界貿易**：UN Comtrade API で国別 輸出入額・単価を自動集計（TradeMap代替）
- ⚖️ **規制**：NITE CHRIP（化審法・安衛法・毒劇法・消防法・PRTR）/ REACH・TSCA・各国
- 🛃 **輸出入・関税**：財務省 貿易統計・実行関税率・外為法
- 🚚 **物流規制**：UN番号・IMDG・IATA・容器・保管
- 📄 **PDF出力**：ワンクリック（日本語対応）
- 🗂 **履歴**：全調査を保存、名前/CAS/HSで再検索・再表示

## セットアップ（ローカル）
```bash
cd ~/chem_intel
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # ANTHROPIC_API_KEY を記入
set -a; . ./.env; set +a

streamlit run app.py        # ブラウザで http://localhost:8501
```
CLIでも生成可能：
```bash
python cli.py "アクリロニトリル" --pdf out.pdf
```

> macOSでPDF（WeasyPrint）を使う場合は事前に `brew install pango gdk-pixbuf libffi` が必要。
> 未導入でもアプリは動作し、PDF不可時はMarkdownダウンロードに切替わります。

## クラウド完結デプロイ（Streamlit Community Cloud）
1. GitHubに本フォルダをpush（Privateリポジトリ可）
   ```bash
   git init && git add . && git commit -m "init chem-intel"
   gh repo create chem-intel --private --source=. --push
   ```
2. https://share.streamlit.io にGitHubでログイン →「New app」
3. リポジトリ / ブランチ / `app.py` を選択してデプロイ
   - `packages.txt`（WeasyPrint依存・日本語フォント）は自動で導入されます
4. **App settings > Secrets** に `.streamlit/secrets.toml.example` の内容を貼り付け、
   `ANTHROPIC_API_KEY` を設定（`COMTRADE_KEY`・`DATABASE_URL` は任意）
5. 完了。発行されたURLにブラウザからアクセス（PC不要）

### 履歴をクラウドで永続化したい場合（推奨）
Streamlit Cloudのディスクは再起動で消えるため、履歴を残すには外部Postgresを使います。
1. https://supabase.com で無料プロジェクト作成
2. 接続文字列（`postgresql://...`）を Secrets の `DATABASE_URL` に設定
   - 未設定でもアプリは動きます（その場合は一時SQLite＝再起動で履歴消去）

### UN Comtrade のキー（推奨）
1. https://comtradedeveloper.un.org でサインアップ → 無料の subscription key を取得
2. Secrets の `COMTRADE_KEY` に設定（未設定でもpreviewで動作、レート制限あり）

## データ源について（正確性のための注記）
- TradeMap はログイン必須・規約上の自動取得制限があるため、同じ国連データを使う
  **UN Comtrade API** を採用しています（アプリ内にTradeMapへのリンクも掲載）。
- NITE CHRIP は公開APIが無いため、直リンク提示＋AIによる一次情報の要約で対応します。
- 本レポートは参考資料です。最終判断は一次情報（CHRIP・財務省・ECHA・SDS）で確認を。

## 構成
```
app.py              Streamlit UI（検索・表示・PDF・履歴）
cli.py              コマンドライン生成（バッチ/自動化用）
chem_intel/
  config.py         設定（環境変数 / secrets）
  llm.py            Claude + ウェブ検索ヘルパー
  identity.py       PubChem 同定
  deep_research.py  市場ディープリサーチ
  nite.py           NITE CHRIP・日本規制
  customs_jp.py     財務省 貿易統計・関税
  comtrade.py       UN Comtrade 世界貿易
  regulations.py    海外規制・物流規制
  report.py         オーケストレーション・結合
  pdf_export.py     Markdown→PDF
  storage.py        履歴 DB（SQLite/Postgres）
requirements.txt    Python依存
packages.txt        Streamlit Cloud用 apt依存（WeasyPrint・日本語フォント）
```
