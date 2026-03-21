# AI-POWERED CONTENT ENRICHMENT SYSTEM

## The Challenge

Rakuten TV has thousands of movies and TV shows in its catalog. Currently, the metadata (descriptions, tags, mood, themes) is inconsistent and often incomplete. This affects content discovery and recommendation quality.

**Your task**: Build a prototype system that uses AI to automatically enrich content metadata.

**My approach**: I developed a solution that enables users to upload a JSON or CSV file, enrich metadata in one of two styles (controlled or explorative), evaluate each generated result using an LLM-based judge, and download the enriched output in both JSON and CSV formats. The system is implemented with a lightweight HTML/JavaScript frontend and a Python Flask backend, with API keys securely managed through environment variables.

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
|-- content_sample.json
|-- content_sample_w_errors.csv
`-- content_sample_w_errors.json
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

6. With the virtual environment active:

```powershell
python backend/app.py
```

7. When is loaded, open the generated local web page:
[http://127.0.0.1:5000](http://127.0.0.1:5000)

## Demo workflow

1. Open the local web page.
2. Upload a document and select how many items to process.
3. Choose a prompt mode:
   - `Controlled`
   - `Explorative`
4. Start the batch process by clicking the button.
5. Discover what are the background steps.
6. Review the preview cards and download the output files.

## Technology rationale

- **HTML/CSS/JavaScript**: frontend for file upload, polling, progress tracking, and result rendering.
- **Flask**: lightweight backend with simple routing, file handling, background job execution, and download support.
- **LangChain**: framework for composing prompts and building provider-agnostic structured chains, reducing boilerplate and standardizing integration with OpenAI and Google models.
- **Pydantic**: data validation library used to enforce schemas for metadata and evaluation scores, ensuring reliable and debuggable outputs.
- **`.env` configuration**: keeps secrets out of the codebase and allows easy configuration of providers, models, and ports.

## Prompts

All the prompts live in `prompts.py`.

Main elements:
- `METADATA_ENRICHMENT_SYSTEM_PROMPT["controlled"]`
- `METADATA_ENRICHMENT_SYSTEM_PROMPT["explorative"]`
- `METADATA_ENRICHMENT_USER_PROMPT`
- `JUDGE_SYSTEM_PROMPT`
- `JUDGE_USER_PROMPT`

## Error handling

The app handles errors in layers, so invalid data does not automatically break the whole run. To test it, upload `content_sample_w_errors.csv` or `content_sample_w_errors.json`. 

- Frontend validation: only `.json` and `.csv` files are accepted in the upload field. 
- Record-level validation errors: each uploaded row/item is normalized into the internal schema. If `title` or `basic_description` is missing, that record is skipped and stored in `validation_errors`. Invalid `year` values do not fail the record and missing `existing_genres` values are treated as empty.
- Processing errors: if the LLM call fails, that item is stored in `processing_errors` and the pipeline continues with the remaining items.
- UI behavior & output: the system provides real-time feedback through the frontend and the errors are reported in the field `error_type` which displays `validation` for input issues, `processing` for enrichment failures, and empty for successful cases.
