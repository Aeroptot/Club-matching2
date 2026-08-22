const MAX_TAGS = 10;
const NONE_ID = "__none__";
const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"];
const PERIODS = ["period11", "period12", "lunchtime"];
const PERIOD_LABELS = { period11: "P11", period12: "P12", lunchtime: "Lunch" };

let staticMode = false;

const state = {
  selectedTags: new Set(),
  tagWeightMults: {},
  blockedSlots: new Set(),
  quizSession: null,
  quizPendingSelections: new Set(),
  quizHistory: [],
};

const els = {
  selectedTags: document.getElementById("selected-tags"),
  quizTagWarning: document.getElementById("quiz-tag-warning"),
  slotGrid: document.getElementById("slot-grid"),
  quizPanel: document.getElementById("quiz-panel"),
  quizQuestion: document.getElementById("quiz-question"),
  quizHint: document.getElementById("quiz-hint"),
  quizOptions: document.getElementById("quiz-options"),
  quizContinue: document.getElementById("quiz-continue"),
  quizBack: document.getElementById("quiz-back"),
  quizRestart: document.getElementById("quiz-restart"),
  resultsSection: document.getElementById("results-section"),
  resultsSummary: document.getElementById("results-summary"),
  results: document.getElementById("results"),
  error: document.getElementById("error"),
};

function showError(message) {
  els.error.textContent = message;
  els.error.classList.remove("hidden");
}

function clearError() {
  els.error.textContent = "";
  els.error.classList.add("hidden");
}

function formatMeeting(day, period) {
  const days = {
    monday: "Mon",
    tuesday: "Tue",
    wednesday: "Wed",
    thursday: "Thu",
    friday: "Fri",
  };
  const periods = {
    period11: "Period 11",
    period12: "Period 12",
    lunchtime: "Lunch",
    period13: "Period 13",
  };
  return `${days[day] || day} · ${periods[period] || period}`;
}

function updateTagLimitWarnings() {
  const atLimit = state.selectedTags.size >= MAX_TAGS;
  els.quizTagWarning?.classList.toggle("hidden", !atLimit);
}

function updateSelectedDisplay() {
  const tags = [...state.selectedTags];
  const text = tags.length ? tags.join(", ") : "none";
  els.selectedTags.textContent = text;
  updateTagLimitWarnings();
}

function clearTags() {
  state.selectedTags.clear();
  state.tagWeightMults = {};
  updateSelectedDisplay();
  clearError();
}

function addQuizTags(tags) {
  let addedAny = false;
  for (const item of tags) {
    const tag = typeof item === "string" ? item : item.tag;
    const mult = typeof item === "string" ? 1 : item.weight_mult ?? 1;
    if (state.selectedTags.size >= MAX_TAGS && !state.selectedTags.has(tag)) break;
    if (!state.selectedTags.has(tag)) {
      state.selectedTags.add(tag);
      addedAny = true;
    }
    const existing = state.tagWeightMults[tag] ?? 1;
    state.tagWeightMults[tag] = Math.max(existing, mult);
  }
  updateSelectedDisplay();
  if (tags.length && !addedAny && state.selectedTags.size >= MAX_TAGS) {
    showError(`Maximum ${MAX_TAGS} tags reached. Clear tags to add more.`);
  } else {
    clearError();
  }
}

function loadSlots() {
  if (!els.slotGrid) return;

  els.slotGrid.innerHTML = "";

  const header = document.createElement("div");
  header.className = "slot-row slot-header";
  header.innerHTML = "<span></span>";
  PERIODS.forEach((period) => {
    const label = document.createElement("span");
    label.textContent = PERIOD_LABELS[period] || period;
    header.appendChild(label);
  });
  els.slotGrid.appendChild(header);

  WEEKDAYS.forEach((day) => {
    const row = document.createElement("div");
    row.className = "slot-row";
    const dayLabel = document.createElement("span");
    dayLabel.className = "slot-day";
    dayLabel.textContent = day.charAt(0).toUpperCase() + day.slice(1, 3);
    row.appendChild(dayLabel);

    PERIODS.forEach((period) => {
      const id = `${day}:${period}`;
      const label = document.createElement("label");
      label.className = "slot-cell";
      label.title = `${dayLabel.textContent} · ${PERIOD_LABELS[period]}`;
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = id;
      input.addEventListener("change", () => {
        if (input.checked) state.blockedSlots.add(id);
        else state.blockedSlots.delete(id);
      });
      label.appendChild(input);
      row.appendChild(label);
    });
    els.slotGrid.appendChild(row);
  });
}

async function postQuiz(body) {
  if (staticMode) {
    try {
      return ClubMatcher.handleQuiz(body);
    } catch (err) {
      showError(err.message || "Quiz failed.");
      return null;
    }
  }
  const res = await fetch("/api/quiz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    showError(data.error || "Quiz failed.");
    return null;
  }
  return data;
}

function bindQuizCheckbox(input, opt) {
  input.addEventListener("change", () => {
    const noneInput = els.quizOptions.querySelector(`input[value="${NONE_ID}"]`);
    const otherInputs = [...els.quizOptions.querySelectorAll('input[type="checkbox"]')].filter(
      (el) => el.value !== NONE_ID
    );

    if (opt.is_none) {
      if (input.checked) {
        state.quizPendingSelections.clear();
        state.quizPendingSelections.add(NONE_ID);
        otherInputs.forEach((el) => {
          el.checked = false;
        });
      } else {
        state.quizPendingSelections.delete(NONE_ID);
      }
      return;
    }

    if (input.checked) {
      if (noneInput) noneInput.checked = false;
      state.quizPendingSelections.delete(NONE_ID);
      state.quizPendingSelections.add(opt.id);
    } else {
      state.quizPendingSelections.delete(opt.id);
    }
  });
}

function renderQuizStep(step) {
  els.quizQuestion.textContent = step.question;
  els.quizOptions.innerHTML = "";
  state.quizPendingSelections.clear();
  updateTagLimitWarnings();

  if (step.phase === "complete") {
    els.quizHint.textContent = state.selectedTags.size
      ? "Questionnaire complete — generating your matches…"
      : "No interests selected — restarting the questions.";
    els.quizContinue.classList.add("hidden");
    els.quizBack.disabled = true;
    if (state.selectedTags.size) {
      setTimeout(() => {
        recommend();
        els.resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 350);
    } else {
      setTimeout(() => initQuiz(), 600);
    }
    return;
  }

  els.quizHint.textContent =
    "Select one or more, then click Continue. Choose None to use the parent category instead.";
  els.quizContinue.classList.remove("hidden");

  step.options.forEach((opt) => {
    const label = document.createElement("label");
    label.className = opt.is_none ? "quiz-check quiz-none" : "quiz-check";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = opt.id;
    bindQuizCheckbox(input, opt);
    label.appendChild(input);
    label.appendChild(document.createTextNode(opt.label));
    els.quizOptions.appendChild(label);
  });

  els.quizBack.disabled = state.quizHistory.length === 0;
}

async function initQuiz({ keepHistory = false } = {}) {
  if (!keepHistory) {
    state.quizHistory = [];
  }
  state.quizPendingSelections.clear();
  let step;
  if (staticMode) {
    step = ClubMatcher.quizStepFromSession(ClubMatcher.emptySession());
  } else {
    const res = await fetch("/api/quiz");
    step = await res.json();
  }
  state.quizSession = step.session;
  renderQuizStep(step);
}

async function continueQuiz() {
  if (!state.quizPendingSelections.size) {
    showError("Select at least one option.");
    return;
  }
  state.quizHistory.push(JSON.parse(JSON.stringify(state.quizSession)));
  const data = await postQuiz({
    session: state.quizSession,
    action: "continue",
    selections: [...state.quizPendingSelections],
  });
  if (!data) return;
  state.quizSession = data.session;
  if (data.tags_added?.length) addQuizTags(data.tags_added);
  renderQuizStep(data);
}

function renderResults(data) {
  els.resultsSection.classList.remove("hidden");
  if (data.count === 0) {
    els.resultsSummary.textContent =
      "No clubs matched your filters. Try fewer blocked times or different tags.";
    els.results.innerHTML = "";
    return;
  }

  const above = data.above_threshold || 0;
  const summary =
    above >= data.count
      ? `${data.count} club${data.count === 1 ? "" : "s"} (all above 50%).`
      : `${data.count} club${data.count === 1 ? "" : "s"} (${above} above 50%, rest fill minimum of ${data.min_results}).`;
  els.resultsSummary.textContent = summary;

  els.results.innerHTML = data.results
    .map((club, i) => {
      const scoreNote = club.above_threshold ? "" : ' <span class="below">below 50%</span>';
      const description = club.description
        ? `<details class="club-description">
             <summary>Description</summary>
             <p>${escapeHtml(club.description)}</p>
           </details>`
        : "";
      return `
      <article class="card">
        <h3>${i + 1}. ${escapeHtml(club.name)}</h3>
        <p class="score">Final score: ${club.final_score_pct}%${scoreNote}</p>
        <p>${escapeHtml(club.category)} · ${club.member_count} members · ${escapeHtml(formatMeeting(club.day, club.period))}${club.room ? ` · Room ${escapeHtml(club.room)}` : ""}</p>
        <p><strong>Tags:</strong> <span class="tags-row">${
          (club.club_tags || [])
            .map(
              (t) =>
                `<span class="tag-chip-sm${t.matched ? " tag-matched" : ""}">${escapeHtml(t.label)}</span>`
            )
            .join("") || "None"
        }</span></p>
        ${description}
      </article>`;
    })
    .join("");
}

async function recommend() {
  clearError();
  const tags = [...state.selectedTags];
  if (!tags.length) {
    showError("Select at least one interest tag.");
    return;
  }

  if (staticMode) {
    renderResults(
      ClubMatcher.recommendPayload(tags, [...state.blockedSlots], state.tagWeightMults)
    );
    return;
  }

  const res = await fetch("/api/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tags,
      tag_weights: state.tagWeightMults,
      blocked_slots: [...state.blockedSlots],
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    showError(data.error || "Recommendation failed.");
    return;
  }
  renderResults(data);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function restartQuiz() {
  clearTags();
  els.resultsSection.classList.add("hidden");
  initQuiz();
}

async function boot() {
  loadSlots();
  try {
    const res = await fetch("/api/tags", { method: "GET" });
    if (res.ok) {
      staticMode = false;
      initQuiz();
      return;
    }
  } catch {
    /* use static mode */
  }
  staticMode = true;
  await ClubMatcher.init("data/");
  initQuiz();
}
els.quizContinue.addEventListener("click", continueQuiz);
els.quizBack.addEventListener("click", async () => {
  const prev = state.quizHistory.pop();
  if (!prev) return;
  state.quizSession = prev;
  const step = await postQuiz({ session: prev, action: "status" });
  if (step) renderQuizStep(step);
});
els.quizRestart.addEventListener("click", restartQuiz);

boot().catch((err) => showError(`Failed to start: ${err.message}`));
