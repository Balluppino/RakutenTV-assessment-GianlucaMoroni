# AI-POWERED CONTENT ENRICHMENT SYSTEM

The goal is to let a user upload a JSON or CSV file, enrich the metadata in one of two styles, score each generated result with an LLM judge, and download the final output in both JSON and CSV.

## Project structure

```text
.
|-- backend/
|   |-- app.py
|   |-- prompts.py
|   `-- .env.example
|-- frontend/
|   |-- index.html
|   |-- styles.css
|   |-- app.js
|   `-- Rakuten_TV_logo.svg.png
|-- requirements.txt
|-- .gitignore
|-- README.md
|-- content_sample.csv
`-- content_sample.json
```

## Setup

1. Create a virtual environment:

```powershell
python -m venv .venv
```

2. Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Create `.env` from the example file:

```powershell
Copy-Item backend\\.env.example backend\\.env
```

5. Open `.env` in a text editor and configure the provider. Keys are loaded automatically from `.env`.

OpenAI example:

```env
OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Google example:

```env
GOOGLE_API_KEY=your_google_key_here
GOOGLE_MODEL=gemini-2.5-flash
```

6. With the virtual environment active:

```powershell
python backend/app.py
```

7. Finally, open the local web page:
[http://127.0.0.1:5000](http://127.0.0.1:5000)

## Demo workflow

1. Open the local web page.
2. Choose a prompt mode:
   - `Controlled`
   - `Explorative`
3. Upload `content_sample.csv`, `content_sample.json`, or another file with the same schema.
4. Choose how many items to process and start the batch.
6. Review the background steps.
7. Check the preview cards, judge scores, and any validation issues and download the output.

## Prompts

All the prompts live in `prompts.py`.

Main pieces:
- `MODE_PROMPTS["controlled"]`
- `MODE_PROMPTS["explorative"]`
- `GENERATION_USER_PROMPT`
- `JUDGE_SYSTEM_PROMPT`
- `JUDGE_USER_PROMPT`