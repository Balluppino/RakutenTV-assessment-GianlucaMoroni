# Flask Metadata Enrichment Demo

Local demo app built with Flask, a split `frontend` / `backend` structure, and LangChain.

The goal is to let a user upload a JSON or CSV file with movie or show records, enrich the metadata in one of two styles, score each generated result with an LLM judge, and download the final output in both JSON and CSV.

## What this demo does

- Runs locally on `localhost`
- Uses a web interface from `frontend/index.html`
- Loads styling from `frontend/styles.css`
- Loads client-side behavior from `frontend/app.js`
- Accepts `.json` and `.csv` uploads
- Normalizes and validates incoming content items
- Processes multiple items in a batch
- Supports two prompt modes:
  - `controlled`: simpler, more consistent, easier to operationalize
  - `explorative`: richer, more expressive, more nuanced
- Uses LangChain for:
  - prompt construction
  - model invocation
  - structured output handling
- Calls the model a second time as a judge
- Returns downloadable results in both JSON and CSV

## Expected input fields

Each content item should contain:
- `content_id`: unique identifier
- `title`: movie or show title
- `year`: release year
- `basic_description`: short description
- `existing_genres`: current genres, as a list or comma-separated string

## Generated metadata fields

For each item, the app generates:
- detailed genre tags
- mood and tone descriptors
- key themes
- target audience
- similar content suggestions
- content warnings
- viewing context recommendations
- a short enrichment rationale

It also generates a judge output with:
- score from 1 to 100

## Project structure

```text
.
|-- backend/
|   |-- app.py
|   |-- prompts.py
|   |-- .env.example
|   `-- .env
|-- frontend/
|   |-- index.html
|   |-- styles.css
|   |-- app.js
|   `-- Rakuten_TV_logo.svg.png
|-- requirements.txt
|-- .gitignore
|-- README.md
|-- content_sample.csv
|-- content_sample.json
`-- outputs/
```

## Requirements

- Python 3.10 or newer

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

5. Open `.env` in a text editor and configure the provider.

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

If both keys are present, also set:

```env
LLM_PROVIDER=openai
```

Optional local defaults:

```env
DEFAULT_MAX_ITEMS=10
FLASK_PORT=5000
```

Notes:
- Keys are loaded automatically from `.env`
- End users do not choose the provider in the UI
- If both providers are configured, `LLM_PROVIDER` decides which one is used

## Run the app

With the virtual environment active:

```powershell
python backend/app.py
```

Then open:
- [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Demo workflow

1. Open the local web page.
2. Choose a prompt mode:
   - `Controlled`
   - `Explorative`
3. Upload `content_sample.csv`, `content_sample.json`, or another file with the same schema.
4. Choose how many items to process.
5. Start the batch.
6. Review the preview cards, judge scores, and any validation issues.
7. Download:
   - JSON output
   - CSV output

## LangChain design

The app uses LangChain chat models plus structured output schemas:

- generation chain:
  - system prompt depends on mode
  - human prompt injects the normalized content item JSON
  - structured schema returns the enriched metadata fields
- judge chain:
  - receives the original content item
  - receives the generated metadata
  - returns a structured quality score

This keeps the workflow predictable enough for a client demo while still using real LLM calls.

## Frontend structure

- `frontend/index.html` contains the page structure
- `frontend/styles.css` contains the UI styling
- `frontend/app.js` contains the client-side interactions:
  - job polling
  - step walkthrough
  - result rendering

## Backend structure

- `backend/app.py` contains the Flask server and LangChain pipeline
- `backend/prompts.py` contains all generation and judge prompts
- `backend/.env` and `backend/.env.example` contain the runtime configuration

## Prompt management

All prompt text lives in `prompts.py`.

Main pieces:
- `MODE_PROMPTS["controlled"]`
- `MODE_PROMPTS["explorative"]`
- `GENERATION_USER_PROMPT`
- `JUDGE_SYSTEM_PROMPT`
- `JUDGE_USER_PROMPT`

This keeps prompt content separate from the Flask application logic.

## Batch behavior

- The app validates and normalizes the uploaded content before calling the model.
- Invalid rows are collected and reported separately.
- The app processes the first `N` valid items, where `N` is the value selected in the UI.
- The default is 10 items, which fits the sample dataset and the demo requirement.
- Results are saved under the local `outputs/` directory during runtime.

## Output format

The JSON export includes:
- batch metadata
- processing counts
- validation errors
- processing errors
- enriched results without `enrichment_rationale`

The JSON and CSV exports both exclude:
- `run_id`
- `provider`
- `model`
- `enrichment_rationale`

The CSV export includes one row per successfully processed content item, flattening list-based metadata fields into pipe-separated values.

## Provider rules

- If only `OPENAI_API_KEY` is set, the app uses OpenAI.
- If only `GOOGLE_API_KEY` is set, the app uses Google.
- If both keys are set, `LLM_PROVIDER` must also be set.
- If no supported key is set, the app returns a configuration error.

## Notes for the demo

- The app is intentionally optimized for a local prototype, not for production hardening.
- The output quality depends on the model and API key available on the demo machine.
- The sample files already contain more than 10 records, so they are ready for the requested multi-item demo.
