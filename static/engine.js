/** Client-side club matcher engine for GitHub Pages (no Python server). */
const ClubMatcher = (() => {
  const NONE_ID = "__none__";
  let CFG = {};
  let parentMap = {};
  let tagTree = {};
  let topLevel = {};
  let clubs = [];
  let tagList = [];

  function displayName(tag) {
    const special = {
      AI: "AI",
      STEM: "STEM",
      anime: "Anime",
      rc_racing: "RC Racing",
      "3d_modeling": "3D Modeling",
      tcg: "TCG",
    };
    if (special[tag]) return special[tag];
    return tag.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function ancestorChain(tag) {
    const chain = [tag];
    let current = tag;
    while (parentMap[current] != null) {
      current = parentMap[current];
      chain.push(current);
    }
    return chain;
  }

  function hierarchyDistance(a, b) {
    if (a === b) return 0;
    const chainA = ancestorChain(a);
    const chainB = ancestorChain(b);
    let best = null;
    chainA.forEach((ancestor, i) => {
      const j = chainB.indexOf(ancestor);
      if (j >= 0) {
        const d = i + j;
        if (d <= 2 && (best === null || d < best)) best = d;
      }
    });
    return best;
  }

  function hierarchyCoefficient(a, b) {
    const d = hierarchyDistance(a, b);
    if (d === null) return 0;
    if (d === 0) return CFG.HIERARCHY_EXACT;
    if (d === 1) return CFG.HIERARCHY_PARENT_CHILD;
    if (d === 2) return CFG.HIERARCHY_GRANDRELATED;
    return 0;
  }

  function pathToTag(tag) {
    const chain = [tag];
    let current = tag;
    while (parentMap[current] != null) {
      current = parentMap[current];
      chain.push(current);
    }
    return chain.reverse();
  }

  function children(tag) {
    let node = tagTree;
    for (const part of pathToTag(tag)) {
      if (!node[part]) return [];
      node = node[part];
    }
    return Object.keys(node);
  }

  function collapseSingletons(tag) {
    // Follow single-child chains: a node whose only child is a leaf
    // (e.g. motorsport -> rc_racing) never shows a one-option quiz layer;
    // selecting it directly adds the leaf tag.
    while (true) {
      const kids = children(tag);
      if (kids.length === 1) tag = kids[0];
      else return tag;
    }
  }

  function normalizeTag(tag) {
    const lower = tag.trim().replace(/ /g, "_").toLowerCase();
    for (const known of Object.keys(parentMap)) {
      if (known.toLowerCase() === lower) return known;
    }
    return lower;
  }

  function distributeUserWeights(tags, weightMults = {}) {
    const total = CFG.USER_TAG_POINTS;
    if (!tags.length) return {};
    // Selection order does not matter: split the points evenly.
    const base = Math.floor(total / tags.length);
    const remainder = total - base * tags.length;
    const weights = tags.map((_, i) => (i < remainder ? base + 1 : base));
    const scaled = Object.fromEntries(
      tags.map((t, i) => [t, Math.max(0, Math.round(weights[i] * (weightMults[t] ?? 1)))])
    );
    if (Object.values(scaled).reduce((a, b) => a + b, 0) === 0 && tags.length) {
      scaled[tags[0]] = 1;
    }
    return scaled;
  }

  function popularityMultiplier(memberCount) {
    for (const [threshold, mult] of CFG.POPULARITY_TIERS) {
      if (memberCount >= threshold) return mult;
    }
    return 1;
  }

  function filterClubs(blockedSlots) {
    const blocked = new Set(blockedSlots || []);
    return clubs.filter((club) => {
      if (CFG.MIN_ACTIVE_MEMBER_COUNT > 0 && club.member_count <= CFG.MIN_ACTIVE_MEMBER_COUNT) {
        return false;
      }
      const slot = `${club.day}:${club.period}`;
      if (blocked.size && blocked.has(slot)) return false;
      return true;
    });
  }

  function scoreClub(club, userTags) {
    // Club coverage: fraction of the club's 20 tag points the user covers.
    // Each club tag contributes weight x best hierarchy strength to a user tag.
    let matchedPoints = 0;
    const matches = [];
    for (const [clubTag, clubWeight] of Object.entries(club.tags)) {
      let bestUserTag = null;
      let bestStrength = 0;
      for (const userTag of Object.keys(userTags)) {
        const strength = hierarchyCoefficient(userTag, clubTag);
        if (strength > bestStrength) {
          bestStrength = strength;
          bestUserTag = userTag;
        }
      }
      if (bestStrength > 0 && bestUserTag !== null) {
        matchedPoints += clubWeight * bestStrength;
        matches.push({
          userTag: bestUserTag,
          clubTag,
          coeff: bestStrength,
          contribution: clubWeight * bestStrength,
        });
      }
    }

    const precision = Object.keys(club.tags).length ? matchedPoints / CFG.CLUB_TAG_POINTS : 0;

    let recall = 0;
    for (const [userTag, userWeight] of Object.entries(userTags)) {
      let bestStrength = 0;
      for (const clubTag of Object.keys(club.tags)) {
        bestStrength = Math.max(bestStrength, hierarchyCoefficient(userTag, clubTag));
      }
      recall += userWeight * bestStrength;
    }
    recall = Object.keys(userTags).length ? recall / CFG.USER_TAG_POINTS : 0;

    // Highlight only direct branch relationships (exact or parent/child);
    // sibling credit (0.25) still counts toward the score.
    const matchedClubTags = new Set(
      matches.filter((m) => m.coeff >= CFG.HIERARCHY_PARENT_CHILD).map((m) => m.clubTag)
    );

    const pop = popularityMultiplier(club.member_count);
    const finalScore = precision * pop;
    return { club, similarity: precision, precision, recall, finalScore, pop, matches, matchedClubTags };
  }

  function recommend(tagNames, blockedSlots, tagWeightMults = {}) {
    const normalized = tagNames.map(normalizeTag);
    const mults = Object.fromEntries(
      Object.entries(tagWeightMults).map(([k, v]) => [normalizeTag(k), v])
    );
    const userTags = distributeUserWeights(normalized, mults);
    const eligible = filterClubs(blockedSlots);
    const results = eligible
      .map((club) => scoreClub(club, userTags))
      .sort(
        (a, b) =>
          b.finalScore - a.finalScore ||
          b.recall - a.recall ||
          a.club.name.localeCompare(b.club.name)
      );

    let picked;
    if (results.length <= CFG.TOP_N_RESULTS) {
      picked = results;
    } else {
      const cutoff = results[CFG.TOP_N_RESULTS - 1].finalScore;
      if (cutoff > 0) {
        // Keep every club tied with the cutoff score (ties share a rank).
        picked = results.filter((r) => r.finalScore >= cutoff);
      } else {
        picked = results.slice(0, CFG.TOP_N_RESULTS);
      }
    }
    if (picked.length < CFG.MIN_RESULTS) {
      const seen = new Set(picked.map((r) => r.club.no));
      picked = picked.concat(
        results.filter((r) => !seen.has(r.club.no)).slice(0, CFG.MIN_RESULTS - picked.length)
      );
    }
    return picked.map((r) => {
      const matched = r.matchedClubTags;
      const clubTags = Object.entries(r.club.tags)
        .sort((a, b) => b[1] - a[1])
        .map(([id]) => ({
          id,
          label: displayName(id),
          matched: matched.has(id),
        }));
      return {
        name: r.club.name,
        category: r.club.category,
        description: r.club.description,
        member_count: r.club.member_count,
        day: r.club.day,
        period: r.club.period,
        room: r.club.room,
        final_score_pct: Math.round(r.finalScore * 1000) / 10,
        above_threshold: r.finalScore >= CFG.MIN_FINAL_SCORE,
        club_tags: clubTags,
      };
    });
  }

  function emptySession() {
    return {
      phase: "root",
      areas: [],
      area_index: 0,
      branch_queue: [],
      drill_extra: [],
      pending_drill_nodes: [],
    };
  }

  function cloneSession(s) {
    return {
      phase: s.phase,
      areas: [...s.areas],
      area_index: s.area_index,
      branch_queue: [...s.branch_queue],
      drill_extra: [...s.drill_extra],
      pending_drill_nodes: [...(s.pending_drill_nodes || [])],
    };
  }

  function tagAdded(tag, fromNone = false) {
    return {
      tag,
      weight_mult: fromNone ? CFG.NONE_TAG_WEIGHT_MULTIPLIER : 1,
    };
  }

  function noneOption(label) {
    return { id: NONE_ID, label: `None — use ${label} instead`, tag: null, is_leaf: false, is_none: true };
  }

  function optionForTag(tag) {
    return {
      id: tag,
      label: displayName(tag),
      tag: children(tag).length ? null : tag,
      is_leaf: !children(tag).length,
      is_none: false,
    };
  }

  function drillNode(session) {
    return session.drill_extra.length
      ? session.drill_extra[session.drill_extra.length - 1]
      : session.branch_queue[0];
  }

  function advanceToNextArea(session, tagsAdded) {
    session.area_index += 1;
    session.phase = session.area_index >= session.areas.length ? "complete" : "branches";
    return { session, tags_added: tagsAdded };
  }

  function finishCurrentBranch(session, tagsAdded) {
    session.drill_extra = [];
    session.pending_drill_nodes = [];
    session.branch_queue.shift();
    if (session.branch_queue.length) return { session, tags_added: tagsAdded };
    return advanceToNextArea(session, tagsAdded);
  }

  function startNextPendingDrill(session, tagsAdded) {
    if (session.pending_drill_nodes?.length) {
      session.drill_extra = [session.pending_drill_nodes.shift()];
      return { session, tags_added: tagsAdded };
    }
    return finishCurrentBranch(session, tagsAdded);
  }

  function quizStepFromSession(session) {
    session = session || emptySession();
    if (session.phase === "root") {
      return stepPayload(session, {
        step_id: "root",
        question: "What broad areas interest you? (choose one or more)",
        options: [
          ...Object.entries(topLevel).map(([id, meta]) => ({
            id,
            label: meta.label,
            tag: null,
            is_leaf: false,
            is_none: false,
          })),
          noneOption("nothing from this list"),
        ],
        phase: "root",
      });
    }
    if (session.phase === "branches") {
      const area = session.areas[session.area_index];
      const meta = topLevel[area];
      return stepPayload(session, {
        step_id: `${area}:branches`,
        question: meta.prompt,
        options: [...meta.branches.map(optionForTag), noneOption(meta.label)],
        phase: "branches",
      });
    }
    if (session.phase === "drill") {
      const branch = session.branch_queue[0];
      const node = drillNode(session);
      const parentLabel = displayName(node);
      const question = session.drill_extra.length
        ? `Which ${parentLabel} topics fit you? (choose one or more)`
        : `Which ${displayName(branch)} topics fit you? (choose one or more)`;
      return stepPayload(session, {
        step_id: `drill:${branch}:${session.drill_extra.join("/")}`,
        question,
        options: [...children(node).map(optionForTag), noneOption(parentLabel)],
        none_parent_tag: node,
        phase: "drill",
      });
    }
    return stepPayload(session, {
      step_id: "complete",
      question: "Questionnaire complete — generating your matches…",
      options: [],
      can_continue: false,
      multi_select: false,
      phase: "complete",
    });
  }

  function stepPayload(session, partial) {
    return {
      step_id: partial.step_id,
      question: partial.question,
      multi_select: partial.multi_select !== false,
      can_continue: partial.can_continue !== false,
      phase: partial.phase,
      none_parent_tag: partial.none_parent_tag || null,
      session: cloneSession(session),
      options: partial.options || [],
      tags_added: [],
    };
  }

  function drillContinue(session, selections) {
    const node = drillNode(session);
    const valid = new Set(children(node));
    selections.forEach((sel) => {
      if (!valid.has(sel)) throw new Error(`Invalid selection: ${sel}`);
    });

    const tagsAdded = [];
    const drillDeeper = [];
    selections.forEach((sel) => {
      const eff = collapseSingletons(sel);
      if (children(eff).length) drillDeeper.push(eff);
      else tagsAdded.push(tagAdded(eff));
    });

    if (drillDeeper.length) {
      session.drill_extra = [drillDeeper[0]];
      session.pending_drill_nodes = [...drillDeeper.slice(1), ...(session.pending_drill_nodes || [])];
      return { session, tags_added: tagsAdded };
    }
    return startNextPendingDrill(session, tagsAdded);
  }

  function quizContinue(session, selections) {
    session = cloneSession(session);
    if (!selections?.length) throw new Error("Select at least one option before continuing.");
    if (selections.includes(NONE_ID) && selections.length > 1) {
      throw new Error('Choose "None" by itself, or pick other options (not both).');
    }

    if (selections.includes(NONE_ID)) {
      if (session.phase === "root") {
        session.phase = "complete";
        return { session, tags_added: [] };
      }
      if (session.phase === "branches") return advanceToNextArea(session, []);
      if (session.phase === "drill") {
        return startNextPendingDrill(session, [tagAdded(drillNode(session), true)]);
      }
    }

    if (session.phase === "root") {
      session.areas = selections;
      session.area_index = 0;
      session.phase = "branches";
      return { session, tags_added: [] };
    }
    if (session.phase === "branches") {
      const drillDeeper = [];
      const leafTags = [];
      selections.forEach((b) => {
        const eff = collapseSingletons(b);
        if (children(eff).length) drillDeeper.push(eff);
        else leafTags.push(eff);
      });
      session.branch_queue = drillDeeper;
      session.drill_extra = [];
      session.pending_drill_nodes = [];
      const tagsAdded = leafTags.map((t) => tagAdded(t));
      if (!drillDeeper.length) return advanceToNextArea(session, tagsAdded);
      session.phase = "drill";
      return { session, tags_added: tagsAdded };
    }
    if (session.phase === "drill") return drillContinue(session, selections);
    throw new Error("Continue is not available at this step.");
  }

  function handleQuiz(body) {
    const session = body.session || emptySession();
    if (body.action === "restart") return quizStepFromSession(emptySession());
    if (body.action === "status") return quizStepFromSession(session);
    if (body.action === "continue") {
      const { session: next, tags_added } = quizContinue(session, body.selections || []);
      const step = quizStepFromSession(next);
      step.tags_added = tags_added;
      return step;
    }
    throw new Error("Unknown quiz action.");
  }

  async function init(dataBase = "data/") {
    const base = dataBase.endsWith("/") ? dataBase : `${dataBase}/`;
    const [site, clubData] = await Promise.all([
      fetch(`${base}site.json`).then((r) => {
        if (!r.ok) throw new Error("Failed to load site.json");
        return r.json();
      }),
      fetch(`${base}clubs.json`).then((r) => {
        if (!r.ok) throw new Error("Failed to load clubs.json");
        return r.json();
      }),
    ]);
    CFG = site.config;
    parentMap = site.parentMap;
    tagTree = site.tagTree;
    topLevel = site.topLevel;
    tagList = site.tags;
    clubs = clubData;
  }

  function getTags() {
    return { tags: tagList, max_tags: CFG.MAX_USER_TAGS };
  }

  function recommendPayload(tagNames, blockedSlots, tagWeightMults = {}) {
    const results = recommend(tagNames, blockedSlots, tagWeightMults);
    const above = results.filter((r) => r.above_threshold).length;
    return {
      count: results.length,
      above_threshold: above,
      min_results: CFG.MIN_RESULTS,
      tags: tagNames,
      blocked_slots: blockedSlots,
      results,
    };
  }

  return { init, getTags, recommendPayload, quizStepFromSession, handleQuiz, emptySession };
})();

window.ClubMatcher = ClubMatcher;
