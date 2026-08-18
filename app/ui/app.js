const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const CHEVRON = `<svg class="chevron" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" d="M6 9l6 6 6-6"/></svg>`;

const state = {
  strings: {},
  screen: "home",
  data: null,
  capturing: null,
  logsQuery: "",
  logsSelected: null,
  logLines: [],
  logHit: 0,
  runQuery: "",
  runLines: [],
  runHit: 0,
  statsFilter: "all",
  assignSlot: null,
};

function t(id, vars) {
  let text = state.strings[id] || id;
  if (vars) {
    for (const [key, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${key}}`, value);
    }
  }
  return text;
}

function api() {
  return window.pywebview.api;
}

async function call(name, ...args) {
  const fn = api()[name];
  return fn.apply(api(), args);
}

function applyShell(shell) {
  if (!shell) return;
  state.strings = shell.strings || state.strings;
  document.title = shell.title || "PoE Helper";
  $("#app-title").textContent = shell.title || "PoE Helper";
  $("#app-sub").textContent = shell.subtitle || "";
  $("#status").textContent = shell.status || "";
  $("#version").textContent = shell.version || "";
  const icon = $("#brand-icon");
  if (shell.icon) icon.src = shell.icon;
  const meta = $("#meta");
  meta.className = `meta ${shell.meta_kind || ""}`;
  $("#meta-text").textContent = shell.meta || "";
  const btn = $("#lang-btn");
  const pop = $("#lang-pop");
  if (shell.languages && btn && pop) {
    const current = shell.languages.find((row) => row.id === shell.language) || shell.languages[0];
    btn.innerHTML = `<span class="combo-label">${esc(current?.label || "")}</span>${CHEVRON}`;
    pop.innerHTML = `<div class="combo-list">${(shell.languages || [])
      .map(
        (row) =>
          `<button type="button" data-lang="${esc(row.id)}" class="${row.id === shell.language ? "on" : ""}">${esc(row.label)}</button>`
      )
      .join("")}</div>`;
  }
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function searchTokens(query) {
  return String(query || "")
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
}

function textMatch(text, query) {
  const hay = String(text || "").toLowerCase();
  const parts = searchTokens(query);
  if (!parts.length) return true;
  return parts.every((part) => hay.includes(part));
}

function img(src, cls = "") {
  if (!src) return "";
  return `<img class="${cls}" src="${esc(src)}" alt="" onerror="this.remove()">`;
}

function help(text) {
  if (!text) return "";
  return `<button class="help" type="button" data-tip="${esc(text)}" aria-label="?">?</button>`;
}

function page({ title, tip, back, actions = "", extra = "", body, fill = false }) {
  return `
    <div class="page">
      <div class="page-bar">
        <div class="page-bar-left">
          ${back || ""}
          <h1>${esc(title || "")}</h1>
          ${help(tip)}
        </div>
        <div class="page-bar-right">${actions}</div>
      </div>
      ${extra}
      <div class="page-body${fill ? " fill" : ""}">${body}</div>
    </div>`;
}

function backBtn(label, attrs = 'data-home') {
  return `<button class="btn" ${attrs}>${esc(label)}</button>`;
}

function toast(message, kind = "error", ms = 4500) {
  const host = $("#toasts");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

function ask(text) {
  return new Promise((resolve) => {
    const modal = $("#modal");
    $("#modal-text").textContent = text;
    $("#modal-ok").textContent = t("overlay.ok") === "overlay.ok" ? "OK" : t("overlay.ok");
    $("#modal-cancel").textContent = t("overlay.cancel");
    modal.hidden = false;
    modal.classList.remove("hidden");
    const done = (ok) => {
      modal.hidden = true;
      modal.classList.add("hidden");
      $("#modal-ok").onclick = null;
      $("#modal-cancel").onclick = null;
      resolve(ok);
    };
    $("#modal-ok").onclick = () => done(true);
    $("#modal-cancel").onclick = () => done(false);
  });
}

async function go(name, extra = {}) {
  const data = await call("navigate", name, extra.scenario_id || "", extra.prefer_chain || false);
  render(data);
}

function render(data) {
  if (!data) return;
  state.data = data;
  state.screen = data.screen || "home";
  applyShell(data.shell);
  closeCombos();
  const view = $("#view");
  const painters = {
    home: paintHome,
    wizard: paintWizard,
    scenarios: paintScenarios,
    settings: paintSettings,
    run: paintRun,
    logs: paintLogs,
    stats: paintStats,
    heist: paintHeist,
    reveal: paintReveal,
  };
  (painters[state.screen] || paintHome)(view, data);
}

function paintHome(view, data) {
  const hk = data.hotkeys || {};
  const count = data.scenario_count || 0;
  const tiles = [
    ["wizard", "create", t("home.create"), t("home.create_sub"), !data.ready],
    ["scenarios", "scenarios", t("home.scenarios"), count ? t("home.scenarios_count", { count }) : t("home.scenarios_empty"), false],
    ["run", "run", t("home.run"), t("home.run_sub", { start: hk.start, stop: hk.stop }), !data.ready],
    ["logs", "logs", t("home.logs"), t("home.logs_sub"), false],
    ["stats", "stats", t("home.stats"), t("home.stats_sub"), false],
    ["heist", "heist", t("home.heist"), t("home.heist_sub"), false],
    ["reveal", "reveal", t("home.reveal"), t("home.reveal_sub"), false],
    ["settings", "settings", t("home.settings"), t("home.settings_sub"), false],
  ];
  view.innerHTML = page({
    title: t("home.title"),
    tip: data.hint || t("home.hint"),
    body: `<div class="tiles">
      ${tiles
        .map(
          ([screen, icon, title, sub, locked]) => `
        <button class="tile" data-go="${screen}" ${locked ? "disabled" : ""}>
          ${img(`../assets/home/${icon}.png`)}
          <span><strong>${esc(title)}</strong><span>${esc(sub)}</span></span>
        </button>`
        )
        .join("")}
    </div>`,
  });
  view.onclick = (ev) => {
    const btn = ev.target.closest("[data-go]");
    if (!btn) return;
    go(btn.dataset.go);
  };
}

function paintWizard(view, data) {
  const steps = (data.labels || [])
    .map((label, i) => `<span class="${i + 1 === data.step ? "on" : ""}">${i + 1}. ${esc(label)}</span>`)
    .join("");
  let body = "";
  if (data.step === 1) {
    body = (data.groups || [])
      .map(
        (group) => `
        <div class="group-label">${esc(group.label)}</div>
        <div class="grid4">
          ${(group.items || [])
            .map(
              (item) => `
            <button class="item-tile ${item.id === data.item_type ? "on" : ""}" data-item="${esc(item.id)}">
              ${img(item.icon)}
              <span><strong>${esc(item.name)}</strong><span>${esc(item.sub)}</span></span>
            </button>`
            )
            .join("")}
        </div>`
      )
      .join("");
  } else if (data.step === 2) {
    body = `<div class="grid2">${(data.crafts || [])
      .map(
        (craft) => `
      <button class="craft-tile ${craft.id === data.craft_type ? "on" : ""}" data-craft="${esc(craft.id)}">
        ${img(craft.icon)}
        <span><strong>${esc(craft.name)}</strong><span>${esc(craft.desc)}</span></span>
      </button>`
      )
      .join("")}</div>`;
  } else if (data.step === 3) {
    if (!(data.steps || []).length) {
      body = `<div class="card">
        <strong>${esc(t("wizard.s3_empty"))}</strong>
        <p class="muted" style="margin:6px 0 0">${esc(t("wizard.s3_empty_hint"))}</p>
      </div>`;
    } else {
      body = (data.steps || []).map((step) => stepCard(step, data)).join("");
    }
  } else {
    const summary = (data.summary || []).map((line, i) => {
      const row = typeof line === "string" ? { text: line, icon: "" } : line;
      return `<div class="summary-step">${img(row.icon)}<div>${i + 1}. ${esc(row.text)}</div></div>`;
    }).join("");
    body = `
      <label class="label">${esc(t("wizard.name"))}</label>
      <input class="field" id="wiz-name" value="${esc(data.name || "")}">
      <div class="card" style="margin-top:12px">
        <div class="summary-meta">
          <div class="summary-chip">${img(data.item_icon)}<span>${esc(t("wizard.item", { name: data.item_name }))}</span></div>
          <div class="summary-chip">${img(data.craft_icon)}<span>${esc(t("wizard.method", { name: data.craft_name }))}</span></div>
        </div>
        ${summary}
      </div>`;
  }
  const titles = {
    1: [t("wizard.s1_title"), t("wizard.s1_sub")],
    2: [t("wizard.s2_title"), t("wizard.s2_sub")],
    3: [t("wizard.s3_title"), t("wizard.s3_sub")],
    4: [t("wizard.s4_title"), ""],
  };
  const [title, sub] = titles[data.step] || ["", ""];
  let actions = "";
  if (data.step === 3) {
    actions += `<button class="btn" data-add-step>${esc(t("wizard.add_step"))}</button>`;
    actions += `<button class="btn primary" data-wiz="next">${esc(t("nav.next"))}</button>`;
  } else if (data.step === 4) {
    actions = `<button class="btn primary" data-wiz="save">${esc(t("nav.save"))}</button>`;
  }
  view.innerHTML = page({
    title,
    tip: sub,
    back: backBtn(data.step > 1 ? t("nav.back") : t("nav.home"), 'data-wiz="back"'),
    actions,
    extra: `<div class="page-sub">${steps}</div>`,
    body,
  });
  bindWizard(view, data);
}

function stepCard(step, data) {
  const action = combo("action", data.actions, step.action_id, t("search.action"));
  const kind = combo("kind", data.kinds, step.kind, t("wizard.condition"));
  const augment = step.show_augment
    ? `<div style="margin-top:10px"><div class="section-head"><span class="label" style="margin:0">${esc(t("wizard.augment"))}</span>${help(t("wizard.augment_hint"))}</div>${combo("augment", data.augments, step.augment, t("wizard.augment"))}</div>`
    : "";
  let mods = "";
  if (step.needs_mods) {
    const unused = (data.mods || []).filter((row) => !(step.mods || []).some((m) => m.mod_type_id === row.id));
    mods = `
      <div class="row" style="margin-top:10px">
        <span class="muted">${esc(t("wizard.required_weight"))}</span>
        <input class="field" data-required style="width:64px" value="${esc(step.required)}">
      </div>
      <div class="label" style="margin-top:10px">${esc(t("wizard.mods"))}</div>
      ${combo("modadd", unused, "", t("search.mod"))}
      <table class="table">
        <tr>
          <th>${esc(t("table.mod"))}</th>
          <th>${esc(t("table.value"))}</th>
          <th>${esc(t("table.tier"))}</th>
          <th>${esc(t("table.need"))}</th>
          <th>${esc(t("table.group"))}</th>
          <th>${esc(t("table.count"))}</th>
          <th></th>
        </tr>
        ${(step.mods || [])
          .map(
            (row, mi) => `
          <tr data-mod="${mi}">
            <td><span class="chip ${esc(row.generation)}">${row.generation === "suffix" ? "S" : "P"}</span> ${esc(row.name)}</td>
            <td><input data-f="value" value="${esc(row.value)}"></td>
            <td><select data-f="tier">${(row.tiers || [])
              .map((opt) => `<option value="${esc(opt.id)}" ${String(row.tier || "any") === opt.id ? "selected" : ""}>${esc(opt.name)}</option>`)
              .join("")}</select></td>
            <td><input data-f="need" value="${esc(row.need)}"></td>
            <td><input data-f="group" value="${esc(row.group)}"></td>
            <td><input data-f="count" value="${esc(row.count)}" ${row.group ? "" : "disabled"}></td>
            <td><button class="btn icon" data-del-mod>×</button></td>
          </tr>`
          )
          .join("")}
      </table>
      <div class="card" style="margin-top:8px">
        <strong>${esc(t("table.odds"))}</strong>
        ${(step.odds || []).length
          ? (step.odds || [])
              .map(
                (row) =>
                  `<div class="row" style="margin-top:4px"><span class="chip ${esc(row.generation)}">${row.generation === "suffix" ? "S" : "P"}</span><span class="grow">${esc(row.name)}</span><span>${row.weight || "—"}</span><strong>${row.chance ? row.chance.toFixed(1) + "%" : "—"}</strong></div>`
              )
              .join("")
          : `<div class="muted" style="margin-top:6px">${esc(t("table.odds_empty"))}</div>`}
      </div>`;
  }
  return `<div class="card" data-step="${step.index}" style="margin-top:10px">
    <div class="row">
      <strong>${esc(t("wizard.step_n", { n: step.index + 1 }))}</strong>
      <span class="grow"></span>
      <button class="btn icon danger" data-del-step>×</button>
    </div>
    <div class="grid2" style="margin-top:10px">
      <div><div class="label">${esc(t("wizard.action"))}</div>${action}</div>
      <div><div class="label">${esc(t("wizard.until"))}</div>${kind}</div>
    </div>
    ${augment}${mods}
  </div>`;
}

function combo(kind, items, selected, placeholder) {
  const current = (items || []).find((row) => row.id === selected);
  const label = current ? current.name : placeholder || "";
  return `<div class="combo" data-combo="${kind}">
    <button type="button" class="combo-trigger" data-selected="${esc(selected || "")}" aria-expanded="false">
      ${current?.icon ? img(current.icon) : ""}
      <span class="combo-label${current ? "" : " placeholder"}">${esc(label)}</span>
      ${CHEVRON}
    </button>
    <div class="combo-pop" hidden>
      <input class="combo-search" placeholder="${esc(placeholder || "")}">
      <div class="combo-list">
        ${(items || [])
          .map(
            (row) =>
              `<button type="button" data-id="${esc(row.id)}" class="${row.id === selected ? "on" : ""}">${img(row.icon)}<span class="chip ${esc(row.generation || "")}" ${row.generation ? "" : "hidden"}>${row.generation === "suffix" ? "S" : row.generation === "prefix" ? "P" : ""}</span><span>${esc(row.name)}</span></button>`
          )
          .join("") || `<div class="combo-empty">${esc(t("logs.no_results"))}</div>`}
      </div>
    </div>
  </div>`;
}

function placePop(trigger, pop) {
  const r = trigger.getBoundingClientRect();
  pop.style.position = "fixed";
  pop.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - 280))}px`;
  pop.style.width = `${Math.max(r.width, 260)}px`;
  pop.style.right = "auto";
  const spaceBelow = window.innerHeight - r.bottom;
  if (spaceBelow < 220 && r.top > spaceBelow) {
    pop.style.top = "auto";
    pop.style.bottom = `${window.innerHeight - r.top + 4}px`;
  } else {
    pop.style.top = `${r.bottom + 4}px`;
    pop.style.bottom = "auto";
  }
}

function parkPop(pop) {
  const home = pop._comboHome;
  pop.hidden = true;
  if (home && pop.parentElement !== home) home.appendChild(pop);
  if (home) {
    home.removeAttribute("data-open");
    const trigger = $(".combo-trigger", home);
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  } else {
    const trigger = pop.parentElement?.querySelector?.(".combo-trigger");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }
}

function closeCombos(except) {
  $$(".combo-pop").forEach((pop) => {
    if (except && (pop._comboHome === except || except.contains(pop))) return;
    parkPop(pop);
  });
}

function bindCombo(root, onPick) {
  $$(".combo", root).forEach((box) => {
    const trigger = $(".combo-trigger", box);
    const pop = $(".combo-pop", box);
    const search = $(".combo-search", box);
    const list = $(".combo-list", box);
    if (!trigger || !pop) return;
    const filter = () => {
      const q = search?.value || "";
      let shown = 0;
      $$("button[data-id]", list).forEach((btn) => {
        const hide = Boolean(q.trim() && !textMatch(btn.textContent, q));
        btn.hidden = hide;
        if (!hide) shown += 1;
      });
      let empty = $(".combo-empty", list);
      if (!shown) {
        if (!empty) {
          empty = document.createElement("div");
          empty.className = "combo-empty";
          empty.textContent = t("logs.no_results");
          list.appendChild(empty);
        }
        empty.hidden = false;
      } else if (empty) {
        empty.hidden = true;
      }
    };
    trigger.addEventListener("mousedown", (ev) => ev.preventDefault());
    trigger.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const open = pop.hidden;
      closeCombos(box);
      if (open) {
        pop._comboHome = box;
        box.setAttribute("data-open", "1");
        document.body.appendChild(pop);
        pop.hidden = false;
        trigger.setAttribute("aria-expanded", "true");
        placePop(trigger, pop);
        if (search) {
          search.value = "";
          filter();
          setTimeout(() => search.focus(), 0);
        }
      } else {
        parkPop(pop);
      }
    });
    search?.addEventListener("input", filter);
    search?.addEventListener("keydown", (ev) => {
      ev.stopPropagation();
      if (ev.key === "Escape") {
        parkPop(pop);
        trigger.focus();
      }
    });
    trigger.addEventListener("keydown", (ev) => {
      if (pop.hidden) return;
      if (ev.key.length === 1 && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
        search.focus();
        search.value += ev.key;
        filter();
        ev.preventDefault();
      }
    });
    list.addEventListener("mousedown", (ev) => {
      const btn = ev.target.closest("button[data-id]");
      if (!btn) return;
      ev.preventDefault();
      onPick(box.dataset.combo, btn.dataset.id, box.closest("[data-step]"));
    });
  });
}

function bindWizard(view, data) {
  view.onclick = async (ev) => {
    const item = ev.target.closest("[data-item]");
    if (item) return render(await call("wizard_select_item", item.dataset.item));
    const craft = ev.target.closest("[data-craft]");
    if (craft) return render(await call("wizard_select_craft", craft.dataset.craft));
    if (ev.target.closest("[data-add-step]")) return render(await call("wizard_add_step"));
    const del = ev.target.closest("[data-del-step]");
    if (del) return render(await call("wizard_remove_step", Number(del.closest("[data-step]").dataset.step)));
    const delMod = ev.target.closest("[data-del-mod]");
    if (delMod) {
      const card = delMod.closest("[data-step]");
      const row = delMod.closest("[data-mod]");
      return render(await call("wizard_remove_mod", Number(card.dataset.step), Number(row.dataset.mod)));
    }
    const nav = ev.target.closest("[data-wiz]");
    if (!nav) return;
    if (nav.dataset.wiz === "save") return render(await call("wizard_save", $("#wiz-name")?.value || ""));
    render(await call("wizard_goto", nav.dataset.wiz));
  };
  bindCombo(view, async (kind, id, card) => {
    if (kind === "action") return render(await call("wizard_patch_step", Number(card.dataset.step), { action_id: id }));
    if (kind === "kind") return render(await call("wizard_patch_step", Number(card.dataset.step), { kind: id }));
    if (kind === "augment") return render(await call("wizard_patch_step", Number(card.dataset.step), { augment: id }));
    if (kind === "modadd") return render(await call("wizard_add_mod", Number(card.dataset.step), id));
  });
  view.onchange = async (ev) => {
    const card = ev.target.closest("[data-step]");
    if (!card) return;
    if (ev.target.matches("[data-required]")) {
      return render(await call("wizard_patch_step", Number(card.dataset.step), { required: ev.target.value }));
    }
    const row = ev.target.closest("[data-mod]");
    if (!row) return;
    const field = ev.target.dataset.f;
    if (!field) return;
    render(await call("wizard_patch_mod", Number(card.dataset.step), Number(row.dataset.mod), { [field]: ev.target.value }));
  };
}

function paintScenarios(view, data) {
  const items = data.items || [];
  view.innerHTML = page({
    title: t("home.scenarios"),
    back: backBtn(t("nav.back")),
    body: items.length
      ? `<div class="list">${items
          .map(
            (row) => `<div class="card">
                <strong>${esc(row.name)}</strong>
                <div class="muted" style="margin:4px 0 10px">${esc(row.meta)}</div>
                <div class="row">
                  <button class="btn" data-edit="${esc(row.id)}">${esc(t("scenarios.edit"))}</button>
                  <button class="btn danger" data-del="${esc(row.id)}" data-name="${esc(row.name)}">${esc(t("scenarios.delete"))}</button>
                  <span class="grow"></span>
                  <button class="btn primary" data-run="${esc(row.id)}">${esc(t("scenarios.run"))}</button>
                </div>
              </div>`
          )
          .join("")}</div>`
      : `<p class="muted">${esc(t("scenarios.empty"))}</p>`,
  });
  view.onclick = async (ev) => {
    if (ev.target.closest("[data-home]")) return go("home");
    const edit = ev.target.closest("[data-edit]");
    if (edit) return go("wizard", { scenario_id: edit.dataset.edit });
    const run = ev.target.closest("[data-run]");
    if (run) return go("run", { scenario_id: run.dataset.run });
    const del = ev.target.closest("[data-del]");
    if (!del) return;
    if (await ask(t("scenarios.delete_confirm", { name: del.dataset.name }))) {
      render(await call("scenario_delete", del.dataset.del));
    }
  };
}

function paintRun(view, data) {
  view.innerHTML = page({
    title: t("run.title"),
    tip: data.hint || "",
    back: backBtn(t("nav.back")),
    actions: `
      <button class="btn primary" data-start>${esc(t("run.start"))}</button>
      <button class="btn ${data.prefer_chain ? "primary" : ""}" data-chain>${esc(t("run.chain"))}</button>
      <button class="btn danger" data-stop>${esc(t("run.stop"))}</button>`,
    fill: true,
    body: `<div class="split">
      <div class="list" id="run-list">
        ${(data.items || []).length
          ? (data.items || [])
              .map(
                (row) => `<button class="pick ${row.id === data.selected_id ? "on" : ""}" data-id="${esc(row.id)}">
                  <strong>${esc(row.name)}</strong><span>${esc(row.meta)}</span>
                </button>`
              )
              .join("")
          : `<div class="muted">${esc(t("scenarios.empty"))}</div>`}
      </div>
      <div class="card">
        <div class="${data.ready_kind === "danger" ? "danger" : "muted"}">${esc(data.ready || "")}</div>
        <strong id="run-status" style="display:block;margin:8px 0">${esc(data.status || t("run.idle"))}</strong>
        <div class="row" style="margin-bottom:8px">
          <button class="btn" data-edit>${esc(t("scenarios.edit"))}</button>
          <button class="btn danger" data-del>${esc(t("scenarios.delete"))}</button>
        </div>
        <div class="log-toolbar">
          <input class="field grow" id="run-search" placeholder="${esc(t("logs.search"))}" value="${esc(state.runQuery)}">
          <span class="log-hits" id="run-hits"></span>
          <button class="btn icon" data-log-prev title="↑">↑</button>
          <button class="btn icon" data-log-next title="↓">↓</button>
        </div>
        <pre class="log" id="run-log"></pre>
      </div>
    </div>`,
  });
  state.runLines = data.log || [];
  $("#run-search").oninput = (ev) => {
    state.runQuery = ev.target.value;
    renderRunLog();
  };
  view.onclick = async (ev) => {
    if (ev.target.closest("[data-home]")) return go("home");
    if (ev.target.closest("[data-log-prev]")) return jumpHits("#run-log", "runHit", -1);
    if (ev.target.closest("[data-log-next]")) return jumpHits("#run-log", "runHit", 1);
    const pick = ev.target.closest("[data-id]");
    if (pick) return render(await call("run_select", pick.dataset.id));
    if (ev.target.closest("[data-start]")) return render(await call("run_start", false));
    if (ev.target.closest("[data-chain]")) return render(await call("run_start", true));
    if (ev.target.closest("[data-stop]")) return render(await call("run_stop"));
    if (ev.target.closest("[data-edit]")) {
      if (!data.selected_id) return toast(t("run.need_scenario"));
      return go("wizard", { scenario_id: data.selected_id });
    }
    if (ev.target.closest("[data-del]")) {
      const row = (data.items || []).find((item) => item.id === data.selected_id);
      if (!row) return toast(t("run.need_scenario"));
      if (await ask(t("scenarios.delete_confirm", { name: row.name }))) {
        render(await call("scenario_delete", row.id));
      }
    }
  };
  renderRunLog(true);
}

function paintSettings(view, data) {
  view.innerHTML = page({
    title: t("settings.title"),
    back: backBtn(t("nav.back")),
    body: `
    <div class="section"><div class="section-head"><h3>${esc(t("settings.craft"))}</h3></div>
      <div class="card">
        <div class="section-head"><span class="label" style="margin:0">${esc(t("settings.speed"))}</span>${help(t("settings.speed_hint"))}</div>
        <div class="row" style="margin:8px 0">
          <input id="speed" type="range" min="15" max="400" value="${esc(data.speed_ms)}" class="grow">
          <span id="speed-val">${esc(data.speed_ms)} ms</span>
        </div>
        <label class="row" style="margin-top:8px"><input id="logs-on" type="checkbox" ${data.logs_enabled ? "checked" : ""}> ${esc(t("settings.logs"))}</label>
        <label class="row" style="margin-top:8px"><input id="shift-on" type="checkbox" ${data.shift_lock ? "checked" : ""}> ${esc(t("settings.shift_lock"))}${help(t("settings.shift_lock_hint"))}</label>
        <div class="section-head" style="margin-top:14px"><strong>${esc(t("settings.hud"))}</strong>${help(t("settings.hud_hint"))}</div>
        <div class="row" style="margin-top:8px">
          <span class="grow muted">${esc(data.hud)}</span>
          <button class="btn" data-reset-hud>${esc(t("settings.hud_reset"))}</button>
          <button class="btn primary" data-map="hud">${esc(t("settings.set_overlay"))}</button>
        </div>
      </div>
    </div>
    <div class="section"><div class="section-head"><h3>${esc(t("settings.hotkeys"))}</h3>${help(t("settings.hotkeys_hint"))}</div>
      <div class="card">
        ${hotkeyRow("start", t("settings.hotkey_start"), data.hotkey_start)}
        ${hotkeyRow("chain", t("settings.hotkey_chain"), data.hotkey_chain)}
        ${hotkeyRow("stop", t("settings.hotkey_stop"), data.hotkey_stop)}
        ${hotkeyRow("heist_start", t("settings.hotkey_heist_start"), data.heist_hotkey)}
        ${hotkeyRow("heist_stop", t("settings.hotkey_heist_stop"), data.heist_exit_hotkey)}
        ${hotkeyRow("reveal_start", t("settings.hotkey_reveal_start"), data.reveal_hotkey)}
        ${hotkeyRow("reveal_stop", t("settings.hotkey_reveal_stop"), data.reveal_exit_hotkey)}
      </div>
    </div>
    <div class="section"><div class="section-head"><h3>${esc(t("settings.item"))}</h3>${help(t("settings.item_hint"))}</div>
      <div class="card">
        <div class="row"><span class="grow muted">${esc(data.item)}</span>
        <button class="btn primary" data-map="item">${esc(t("settings.set_overlay"))}</button></div>
      </div>
    </div>
    <div class="section"><div class="section-head"><h3>${esc(t("settings.chain"))}</h3>${help(t("settings.chain_hint"))}</div>
      <div class="card">
        <div class="row"><span class="grow muted">${esc(data.chain)}</span>
        <button class="btn primary" data-map="chain">${esc(t("settings.set_overlay"))}</button></div>
      </div>
    </div>
    <div class="section"><div class="section-head"><h3>${esc(t("settings.currency_tab"))}</h3>${help(t("settings.tab_hint"))}</div>
      <div class="card">
        <div class="row"><span class="grow muted">${esc(data.tab)}</span>
        <button class="btn primary" data-map="tab">${esc(t("settings.map_tab"))}</button></div>
        <div class="muted" style="margin:8px 0">${esc(data.tab_mapped)}</div>
        <div class="slots">${(data.slot_groups || [])
          .map(
            (group) =>
              `<div class="slot-grid" style="grid-template-columns:repeat(${group.cols},46px)">${(group.slots || [])
                .map((slot) => `<button class="slot ${slot.filled ? "on" : ""}" data-slot="${esc(slot.key)}">${esc(slot.label)}</button>`)
                .join("")}</div>`
          )
          .join("")}</div>
        <div id="slot-assign" style="margin-top:10px"></div>
      </div>
    </div>
    <div class="section"><div class="section-head"><h3>${esc(t("settings.currencies"))}</h3></div>
      <div class="card">${(data.currencies || [])
        .map(
          (row) => `<div class="row currency-row" style="margin:6px 0">${img(row.icon)}<span style="width:220px">${esc(row.name)}</span><span class="muted grow">${esc(row.status)}</span>
          <button class="btn primary" data-map="position" data-target="${esc(row.id)}">${esc(t("settings.set_overlay"))}</button></div>`
        )
        .join("")}</div>
    </div>
    <div class="section"><div class="section-head"><h3>${esc(t("settings.buttons"))}</h3></div>
      <div class="card">${(data.buttons || [])
        .map(
          (row) => `<div class="row" style="margin:6px 0"><span style="width:220px">${esc(row.name)}</span><span class="muted grow">${esc(row.status)}</span>
          <button class="btn primary" data-map="position" data-target="${esc(row.id)}">${esc(t("settings.set_overlay"))}</button></div>`
        )
        .join("")}</div>
    </div>
    <div class="section"><div class="section-head"><h3>${esc(t("settings.data"))}</h3></div>
      <div class="card"><button class="btn" data-refresh>${esc(t("home.refresh"))}</button></div>
    </div>`,
  });
  $("#speed").oninput = () => ($("#speed-val").textContent = `${$("#speed").value} ms`);
  $("#speed").onchange = () => saveSettings();
  $("#logs-on").onchange = () => saveSettings();
  $("#shift-on").onchange = () => saveSettings();
  view.onclick = async (ev) => {
    if (ev.target.closest("[data-home]")) return go("home");
    if (ev.target.closest("[data-refresh]")) return render(await call("reload_catalog", true));
    if (ev.target.closest("[data-reset-hud]")) return render(await call("settings_reset_hud"));
    const map = ev.target.closest("[data-map]");
    if (map) return call("settings_map", map.dataset.map, map.dataset.target || "");
    const clear = ev.target.closest("[data-hotkey-clear]");
    if (clear) {
      if (clear.disabled) return;
      cancelHotkeyCapture();
      return render(await call("settings_hotkey", clear.dataset.hotkeyClear, ""));
    }
    const key = ev.target.closest("[data-hotkey]");
    if (key) {
      beginHotkeyCapture("settings", key.dataset.hotkey, key);
      return;
    }
    const slot = ev.target.closest("[data-slot]");
    if (slot) {
      state.assignSlot = slot.dataset.slot;
      const host = $("#slot-assign");
      host.innerHTML = `<div class="label">${esc(t("settings.assign_slot"))}</div>${combo("assign", data.assign_items, "", t("search.action"))}`;
      bindCombo(host, async (_kind, id) => {
        render(await call("settings_assign_slot", state.assignSlot, id));
      });
    }
  };
}

async function saveSettings() {
  render(
    await call("settings_save", {
      speed_ms: Number($("#speed").value),
      logs_enabled: $("#logs-on").checked,
      shift_lock: $("#shift-on").checked,
    })
  );
}

function hotkeyRow(kind, label, value) {
  const bound = String(value || "").trim();
  const shown = bound || t("settings.hotkey_none");
  return `<div class="row" style="margin-top:8px"><span class="muted grow">${esc(label)}</span>
    <button class="btn" data-hotkey="${kind}">${esc(shown)}</button>
    <button class="btn danger" data-hotkey-clear="${kind}" ${bound ? "" : "disabled"}>${esc(t("settings.hotkey_remove"))}</button></div>`;
}

function paintLogs(view, data) {
  view.innerHTML = page({
    title: t("logs.title"),
    tip: t("logs.hint"),
    back: backBtn(t("nav.back")),
    actions: `<button class="btn danger" data-del ${state.logsSelected ? "" : "disabled"}>${esc(t("logs.delete"))}</button>`,
    fill: true,
    body: `<div class="split">
      <div class="list" id="log-list">${paintLogGroups(data)}</div>
      <div class="log-pane">
        <div class="log-toolbar">
          <input class="field grow" id="log-search" placeholder="${esc(t("logs.search"))}" value="${esc(state.logsQuery)}" ${state.logsSelected ? "" : "disabled"}>
          <span class="log-hits" id="log-hits"></span>
          <button class="btn icon" data-prev title="↑" ${state.logsSelected ? "" : "disabled"}>↑</button>
          <button class="btn icon" data-next title="↓" ${state.logsSelected ? "" : "disabled"}>↓</button>
        </div>
        <strong id="log-head" style="display:block;margin-bottom:8px">${esc(t("logs.pick"))}</strong>
        <pre class="log" id="log-body"></pre>
      </div>
    </div>`,
  });
  $("#log-search").oninput = (ev) => {
    state.logsQuery = ev.target.value;
    renderLogBody();
  };
  view.onclick = async (ev) => {
    if (ev.target.closest("[data-home]")) return go("home");
    if (ev.target.closest("[data-prev]")) return jumpLog(-1);
    if (ev.target.closest("[data-next]")) return jumpLog(1);
    const row = ev.target.closest("[data-sid]");
    if (row) {
      await openLog(row.dataset.sid);
      return;
    }
    if (ev.target.closest("[data-del]") && state.logsSelected) {
      const next = await call("logs_delete", state.logsSelected);
      state.logsSelected = null;
      state.logLines = [];
      state.logsQuery = "";
      $("#log-list").innerHTML = paintLogGroups(next);
      $("#log-head").textContent = t("logs.pick");
      $("#log-search").value = "";
      $("#log-search").disabled = true;
      $$("[data-prev],[data-next],[data-del]").forEach((el) => (el.disabled = true));
      renderLogBody();
    }
  };
  if (state.logsSelected) openLog(state.logsSelected);
}

async function openLog(id) {
  state.logsSelected = id;
  $$("#log-list .pick").forEach((el) => el.classList.toggle("on", el.dataset.sid === id));
  const detail = await call("logs_open", id, "");
  if (detail.missing) {
    state.logsSelected = null;
    state.logLines = [];
    $("#log-head").textContent = t("logs.pick");
    renderLogBody();
    return;
  }
  state.logLines = detail.lines || [];
  $("#log-head").textContent = detail.heading || t("logs.pick");
  const search = $("#log-search");
  if (search) {
    search.disabled = false;
    search.focus();
  }
  $$("[data-prev],[data-next],[data-del]").forEach((el) => (el.disabled = false));
  renderLogBody();
  if (detail.running) {
    const box = $("#log-body");
    if (box) box.scrollTop = box.scrollHeight;
  }
}

function highlightLine(text, query) {
  const line = String(text ?? "");
  const parts = searchTokens(query);
  if (!parts.length) return esc(line);
  const lower = line.toLowerCase();
  const marks = new Array(line.length).fill(false);
  for (const part of parts) {
    let i = 0;
    while (i < lower.length) {
      const j = lower.indexOf(part, i);
      if (j < 0) break;
      for (let k = 0; k < part.length; k++) marks[j + k] = true;
      i = j + part.length;
    }
  }
  let out = "";
  let i = 0;
  while (i < line.length) {
    const on = marks[i];
    let j = i + 1;
    while (j < line.length && marks[j] === on) j += 1;
    const chunk = esc(line.slice(i, j));
    out += on ? `<mark>${chunk}</mark>` : chunk;
    i = j;
  }
  return out;
}

function renderLogBody() {
  fillLog("#log-body", "#log-hits", state.logsSelected ? state.logLines : [], state.logsQuery, "logHit");
}

function renderRunLog(stickBottom) {
  fillLog("#run-log", "#run-hits", state.runLines, state.runQuery, "runHit", stickBottom);
}

function fillLog(boxSel, hitsSel, lines, query, hitKey, stickBottom) {
  const box = $(boxSel);
  const hitsEl = $(hitsSel);
  if (!box) return;
  const q = (query || "").trim();
  const rows = lines || [];
  if (!rows.length) {
    box.innerHTML = "";
    if (hitsEl) hitsEl.textContent = "";
    return;
  }
  let hitCount = 0;
  box.innerHTML = rows
    .map((line, i) => {
      const hit = q && textMatch(line, q);
      if (hit) hitCount += 1;
      return `<div class="log-line${hit ? " hit" : ""}" data-i="${i}">${highlightLine(line, q)}</div>`;
    })
    .join("");
  if (hitsEl) {
    hitsEl.textContent = q ? (hitCount ? t("logs.hits", { n: hitCount }) : t("logs.no_hits")) : "";
  }
  state[hitKey] = hitCount ? Math.min(state[hitKey] || 0, hitCount - 1) : 0;
  if (q && hitCount) jumpHits(boxSel, hitKey, 0);
  else if (stickBottom) box.scrollTop = box.scrollHeight;
}

function jumpLog(dir) {
  jumpHits("#log-body", "logHit", dir);
}

function jumpHits(boxSel, hitKey, dir) {
  const hits = $$(`${boxSel} .log-line.hit`);
  if (!hits.length) return;
  const next = ((state[hitKey] || 0) + dir + hits.length) % hits.length;
  state[hitKey] = next;
  hits.forEach((el) => el.classList.remove("current"));
  const el = hits[next];
  if (!el) return;
  el.classList.add("current");
  el.scrollIntoView({ block: "center" });
}

function paintLogGroups(data) {
  if (!(data.groups || []).length) return `<div class="muted">${esc(data.empty || t("logs.empty"))}</div>`;
  return (data.groups || [])
    .map(
      (group) =>
        `<div class="group-label">${esc(group.name)}</div>${(group.items || [])
          .map(
            (row) =>
              `<button class="pick ${row.id === state.logsSelected ? "on" : ""}" data-sid="${esc(row.id)}">${esc(row.label)}</button>`
          )
          .join("")}`
    )
    .join("");
}

function paintStats(view, data) {
  const scenarios = data.scenarios || [];
  if (!scenarios.length && !(data.currencies || []).length) {
    view.innerHTML = page({
      title: t("stats.title"),
      tip: t("stats.hint"),
      back: backBtn(t("nav.back")),
      body: `<p class="muted">${esc(t("stats.empty"))}</p>`,
    });
    view.onclick = (ev) => {
      if (ev.target.closest("[data-home]")) go("home");
    };
    return;
  }
  const selected = scenarios.find((row) => row.id === state.statsFilter);
  const currencies = selected ? selected.currencies : data.currencies || [];
  const crafts = selected ? selected.crafts : data.crafts || 0;
  const sessions = selected ? selected.sessions : data.sessions || 0;
  const mods = selected ? selected.mods || [] : data.mods || [];
  const currencyRows = currencies.length
    ? currencies
        .map(
          (row) => `<div class="stat-row">
            ${img(row.icon)}
            <span class="grow">${esc(row.name)}</span>
            <strong>${esc(row.avg == null || row.avg === "" ? "—" : t("stats.avg", { n: row.avg }))}</strong>
            <span class="muted">${esc(t("stats.total", { n: row.total }))}</span>
          </div>`
        )
        .join("")
    : "";
  const modRows = mods.length
    ? `<div class="stat-head">${esc(t("stats.mods"))}</div>` +
      mods
        .map(
          (row) => `<div class="stat-row">
            <span class="grow">${esc(row.name)}</span>
            <strong>${esc(row.pct == null || row.pct === "" ? "—" : t("stats.mod_pct", { n: row.pct }))}</strong>
            <span class="muted">${esc(t("stats.mod_total", { n: row.total }))}</span>
          </div>`
        )
        .join("")
    : "";
  const rows = currencyRows || modRows ? `${currencyRows}${modRows}` : `<p class="muted">${esc(t("stats.empty"))}</p>`;
  view.innerHTML = page({
    title: t("stats.title"),
    tip: t("stats.hint"),
    back: backBtn(t("nav.back")),
    fill: true,
    body: `<div class="split">
      <div class="list">
        <button class="pick ${selected ? "" : "on"}" data-sid="all"><strong>${esc(t("stats.all"))}</strong><span>${esc(t("stats.summary", { crafts: data.crafts || 0, sessions: data.sessions || 0 }))}</span></button>
        ${scenarios
          .map(
            (row) =>
              `<button class="pick ${row.id === state.statsFilter ? "on" : ""}" data-sid="${esc(row.id)}"><strong>${esc(row.name)}</strong><span>${esc(t("stats.summary", { crafts: row.crafts, sessions: row.sessions }))}</span></button>`
          )
          .join("")}
      </div>
      <div class="card">
        <div class="muted" style="margin-bottom:10px">${esc(t("stats.summary", { crafts, sessions }))}</div>
        <div class="stat-list">${rows}</div>
      </div>
    </div>`,
  });
  view.onclick = (ev) => {
    if (ev.target.closest("[data-home]")) return go("home");
    const pick = ev.target.closest("[data-sid]");
    if (!pick) return;
    state.statsFilter = pick.dataset.sid === "all" ? "all" : pick.dataset.sid;
    paintStats(view, data);
  };
}

function paintHeist(view, data) {
  paintJob(view, {
    title: t("heist.title"),
    hint: t("heist.hint"),
    data,
    start: "heist_start",
    stop: "heist_stop",
    save: "heist_save",
    preset: "heist_preset",
    hotkey: "heist_hotkey",
    map: "heist_map",
    extra: `
      <div class="section"><div class="section-head"><h3>${esc(t("heist.points"))}</h3>${help(t("heist.points_hint"))}</div>
        <div class="card">
          <div class="row"><span class="grow muted">${esc(t("heist.confirm_point"))}: ${esc(data.confirm)}</span>
            <button class="btn primary" data-map="confirm">${esc(t("settings.set_overlay"))}</button></div>
          <div class="row" style="margin-top:8px"><span class="grow muted">${esc(t("heist.bp_point"))}: ${esc(data.blueprint)}</span>
            <button class="btn primary" data-map="blueprint">${esc(t("settings.set_overlay"))}</button></div>
          <button class="btn" data-clear style="margin-top:10px">${esc(t("heist.clear_points"))}</button>
        </div>
      </div>
      <div class="section"><div class="section-head"><h3>${esc(t("heist.inventory_region"))}</h3>${help(t("heist.inventory_hint"))}</div>
        <div class="card">
          <div class="row"><span class="grow muted">${esc(data.inventory)}</span>
          <button class="btn primary" data-map="inventory">${esc(t("settings.set_overlay"))}</button></div>
        </div>
      </div>`,
    hotHint: t("heist.hotkeys_hint"),
  });
}

function paintReveal(view, data) {
  paintJob(view, {
    title: t("reveal.title"),
    hint: t("reveal.hint"),
    data,
    start: "reveal_start",
    stop: "reveal_stop",
    save: "reveal_save",
    preset: "reveal_preset",
    hotkey: "reveal_hotkey",
    map: "reveal_map",
    extra: `
      <div class="section"><div class="section-head"><h3>${esc(t("reveal.map"))}</h3>${help(t("reveal.map_hint"))}</div>
        <div class="card">
          <div class="row"><span class="grow muted">${esc(t("reveal.map"))}: ${esc(data.map)}</span>
            <button class="btn primary" data-map="map">${esc(t("settings.set_overlay"))}</button></div>
          <div class="row" style="margin-top:8px"><span class="grow muted">${esc(t("reveal.slot"))}: ${esc(data.slot)}</span>
            <button class="btn primary" data-map="slot">${esc(t("settings.set_overlay"))}</button></div>
        </div>
      </div>
      <div class="section"><div class="section-head"><h3>${esc(t("heist.inventory_region"))}</h3>${help(t("reveal.inventory_hint"))}</div>
        <div class="card">
          <div class="row"><span class="grow muted">${esc(data.inventory)}</span>
          <button class="btn primary" data-map="inventory">${esc(t("settings.set_overlay"))}</button></div>
        </div>
      </div>`,
    hotHint: t("reveal.hotkeys_hint"),
  });
}

function paintJob(view, opt) {
  const data = opt.data;
  view.innerHTML = page({
    title: opt.title,
    tip: opt.hint,
    back: backBtn(t("nav.back")),
    actions: `
      <span class="muted">${esc(data.status || "")}</span>
      <button class="btn primary" data-start ${data.running ? "disabled" : ""}>${esc(t("heist.start"))}</button>
      <button class="btn danger" data-stop ${data.running ? "" : "disabled"}>${esc(t("heist.stop"))}</button>`,
    body: `
    ${opt.extra || ""}
    <div class="section"><div class="section-head"><h3>${esc(t("heist.speed"))}</h3></div>
      <div class="card">
        <div class="row" style="margin-bottom:10px">
          <button class="btn" data-preset="slow">${esc(t("heist.slow"))}</button>
          <button class="btn" data-preset="normal">${esc(t("heist.normal"))}</button>
          <button class="btn" data-preset="fast">${esc(t("heist.fast"))}</button>
        </div>
        <div class="grid2">${(data.speeds || [])
          .map(
            (row) =>
              `<label class="row"><span class="muted grow">${esc(row.label)}</span>
              <input class="field" style="width:80px" data-speed="${esc(row.key)}" value="${esc(row.value)}"></label>`
          )
          .join("")}</div>
      </div>
    </div>
    <div class="section"><div class="section-head"><h3>${esc(t("heist.log"))}</h3></div>
      <pre class="log" id="job-log">${esc((data.log || []).join("\n"))}</pre>
    </div>`,
  });
  const persist = debounce(async () => {
    const patch = {};
    $$("[data-speed]", view).forEach((input) => (patch[input.dataset.speed] = input.value));
    await call(opt.save, patch);
  }, 250);
  view.oninput = (ev) => {
    if (ev.target.matches("[data-speed]")) persist();
  };
  view.onclick = async (ev) => {
    if (ev.target.closest("[data-home]")) {
      const patch = {};
      $$("[data-speed]", view).forEach((input) => (patch[input.dataset.speed] = input.value));
      await call(opt.save, patch);
      return go("home");
    }
    if (ev.target.closest("[data-start]")) {
      const patch = {};
      $$("[data-speed]", view).forEach((input) => (patch[input.dataset.speed] = input.value));
      await call(opt.save, patch);
      return render(await call(opt.start));
    }
    if (ev.target.closest("[data-stop]")) return render(await call(opt.stop));
    const preset = ev.target.closest("[data-preset]");
    if (preset) return render(await call(opt.preset, preset.dataset.preset));
    const map = ev.target.closest("[data-map]");
    if (map) return call(opt.map, map.dataset.map);
    if (ev.target.closest("[data-clear]")) return render(await call("heist_clear_points"));
    const clear = ev.target.closest("[data-hotkey-clear]");
    if (clear) {
      if (clear.disabled) return;
      cancelHotkeyCapture();
      return render(await call(opt.hotkey, clear.dataset.hotkeyClear, ""));
    }
    const key = ev.target.closest("[data-hotkey]");
    if (key) {
      beginHotkeyCapture(opt.hotkey, key.dataset.hotkey, key);
    }
  };
}

function beginHotkeyCapture(kind, target, button) {
  if (state.capturing && state.capturing.button === button) {
    cancelHotkeyCapture();
    return;
  }
  cancelHotkeyCapture();
  state.capturing = { kind, target, button, previous: button.textContent };
  button.textContent = t("settings.press_key");
}

function cancelHotkeyCapture() {
  const cap = state.capturing;
  if (!cap) return;
  if (cap.button) cap.button.textContent = cap.previous || t("settings.hotkey_none");
  state.capturing = null;
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function appendLog(sel, line) {
  const box = $(sel);
  if (!box) return;
  box.textContent = box.textContent ? `${box.textContent}\n${line}` : line;
  box.scrollTop = box.scrollHeight;
}

window.app = {
  async onEvent(event) {
    if (!event) return;
    if (event.kind === "toast") toast(event.payload.message, event.payload.kind, event.payload.ms);
    if (event.kind === "status") applyShell(event.payload);
    if (event.kind === "screen") render(event.payload);
    if (event.kind === "craft_log" && state.screen === "run") {
      state.runLines.push(event.payload.line);
      const box = $("#run-log");
      const stick = Boolean(box && box.scrollHeight - box.scrollTop - box.clientHeight < 48 && !state.runQuery.trim());
      renderRunLog(stick);
      const status = $("#run-status");
      if (status) status.textContent = event.payload.status || event.payload.line;
    }
    if (event.kind === "job_log") {
      if (event.payload.job === "heist" && state.screen === "heist") appendLog("#job-log", event.payload.line);
      if (event.payload.job === "reveal" && state.screen === "reveal") appendLog("#job-log", event.payload.line);
    }
    if (event.kind === "heist_running" && state.screen === "heist") {
      const data = await call("boot");
      render(data);
    }
    if (event.kind === "reveal_running" && state.screen === "reveal") {
      const data = await call("boot");
      render(data);
    }
  },
};

function keyName(ev) {
  if (ev.key.startsWith("F") && /^F\d{1,2}$/.test(ev.key)) return ev.key.toUpperCase();
  if (ev.key.length === 1) return ev.key.toUpperCase();
  const map = { Escape: "ESCAPE", " ": "SPACE", Enter: "RETURN", Tab: "TAB", Backspace: "BACKSPACE" };
  return map[ev.key] || ev.key.toUpperCase();
}

function keyChord(ev) {
  const key = keyName(ev);
  if (!key || ["SHIFT", "CONTROL", "CTRL", "ALT", "META", "WIN"].includes(key)) return "";
  const parts = [];
  if (ev.ctrlKey) parts.push("CTRL");
  if (ev.altKey) parts.push("ALT");
  if (ev.shiftKey) parts.push("SHIFT");
  if (ev.metaKey) parts.push("WIN");
  parts.push(key);
  return parts.join("+");
}

document.addEventListener("keydown", async (ev) => {
  if (ev.key === "Escape" && !state.capturing) closeCombos();
  const search = document.activeElement;
  const inLogSearch = search && (search.id === "log-search" || search.id === "run-search");
  if (inLogSearch && (ev.key === "Enter" || ev.key === "F3")) {
    ev.preventDefault();
    if (search.id === "run-search") jumpHits("#run-log", "runHit", ev.shiftKey ? -1 : 1);
    else jumpLog(ev.shiftKey ? -1 : 1);
  }
  if (!state.capturing) return;
  if (["Shift", "Control", "Alt", "Meta"].includes(ev.key)) return;
  ev.preventDefault();
  if (ev.key === "Escape") {
    cancelHotkeyCapture();
    return;
  }
  const chord = keyChord(ev);
  if (!chord) return;
  const cap = state.capturing;
  state.capturing = null;
  if (cap.kind === "settings") render(await call("settings_hotkey", cap.target, chord));
  else render(await call(cap.kind, cap.target, chord));
});

document.addEventListener("click", (ev) => {
  if (ev.target.closest(".combo") || ev.target.closest(".combo-pop")) return;
  closeCombos();
});

let booted = false;

async function boot() {
  if (booted) return;
  booted = true;
  $("#brand").onclick = () => go("home");
  $("#lang-btn").onclick = (ev) => {
    ev.stopPropagation();
    const pop = $("#lang-pop");
    const open = pop.hidden;
    closeCombos();
    pop.hidden = !open;
    $("#lang-btn").setAttribute("aria-expanded", String(open));
  };
  $("#lang-pop").onclick = async (ev) => {
    const btn = ev.target.closest("[data-lang]");
    if (!btn) return;
    closeCombos();
    render(await call("set_language", btn.dataset.lang));
  };
  render(await call("boot"));
}

window.addEventListener("pywebviewready", boot);
if (window.pywebview?.api) boot();
