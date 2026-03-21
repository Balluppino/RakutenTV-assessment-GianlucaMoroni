const state = {
  slideIndex: 0,
  jobId: null,
  pollHandle: null,
  latestJob: null,
  walkthroughCompleted: false,
};

const dom = {
  form: document.getElementById("demoForm"),
  contentFile: document.getElementById("content_file"),
  fileError: document.getElementById("fileError"),
  processButton: document.getElementById("processButton"),
  processingSection: document.getElementById("processingSection"),
  progressBar: document.getElementById("progressBar"),
  progressText: document.getElementById("progressText"),
  stepList: document.getElementById("stepList"),
  slideKicker: document.getElementById("slideKicker"),
  slideTitle: document.getElementById("slideTitle"),
  slideDescription: document.getElementById("slideDescription"),
  slidePromptBlock: document.getElementById("slidePromptBlock"),
  slidePromptText: document.getElementById("slidePromptText"),
  backStepButton: document.getElementById("backStepButton"),
  nextStepButton: document.getElementById("nextStepButton"),
  resultsReveal: document.getElementById("resultsReveal"),
  downloadActions: document.getElementById("downloadActions"),
  resultsPanel: document.getElementById("resultsPanel"),
};

const processSteps = JSON.parse(
  document.getElementById("processStepsData").textContent
);
const allowedFileExtensions = new Set(["json", "csv"]);

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function chips(values, extraClass = "") {
  if (!values || values.length === 0) {
    return '<span class="chip">None</span>';
  }

  return values
    .map((value) => `<span class="chip ${extraClass}">${escapeHtml(value)}</span>`)
    .join("");
}

function renderField(label, content, extraClass = "") {
  return [
    `<div class="preview-field ${extraClass}">`,
    `<strong>${escapeHtml(label)}</strong>`,
    `<div>${content}</div>`,
    "</div>",
  ].join("");
}

function showFileError(message) {
  dom.fileError.textContent = message;
  dom.fileError.classList.remove("hidden");
}

function clearFileError() {
  dom.fileError.textContent = "";
  dom.fileError.classList.add("hidden");
}

function getFileExtension(filename) {
  const parts = filename.split(".");
  if (parts.length < 2) {
    return "";
  }

  return parts.at(-1).toLowerCase();
}

function validateSelectedFile() {
  const file = dom.contentFile.files?.[0];

  if (!file) {
    clearFileError();
    return true;
  }

  const extension = getFileExtension(file.name);
  if (allowedFileExtensions.has(extension)) {
    clearFileError();
    return true;
  }

  dom.contentFile.value = "";
  showFileError("Only JSON or CSV files are allowed.");
  return false;
}

function errorLabel(entry) {
  if (entry.title) {
    return entry.title;
  }
  if (entry.content_id) {
    return entry.content_id;
  }
  return `Row ${entry.row_number || "?"}`;
}

function renderErrors(title, items) {
  if (!items || items.length === 0) {
    return "";
  }

  const listItems = items
    .map(
      (entry) =>
        `<li><strong>${escapeHtml(errorLabel(entry))}</strong>: ${escapeHtml(entry.error)}</li>`
    )
    .join("");

  return [
    '<div class="errors">',
    `<h3>${escapeHtml(title)}</h3>`,
    `<ul>${listItems}</ul>`,
    "</div>",
  ].join("");
}

function renderCards(items) {
  if (!items || items.length === 0) {
    return '<div class="placeholder">The run is still finishing. Preview cards will appear here as soon as successful outputs are ready.</div>';
  }

  const cards = items
    .slice(0, 3)
    .map((item) => {
      return [
        '<article class="preview">',
        `<h3>${escapeHtml(item.title)}</h3>`,
        '<div class="chips">',
        `<span class="chip mono">${escapeHtml(item.content_id)}</span>`,
        `<span class="chip">${escapeHtml(item.year || "Year n/a")}</span>`,
        `<span class="chip score">Score ${escapeHtml(item.score)}</span>`,
        "</div>",
        '<div class="preview-grid">',
        renderField("existing_genres", chips(item.existing_genres || [])),
        renderField(
          "ENRICHED_detailed_genres",
          chips(item.enriched_metadata?.detailed_genres || [], "score"),
          "preview-field-enriched"
        ),
        renderField(
          "ENRICHED_similar_content_suggestions",
          chips(item.enriched_metadata?.similar_content_suggestions || [], "score"),
          "preview-field-enriched"
        ),
        renderField(
          "ENRICHED_themes",
          chips(item.enriched_metadata?.themes || [], "score"),
          "preview-field-enriched"
        ),
        "</div>",
        "</article>",
      ].join("");
    })
    .join("");

  return `<div class="results">${cards}</div>`;
}

function updateSlide() {
  const step = processSteps[state.slideIndex];
  dom.slideKicker.textContent = `Step ${state.slideIndex + 1}`;
  dom.slideTitle.textContent = step.title;
  dom.slideDescription.textContent = step.description;
  if (step.prompt_text) {
    dom.slidePromptText.textContent = step.prompt_text;
    dom.slidePromptBlock.classList.remove("hidden");
  } else {
    dom.slidePromptText.textContent = "";
    dom.slidePromptBlock.classList.add("hidden");
  }
  dom.backStepButton.disabled = state.slideIndex === 0;

  if (state.slideIndex >= processSteps.length - 1) {
    dom.resultsReveal.classList.remove("hidden");
    dom.nextStepButton.textContent = "Done";
    dom.nextStepButton.disabled = state.walkthroughCompleted;
    dom.nextStepButton.style.visibility = "visible";
  } else {
    state.walkthroughCompleted = false;
    dom.nextStepButton.textContent = "Next";
    dom.nextStepButton.disabled = false;
    dom.nextStepButton.style.visibility = "visible";
    dom.resultsReveal.classList.add("hidden");
  }

  renderStepList();

  if (state.latestJob) {
    renderResults(state.latestJob);
  }
}

function renderStepList() {
  dom.stepList.innerHTML = processSteps
    .map(
      (step, index) => [
        `<div class="step ${getStepVisualState(index)}">`,
        `<span class="kicker">Step ${index + 1}</span>`,
        `<h3>${escapeHtml(step.title)}</h3>`,
        "</div>",
      ].join("")
    )
    .join("");
}

function getStepVisualState(index) {
  if (state.walkthroughCompleted && index === processSteps.length - 1) {
    return "completed";
  }

  if (index < state.slideIndex) {
    return "completed";
  }

  if (index === state.slideIndex) {
    return "active";
  }

  return "pending";
}

function renderDownloads(job) {
  if (!job.download_urls?.json) {
    dom.downloadActions.innerHTML = "";
    return;
  }

  dom.downloadActions.innerHTML = [
    `<a class="dl" href="${job.download_urls.json}">Download JSON</a>`,
    `<a class="dl" href="${job.download_urls.csv}">Download CSV</a>`,
  ].join("");
}

function renderResults(job) {
  if (state.slideIndex < processSteps.length - 1) {
    return;
  }

  renderDownloads(job);

  if (job.status === "completed") {
    dom.resultsPanel.innerHTML = [
      renderCards(job.preview),
      renderErrors("Validation issues", job.validation_errors_preview),
      renderErrors("Processing issues", job.processing_errors_preview),
    ].join("");
    return;
  }

  if (job.status === "failed") {
    dom.resultsPanel.innerHTML = [
      `<div class="alert">${escapeHtml(job.status_message)}</div>`,
      renderErrors("Validation issues", job.validation_errors_preview),
      renderErrors("Processing issues", job.processing_errors_preview),
    ].join("");
    return;
  }

  dom.resultsPanel.innerHTML =
    '<div class="placeholder">Metadata enrichment is still in progress...</div>';
}

function renderJob(job) {
  state.latestJob = job;

  const progress = Math.max(0, Math.min(100, Number(job.progress_percent || 0)));
  dom.progressBar.style.width = `${progress}%`;
  if (dom.progressText) {
    dom.progressText.textContent = `${Math.round(progress)}%`;
  }

  renderResults(job);
}

async function pollJob() {
  if (!state.jobId) {
    return;
  }

  try {
    const response = await fetch(`/api/jobs/${state.jobId}`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Unable to read job status.");
    }

    renderJob(data);

    if (data.status === "completed" || data.status === "failed") {
      clearInterval(state.pollHandle);
      state.pollHandle = null;
      dom.processButton.disabled = false;
    }
  } catch (error) {
    clearInterval(state.pollHandle);
    state.pollHandle = null;
    dom.processButton.disabled = false;
  }
}

dom.nextStepButton.addEventListener("click", () => {
  if (state.slideIndex < processSteps.length - 1) {
    state.slideIndex += 1;
  } else {
    state.walkthroughCompleted = true;
  }
  updateSlide();
});

dom.backStepButton.addEventListener("click", () => {
  if (state.slideIndex > 0) {
    state.slideIndex -= 1;
    updateSlide();
  }
});

dom.contentFile.addEventListener("change", () => {
  validateSelectedFile();
});

dom.form.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!validateSelectedFile()) {
    return;
  }

  state.slideIndex = 0;
  state.latestJob = null;
  state.walkthroughCompleted = false;
  updateSlide();

  dom.processingSection.classList.remove("hidden");
  dom.processingSection.scrollIntoView({ behavior: "smooth", block: "start" });
  dom.processButton.disabled = true;
  dom.progressBar.style.width = "4%";
  if (dom.progressText) {
    dom.progressText.textContent = "4%";
  }
  dom.downloadActions.innerHTML = "";
  dom.resultsPanel.innerHTML =
    '<div class="placeholder">Run started. Use Next to walk through the pipeline while the backend processes in the background.</div>';

  const formData = new FormData(dom.form);

  try {
    const response = await fetch("/api/process", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Unable to start processing.");
    }

    state.jobId = data.job_id;
    renderJob(data);

    if (state.pollHandle) {
      clearInterval(state.pollHandle);
    }

    state.pollHandle = setInterval(pollJob, 1500);
    pollJob();
  } catch (error) {
    dom.processButton.disabled = false;
    dom.resultsPanel.innerHTML = `<div class="alert">${escapeHtml(error.message)}</div>`;
  }
});

updateSlide();
