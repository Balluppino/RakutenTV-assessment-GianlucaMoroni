MODE_PROMPTS = {
    "controlled": (
        "You are enriching movie and TV metadata for a client-facing catalog workflow. "
        "Work in a controlled style: consistent, simple, grounded, and easy to operationalize. "
        "Do not over-infer plot details that are not supported by the provided input. "
        "Keep lists concise, practical, and taxonomy-friendly. "
        "Use clean genre and audience labels, avoid duplicates, and prefer safe, broadly reusable wording."
    ),
    "explorative": (
        "You are enriching movie and TV metadata for a client-facing catalog workflow. "
        "Work in an explorative style: richer, more expressive, and slightly more creative while still grounded in the provided input. "
        "Expand the metadata with nuanced moods, themes, viewing contexts, and similar content suggestions. "
        "Do not invent factual plot elements that are not supported, but do surface interesting angles and richer descriptors."
    ),
}

MODE_LABELS = {
    "controlled": "Controlled",
    "explorative": "Explorative",
}

GENERATION_USER_PROMPT = """Enrich the metadata for the following content item.

Return a structured response that matches the requested schema exactly.
If a field is not applicable, return an empty list instead of making up unsupported facts.

Content item JSON:
{item_json}
"""

JUDGE_SYSTEM_PROMPT = (
    "You are an LLM quality judge for metadata enrichment. "
    "Score each result from 1 to 100. "
    "Evaluate: relevance to the source item, completeness, consistency, usefulness for catalog tagging, and alignment with the requested style. "
    "Be strict but fair. Return only the numeric score in the requested schema."
)

JUDGE_USER_PROMPT = """Review the generated metadata for the following content item.

Requested style:
{mode_name}

Original content item JSON:
{item_json}

Generated metadata JSON:
{generated_metadata_json}
"""
