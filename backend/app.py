import csv
import io
import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

try:
    from prompts import (
        METADATA_ENRICHMENT_USER_PROMPT,
        JUDGE_SYSTEM_PROMPT,
        JUDGE_USER_PROMPT,
        METADATA_ENRICHMENT_SYSTEM_PROMPT,
    )
except ModuleNotFoundError:
    from backend.prompts import (
        METADATA_ENRICHMENT_USER_PROMPT,
        JUDGE_SYSTEM_PROMPT,
        JUDGE_USER_PROMPT,
        METADATA_ENRICHMENT_SYSTEM_PROMPT,
    )

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

load_dotenv(BASE_DIR / ".env")
MAX_ITEMS_CAP = 50
PROVIDER_LABELS = {
    "openai": "OpenAI",
    "google": "Google",
}
MODE_LABELS = {
    "controlled": "Controlled",
    "explorative": "Explorative",
}
MODE_PROMPT_SECTIONS = {
    "controlled": [
        {
            "letter": "C",
            "title": "Context",
            "body": "You are working within a client-facing catalog workflow to enrich metadata for movies and TV content.",
        },
        {
            "letter": "R",
            "title": "Role",
            "body": "You are a precise metadata enrichment assistant.",
        },
        {
            "letter": "A",
            "title": "Action",
            "body": (
                "Produce metadata that is grounded in the provided input and easy to operationalize in production. Do not "
                "over-infer plot details or invent unsupported facts. Keep lists concise, practical, and taxonomy-friendly, "
                "and use clean genre and audience labels without duplicates."
            ),
        },
        {
            "letter": "F",
            "title": "Format",
            "body": "Return only content that matches the requested structured schema.",
        },
        {
            "letter": "T",
            "title": "Tone",
            "body": "Use a controlled style that is precise, consistent, and broadly reusable.",
        },
    ],
    "explorative": [
        {
            "letter": "C",
            "title": "Context",
            "body": "You are working within a client-facing catalog workflow to enrich metadata for movies and TV content.",
        },
        {
            "letter": "R",
            "title": "Role",
            "body": "You are a creative but disciplined metadata enrichment assistant.",
        },
        {
            "letter": "A",
            "title": "Action",
            "body": (
                "Produce metadata that is richer and more expressive while remaining suitable for catalog use. Expand the output "
                "with nuanced moods, themes, viewing contexts, and similar content suggestions. Stay grounded in the provided input "
                "and avoid inventing unsupported factual details."
            ),
        },
        {
            "letter": "F",
            "title": "Format",
            "body": "Return only content that matches the requested structured schema.",
        },
        {
            "letter": "T",
            "title": "Tone",
            "body": "Use an explorative style that is expressive, insightful, slightly creative, and still catalog-safe.",
        },
    ],
}
PROCESS_STEPS = [
    {
        "key": "ingestion",
        "title": "Loop over content items",
        "description": (
            "The uploaded JSON or CSV file is parsed, each row is validated and "
            "normalized into the internal schema (content_id, title, year, basic_description, existing_genres), invalid entries are collected as "
            "validation errors, and only the first selected valid items move "
            "forward in the pipeline."
        ),
    },
    {
        "key": "prompt_construction",
        "title": "Prompt construction",
        "description": (
            "Based on the selected mode (controlled, with T=0.2, or explorative, with T=0.7), provider, and model, the system assembles "
            "the prompt with which the selected model will be called. The prompt is composed of the instructions and enrichment "
            "strategy and the specific content item to process."
        ),
    },
    {
        "key": "metadata_generation",
        "title": "Generate structured metadata",
        "description": (
            "For each selected content item, the generation chain sends the item "
            "payload to the selected model and validates the returned structured "
            "metadata against the expected schema. If the call fails or the "
            "response doesn't match the schema, the item is stored as a "
            "processing error and does not move to the evaluation step."
        ),
    },
    {
        "key": "llm_judge",
        "title": "Evaluate generated metadata",
        "description": (
            "After the enriched metadata is generated, an evaluation step is performed using the same model "
            "configured with a lower temperature (T=0.1) and a specialized evaluation prompt. "
            "This step assesses the output quality and assigns a score from 1 to 100."
        ),
        "prompt_text": (
            f"PROMPT:\n{JUDGE_SYSTEM_PROMPT}\n\n"
        ),
    },
    {
        "key": "export",
        "title": "Return results in JSON and CSV",
        "description": (
            "At the end of the run, the system creates a dedicated output folder, saves successful results "
            "together with validation and processing errors, returns preview data and download URLs for the "
            "enriched metadata in both JSON and CSV formats."
        ),
    },
]

app = Flask(
    __name__,
    template_folder=str(FRONTEND_DIR),
    static_folder=str(FRONTEND_DIR),
    static_url_path="/frontend",
)
jobs_lock = Lock()
jobs: dict[str, dict] = {}


class ContentItem(BaseModel):
    content_id: str
    title: str
    year: int | None = None
    basic_description: str
    existing_genres: list[str] = Field(default_factory=list)


class GeneratedMetadata(BaseModel):
    detailed_genres: list[str] = Field(default_factory=list)
    mood_tone_descriptors: list[str] = Field(default_factory=list)
    key_themes: list[str] = Field(default_factory=list)
    target_audience: list[str] = Field(default_factory=list)
    similar_content_suggestions: list[str] = Field(default_factory=list)
    content_warnings: list[str] = Field(default_factory=list)
    viewing_context_recommendations: list[str] = Field(default_factory=list)
    enrichment_rationale: str


class JudgeEvaluation(BaseModel):
    score: int = Field(ge=1, le=100)


def read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        return int(raw_value)
    except ValueError:
        return default


DEFAULT_MAX_ITEMS = read_int_env("DEFAULT_MAX_ITEMS", 10)


def get_configured_provider() -> str:
    configured_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    has_openai_key = bool(os.getenv("OPENAI_API_KEY"))
    has_google_key = bool(os.getenv("GOOGLE_API_KEY"))

    if configured_provider:
        if configured_provider not in PROVIDER_LABELS:
            raise ValueError("LLM_PROVIDER must be either 'openai' or 'google'.")
        return configured_provider

    if has_openai_key and not has_google_key:
        return "openai"

    if has_google_key and not has_openai_key:
        return "google"

    if has_openai_key and has_google_key:
        raise ValueError(
            "Both OPENAI_API_KEY and GOOGLE_API_KEY are set. "
            "Please set LLM_PROVIDER in the .env file."
        )

    raise ValueError(
        "No API key found. Add OPENAI_API_KEY or GOOGLE_API_KEY to the .env file."
    )


def get_model_name(provider: str) -> str:
    if provider == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    return os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")


def build_chat_model(provider: str, temperature: float):
    model_name = get_model_name(provider)

    if provider == "openai":
        return ChatOpenAI(model=model_name, temperature=temperature)

    return ChatGoogleGenerativeAI(model=model_name, temperature=temperature)


def build_generation_chain(provider: str, mode: str):
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", METADATA_ENRICHMENT_SYSTEM_PROMPT[mode]),
            ("human", METADATA_ENRICHMENT_USER_PROMPT),
        ]
    )
    temperature = 0.2 if mode == "controlled" else 0.7
    model = build_chat_model(provider, temperature)
    structured_model = model.with_structured_output(
        GeneratedMetadata.model_json_schema(),
        method="json_schema",
    )
    return prompt | structured_model


def build_judge_chain(provider: str):
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", JUDGE_SYSTEM_PROMPT),
            ("human", JUDGE_USER_PROMPT),
        ]
    )
    model = build_chat_model(provider, temperature=0.1)
    structured_model = model.with_structured_output(
        JudgeEvaluation.model_json_schema(),
        method="json_schema",
    )
    return prompt | structured_model


def parse_limit(limit_value: str | None) -> int:
    if not limit_value:
        return DEFAULT_MAX_ITEMS

    try:
        limit = int(limit_value)
    except ValueError as exc:
        raise ValueError("Items to process must be a number.") from exc

    if limit < 1:
        raise ValueError("Items to process must be at least 1.")

    if limit > MAX_ITEMS_CAP:
        raise ValueError(f"Items to process cannot exceed {MAX_ITEMS_CAP}.")

    return limit


def parse_uploaded_items(uploaded_file) -> list[dict]:
    filename = (uploaded_file.filename or "").strip()
    if not filename:
        raise ValueError("Please upload a JSON or CSV file.")

    raw_bytes = uploaded_file.read()
    if not raw_bytes:
        raise ValueError("The uploaded file is empty.")

    return parse_uploaded_items_from_bytes(filename, raw_bytes)


def parse_uploaded_items_from_bytes(filename: str, raw_bytes: bytes) -> list[dict]:
    file_extension = Path(filename).suffix.lower()

    if file_extension == ".json":
        return parse_json_items(raw_bytes)

    if file_extension == ".csv":
        return parse_csv_items(raw_bytes)

    raise ValueError("Unsupported file type. Please upload a .json or .csv file.")


def parse_json_items(raw_bytes: bytes) -> list[dict]:
    try:
        payload = json.loads(raw_bytes.decode("utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError("The JSON file could not be parsed.") from exc

    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        items = payload["items"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("The JSON file must contain a list of content items.")

    if not items:
        raise ValueError("The JSON file does not contain any content items.")

    return items


def parse_csv_items(raw_bytes: bytes) -> list[dict]:
    text_buffer = io.StringIO(raw_bytes.decode("utf-8-sig"))
    reader = csv.DictReader(text_buffer)
    rows = list(reader)

    if not rows:
        raise ValueError("The CSV file does not contain any content items.")

    expected_fields = {"content_id", "title", "year", "basic_description", "existing_genres"}
    if expected_fields.issubset(set(reader.fieldnames or [])):
        repaired_rows = []
        malformed_rows_detected = False

        for row in rows:
            if (
                row.get("content_id")
                and not row.get("title")
                and not row.get("year")
                and not row.get("basic_description")
                and not row.get("existing_genres")
                and "," in row["content_id"]
            ):
                malformed_rows_detected = True
                parsed_line = next(csv.reader([row["content_id"]]))
                if len(parsed_line) != 5:
                    raise ValueError(
                        "The CSV file contains malformed rows and could not be parsed."
                    )
                repaired_rows.append(
                    {
                        "content_id": parsed_line[0],
                        "title": parsed_line[1],
                        "year": parsed_line[2],
                        "basic_description": parsed_line[3],
                        "existing_genres": parsed_line[4],
                    }
                )
            else:
                repaired_rows.append(row)

        if malformed_rows_detected:
            return repaired_rows

    return rows


def normalize_genres(raw_value) -> list[str]:
    if raw_value is None:
        return []

    if isinstance(raw_value, list):
        values = raw_value
    else:
        text_value = str(raw_value).replace(";", ",").replace("|", ",")
        values = text_value.split(",")

    genres = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned:
            genres.append(cleaned)
    return genres


def normalize_year(raw_value) -> int | None:
    if raw_value in (None, ""):
        return None

    try:
        return int(str(raw_value).strip())
    except ValueError:
        return None


def normalize_item(raw_item: dict, row_number: int) -> ContentItem:
    if not isinstance(raw_item, dict):
        raise ValueError("Each content item must be a JSON object or CSV row.")

    content_id = str(raw_item.get("content_id") or f"row-{row_number}").strip()
    title = str(raw_item.get("title") or "").strip()
    basic_description = str(raw_item.get("basic_description") or "").strip()

    if not title:
        raise ValueError("Missing required field: title.")

    if not basic_description:
        raise ValueError("Missing required field: basic_description.")

    return ContentItem(
        content_id=content_id,
        title=title,
        year=normalize_year(raw_item.get("year")),
        basic_description=basic_description,
        existing_genres=normalize_genres(raw_item.get("existing_genres")),
    )


def normalize_items(raw_items: list[dict]) -> tuple[list[ContentItem], list[dict]]:
    normalized_items: list[ContentItem] = []
    validation_errors: list[dict] = []

    for row_number, raw_item in enumerate(raw_items, start=1):
        try:
            normalized_items.append(normalize_item(raw_item, row_number))
        except ValueError as exc:
            validation_errors.append(
                {
                    "row_number": row_number,
                    "content_id": str(raw_item.get("content_id") or "").strip(),
                    "error": str(exc),
                }
            )

    return normalized_items, validation_errors


def run_enrichment_pipeline(
    items: list[ContentItem],
    provider: str,
    mode: str,
    progress_callback=None,
) -> tuple[list[dict], list[dict]]:
    if progress_callback:
        progress_callback(
            "prompt_construction",
            "Building prompt templates and structured-output chains.",
        )
    generation_chain = build_generation_chain(provider, mode)
    judge_chain = build_judge_chain(provider)
    processed_results: list[dict] = []
    processing_errors: list[dict] = []
    total_items = len(items)

    for item_index, item in enumerate(items, start=1):
        item_payload = json.dumps(item.model_dump(), indent=2, ensure_ascii=False)

        try:
            if progress_callback:
                progress_callback(
                    "metadata_generation",
                    f"Generating metadata for item {item_index} of {total_items}: {item.title}",
                )
            generated_raw = generation_chain.invoke({"item_json": item_payload})
            generated_metadata = GeneratedMetadata.model_validate(generated_raw)

            if progress_callback:
                progress_callback(
                    "llm_judge",
                    f"Evaluating output quality for item {item_index} of {total_items}: {item.title}",
                )
            judge_raw = judge_chain.invoke(
                {
                    "item_json": item_payload,
                    "mode_name": MODE_LABELS[mode],
                    "generated_metadata_json": json.dumps(
                        generated_metadata.model_dump(),
                        indent=2,
                        ensure_ascii=False,
                    ),
                }
            )
            judge_evaluation = JudgeEvaluation.model_validate(judge_raw)
        except ValidationError as exc:
            processing_errors.append(
                {
                    "content_id": item.content_id,
                    "title": item.title,
                    "error": f"Structured output validation failed: {exc.errors()}",
                }
            )
            continue
        except Exception as exc:
            processing_errors.append(
                {
                    "content_id": item.content_id,
                    "title": item.title,
                    "error": str(exc),
                }
            )
            continue

        processed_results.append(
            {
                "content_id": item.content_id,
                "title": item.title,
                "year": item.year,
                "basic_description": item.basic_description,
                "existing_genres": item.existing_genres,
                "metadata": generated_metadata.model_dump(),
                "judge": judge_evaluation.model_dump(),
            }
        )

    return processed_results, processing_errors


def create_job_state(
    *,
    job_id: str,
    source_filename: str,
    provider: str,
    model_name: str,
    mode: str,
    selected_item_count: int | None = None,
) -> dict:
    return {
        "job_id": job_id,
        "status": "queued",
        "status_message": "Upload received. Waiting to start processing.",
        "current_step_key": PROCESS_STEPS[0]["key"],
        "current_step_index": 0,
        "provider": provider,
        "provider_label": PROVIDER_LABELS[provider],
        "model": model_name,
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "source_filename": source_filename,
        "selected_item_count": selected_item_count,
        "processed_count": 0,
        "validation_error_count": 0,
        "processing_error_count": 0,
        "preview": [],
        "download_urls": {},
        "validation_errors_preview": [],
        "processing_errors_preview": [],
        "raw_item_count": 0,
        "completed_step_count": 0,
    }


def update_job(job_id: str, **changes) -> None:
    with jobs_lock:
        job = jobs[job_id]
        job.update(changes)


def build_job_payload(job: dict) -> dict:
    step_index = int(job.get("current_step_index", 0))
    current_step_key = job.get("current_step_key", PROCESS_STEPS[0]["key"])
    steps = []

    for index, step in enumerate(PROCESS_STEPS):
        if job["status"] == "completed":
            state = "completed"
        elif job["status"] == "failed":
            if step["key"] == current_step_key:
                state = "failed"
            elif index < step_index:
                state = "completed"
            else:
                state = "pending"
        elif index < step_index:
            state = "completed"
        elif step["key"] == current_step_key:
            state = "active"
        else:
            state = "pending"

        steps.append(
            {
                "key": step["key"],
                "title": step["title"],
                "description": step["description"],
                "state": state,
            }
        )

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "status_message": job["status_message"],
        "provider_label": job["provider_label"],
        "model": job["model"],
        "mode_label": job["mode_label"],
        "source_filename": job["source_filename"],
        "selected_item_count": job["selected_item_count"],
        "processed_count": job["processed_count"],
        "validation_error_count": job["validation_error_count"],
        "processing_error_count": job["processing_error_count"],
        "raw_item_count": job["raw_item_count"],
        "preview": job["preview"],
        "download_urls": job["download_urls"],
        "validation_errors_preview": job["validation_errors_preview"],
        "processing_errors_preview": job["processing_errors_preview"],
        "steps": steps,
        "current_step_index": job["current_step_index"],
        "current_step_key": job["current_step_key"],
    }


def set_job_step(job_id: str, step_key: str, status_message: str, **extra) -> None:
    step_index = next(
        index for index, step in enumerate(PROCESS_STEPS) if step["key"] == step_key
    )
    update_job(
        job_id,
        current_step_key=step_key,
        current_step_index=step_index,
        completed_step_count=step_index,
        status="running",
        status_message=status_message,
        **extra,
    )


def run_processing_job(
    job_id: str,
    source_filename: str,
    raw_bytes: bytes,
    provider: str,
    model_name: str,
    mode: str,
    max_items: int,
) -> None:
    try:
        set_job_step(
            job_id,
            "ingestion",
            "Validating the upload and normalizing content items.",
        )
        raw_items = parse_uploaded_items_from_bytes(source_filename, raw_bytes)
        normalized_items, validation_errors = normalize_items(raw_items)
        update_job(
            job_id,
            raw_item_count=len(raw_items),
            validation_error_count=len(validation_errors),
            validation_errors_preview=validation_errors[:5],
        )

        if not normalized_items:
            update_job(
                job_id,
                status="failed",
                status_message="No valid content items were found in the uploaded file.",
                processing_errors_preview=[],
            )
            return

        items_to_process = normalized_items[:max_items]
        update_job(job_id, selected_item_count=len(items_to_process))

        results, processing_errors = run_enrichment_pipeline(
            items_to_process,
            provider,
            mode,
            progress_callback=lambda step_key, message: set_job_step(
                job_id,
                step_key,
                message,
            ),
        )
        update_job(
            job_id,
            processed_count=len(results),
            processing_error_count=len(processing_errors),
            processing_errors_preview=processing_errors[:5],
        )

        if not results:
            update_job(
                job_id,
                status="failed",
                status_message="The pipeline did not produce any successful results.",
            )
            return

        set_job_step(
            job_id,
            "export",
            "Persisting outputs and preparing downloadable JSON and CSV files.",
        )
        response_payload = persist_results(
            source_filename=source_filename,
            provider=provider,
            model_name=model_name,
            mode=mode,
            raw_item_count=len(raw_items),
            selected_item_count=len(items_to_process),
            validation_errors=validation_errors,
            processing_errors=processing_errors,
            results=results,
        )
        final_payload = {**response_payload, "preview": response_payload["preview"][:3]}
        update_job(
            job_id,
            **final_payload,
            status="completed",
            status_message=(
                f"Completed. {response_payload['processed_count']} items processed "
                f"with {response_payload['provider_label']}."
            ),
            current_step_key="export",
            current_step_index=len(PROCESS_STEPS) - 1,
            completed_step_count=len(PROCESS_STEPS),
        )
    except ValueError as exc:
        update_job(
            job_id,
            status="failed",
            status_message=str(exc),
        )
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            status_message=f"Unexpected processing error: {exc}",
        )


def join_list(values: list[str]) -> str:
    return " | ".join(values)


def build_enriched_metadata(metadata: dict) -> dict:
    return {
        "detailed_genres": metadata["detailed_genres"],
        "mood": metadata["mood_tone_descriptors"],
        "themes": metadata["key_themes"],
        "target_audience": metadata["target_audience"],
        "similar_content_suggestions": metadata["similar_content_suggestions"],
        "content_warnings": metadata["content_warnings"],
        "viewing_context": metadata["viewing_context_recommendations"],
    }


def build_export_results(results: list[dict]) -> list[dict]:
    export_results = []

    for result in results:
        export_results.append(
            {
                "content_id": result["content_id"],
                "title": result["title"],
                "year": result["year"],
                "basic_description": result["basic_description"],
                "existing_genres": result["existing_genres"],
                "enriched_metadata": build_enriched_metadata(result["metadata"]),
                "score": result["judge"]["score"],
                "prompt_mode": result.get("prompt_mode", ""),
                "error_type": "",
            }
        )

    return export_results


def build_export_error_entries(
    entries: list[dict],
    prompt_mode: str,
    error_type: str,
) -> list[dict]:
    export_entries = []

    for entry in entries:
        export_entries.append(
            {
                "content_id": entry.get("content_id", ""),
                "title": entry.get("title", ""),
                "year": "",
                "basic_description": "",
                "existing_genres": "",
                "enriched_metadata": {
                    "detailed_genres": [],
                    "mood": [],
                    "themes": [],
                    "target_audience": [],
                    "similar_content_suggestions": [],
                    "content_warnings": [],
                    "viewing_context": [],
                },
                "score": "",
                "prompt_mode": prompt_mode,
                "error_type": error_type,
            }
        )

    return export_entries


def write_csv_results(
    csv_path: Path,
    rows: list[dict],
) -> None:
    fieldnames = [
        "content_id",
        "title",
        "year",
        "basic_description",
        "existing_genres",
        "ENRICHED_detailed_genres",
        "ENRICHED_mood",
        "ENRICHED_themes",
        "ENRICHED_target_audience",
        "ENRICHED_similar_content_suggestions",
        "ENRICHED_content_warnings",
        "ENRICHED_viewing_context",
        "score",
        "prompt_mode",
        "error_type",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            metadata = row["enriched_metadata"]
            writer.writerow(
                {
                    "content_id": row["content_id"],
                    "title": row["title"],
                    "year": row["year"] or "",
                    "basic_description": row["basic_description"],
                    "existing_genres": (
                        join_list(row["existing_genres"])
                        if isinstance(row["existing_genres"], list)
                        else row["existing_genres"]
                    ),
                    "ENRICHED_detailed_genres": join_list(metadata["detailed_genres"]),
                    "ENRICHED_mood": join_list(metadata["mood"]),
                    "ENRICHED_themes": join_list(metadata["themes"]),
                    "ENRICHED_target_audience": join_list(metadata["target_audience"]),
                    "ENRICHED_similar_content_suggestions": join_list(
                        metadata["similar_content_suggestions"]
                    ),
                    "ENRICHED_content_warnings": join_list(
                        metadata["content_warnings"]
                    ),
                    "ENRICHED_viewing_context": join_list(
                        metadata["viewing_context"]
                    ),
                    "score": row["score"],
                    "prompt_mode": row["prompt_mode"],
                    "error_type": row["error_type"],
                }
            )


def persist_results(
    source_filename: str,
    provider: str,
    model_name: str,
    mode: str,
    raw_item_count: int,
    selected_item_count: int,
    validation_errors: list[dict],
    processing_errors: list[dict],
    results: list[dict],
) -> dict:
    OUTPUT_DIR.mkdir(exist_ok=True)
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_filename": source_filename,
        "provider_label": PROVIDER_LABELS[provider],
        "raw_item_count": raw_item_count,
        "selected_item_count": selected_item_count,
        "processed_count": len(results),
        "validation_error_count": len(validation_errors),
        "processing_error_count": len(processing_errors),
    }

    export_results = build_export_results(
        [{**result, "prompt_mode": mode} for result in results]
    )
    export_validation_errors = build_export_error_entries(
        validation_errors,
        prompt_mode=mode,
        error_type="validation",
    )
    export_processing_errors = build_export_error_entries(
        processing_errors,
        prompt_mode=mode,
        error_type="processing",
    )
    csv_rows = export_results + export_validation_errors + export_processing_errors

    json_payload = {
        **summary,
        "validation_errors": export_validation_errors,
        "processing_errors": export_processing_errors,
        "results": export_results,
    }

    json_path = run_dir / "metadata_results.json"
    csv_path = run_dir / "metadata_results.csv"
    json_path.write_text(
        json.dumps(json_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_csv_results(csv_path, csv_rows)

    return {
        **summary,
        "download_urls": {
            "json": f"/downloads/{run_id}/{json_path.name}",
            "csv": f"/downloads/{run_id}/{csv_path.name}",
        },
        "preview": export_results[:5],
        "validation_errors_preview": validation_errors[:5],
        "processing_errors_preview": processing_errors[:5],
    }


@app.get("/")
def index():
    try:
        provider = get_configured_provider()
        provider_name = PROVIDER_LABELS[provider]
        model_name = get_model_name(provider)
        config_error = None
    except ValueError as exc:
        provider_name = "Not configured"
        model_name = "-"
        config_error = str(exc)

    return render_template(
        "index.html",
        mode_labels=MODE_LABELS,
        mode_prompts=METADATA_ENRICHMENT_SYSTEM_PROMPT,
        mode_prompt_sections=MODE_PROMPT_SECTIONS,
        process_steps=PROCESS_STEPS,
        provider_name=provider_name,
        model_name=model_name,
        default_max_items=DEFAULT_MAX_ITEMS,
        config_error=config_error,
    )


@app.post("/api/process")
def process_content():
    uploaded_file = request.files.get("content_file")
    mode = (request.form.get("mode") or "").strip().lower()
    limit_value = (request.form.get("max_items") or "").strip()

    if mode not in MODE_LABELS:
        return jsonify({"error": "Invalid enrichment mode."}), 400

    if uploaded_file is None:
        return jsonify({"error": "Please upload a JSON or CSV file."}), 400

    try:
        provider = get_configured_provider()
        model_name = get_model_name(provider)
        max_items = parse_limit(limit_value)
        source_filename = (uploaded_file.filename or "").strip()
        raw_bytes = uploaded_file.read()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not source_filename:
        return jsonify({"error": "Please upload a JSON or CSV file."}), 400

    if not raw_bytes:
        return jsonify({"error": "The uploaded file is empty."}), 400

    job_id = f"job_{uuid4().hex[:10]}"
    job_state = create_job_state(
        job_id=job_id,
        source_filename=source_filename,
        provider=provider,
        model_name=model_name,
        mode=mode,
        selected_item_count=max_items,
    )
    with jobs_lock:
        jobs[job_id] = job_state

    worker = Thread(
        target=run_processing_job,
        args=(job_id, source_filename, raw_bytes, provider, model_name, mode, max_items),
        daemon=True,
    )
    worker.start()

    return jsonify(build_job_payload(job_state)), 202


@app.get("/api/jobs/<job_id>")
def get_job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if job is None:
        return jsonify({"error": "Job not found."}), 404

    return jsonify(build_job_payload(job))


@app.get("/downloads/<run_id>/<filename>")
def download_result(run_id: str, filename: str):
    run_directory = OUTPUT_DIR / run_id
    return send_from_directory(run_directory, filename, as_attachment=True)

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(debug=True, port=port)
