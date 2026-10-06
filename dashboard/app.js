const DATA = "data/";
const STATUS = {
  success: ["ok", "완료"],
  qa_failed: ["warn", "QA 불합격"],
  failed: ["bad", "실패"],
  running: ["info", "진행 중"],
};
const UPLOAD = {
  uploaded: ["ok", "업로드됨"],
  skipped: ["mute", "업로드 안 함"],
};
const SCORE_LABELS = { hook: "훅", fun: "재미", clarity: "명확성", visual: "비주얼", subtitle: "자막", safety: "안전" };
const TARGET_LABELS = { planner: "기획자", producer: "제작자", effector: "이펙터" };

const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pill = (map, key, fallback = "mute") => {
  const [cls, label] = map[key] || [fallback, key || "-"];
  return `<span class="pill ${cls}">${esc(label)}</span>`;
};
const scoreColor = (v) => (v >= 75 ? "var(--ok)" : v >= 60 ? "var(--warn)" : "var(--bad)");
const fmtSecs = (s) => (s == null ? "" : s >= 60 ? `${Math.floor(s / 60)}분 ${Math.round(s % 60)}초` : `${s}초`);
const safeUrl = (u) => (/^https:\/\//.test(u || "") ? u : null);

async function getJSON(path) {
  const res = await fetch(DATA + path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function renderStats(index) {
  const total = index.length;
  const ok = index.filter((r) => r.status === "success").length;
  const uploaded = index.filter((r) => r.upload_status === "uploaded").length;
  const scores = index.map((r) => r.overall).filter((v) => typeof v === "number");
  const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : "-";
  const last = index[0];
  $("#stats").innerHTML = [
    ["최근 실행", last ? `${last.date.slice(5)} ${STATUS[last.status]?.[1] ?? ""}` : "-"],
    ["총 실행", total],
    ["성공률", total ? `${Math.round((ok / total) * 100)}%` : "-"],
    ["업로드", uploaded],
    ["평균 QA", avg],
  ].map(([k, v]) => `<div class="stat"><b>${esc(v)}</b><span>${esc(k)}</span></div>`).join("");
}

function renderList(index, current) {
  $("#run-list").innerHTML = index.map((r) => `
    <li><button class="run-item" data-date="${esc(r.date)}" aria-current="${r.date === current}">
      ${r.thumbnail ? `<img src="${DATA + esc(r.thumbnail)}" alt="" loading="lazy">` : `<div class="noimg"></div>`}
      <span class="meta">
        <span class="date">${esc(r.date)}${r.duration ? ` · ${Math.round(r.duration)}초` : ""}</span>
        <span class="title">${esc(r.title || "(제목 없음)")}</span>
        <span class="row">${pill(STATUS, r.status)}${typeof r.overall === "number" ? `<span class="pill mute">QA ${r.overall}</span>` : ""}</span>
      </span>
    </button></li>`).join("");
}

function heroCard(run) {
  const plan = run.plan || {};
  const up = run.upload || {};
  const yt = safeUrl(up.url);
  const eff = run.effects || {};
  const imgs = run.production?.image_providers || {};
  const poster = run.thumbnail ? DATA + run.thumbnail : "";
  const video = run.video_file
    ? `<video controls playsinline preload="metadata" poster="${esc(poster)}" src="${esc(run.video_file)}"></video>`
    : poster ? `<img src="${esc(poster)}" alt="썸네일">` : "";
  return `<article class="card hero">
    <div class="player">${video}</div>
    <div class="hero-info">
      <div class="row">${pill(STATUS, run.status)}${pill(UPLOAD, up.status)}${up.privacy ? `<span class="pill mute">${esc(up.privacy)}</span>` : ""}</div>
      <h2>${esc(plan.title || "(기획 전 단계에서 중단)")}</h2>
      ${plan.hook ? `<p class="muted">훅: “${esc(plan.hook)}”</p>` : ""}
      <dl class="kv">
        <dt>날짜</dt><dd>${esc(run.date)}</dd>
        <dt>길이</dt><dd>${eff.duration ? `${eff.duration}초` : "-"}</dd>
        <dt>LLM</dt><dd>${esc(run.llm_provider)}</dd>
        <dt>이미지</dt><dd>${esc(Object.entries(imgs).map(([k, v]) => `${k} ${v}장`).join(", ") || "-")}</dd>
        <dt>음성</dt><dd>${esc([eff.tts_provider, eff.voice].filter(Boolean).join(" · ") || "-")}</dd>
        <dt>BGM</dt><dd>${esc(eff.bgm || "없음")}</dd>
        ${up.reason ? `<dt>업로드</dt><dd>${esc(up.reason)}</dd>` : ""}
        ${plan.reason ? `<dt>선정 이유</dt><dd>${esc(plan.reason)}</dd>` : ""}
      </dl>
      <div class="row">
        ${yt ? `<a class="btn" href="${esc(yt)}" target="_blank" rel="noopener">YouTube에서 보기</a>` : ""}
        ${run.video_file ? `<a class="btn ghost" href="${esc(run.video_file)}" download>MP4 다운로드</a>` : ""}
      </div>
    </div>
  </article>`;
}

function timelineCard(run) {
  const icon = { done: "✓", failed: "✕", running: "…" };
  const items = (run.stages || []).map((s) => `
    <li>
      <span class="dot ${esc(s.status)}">${icon[s.status] || ""}</span>
      <div><div class="label">${esc(s.label)}</div>
        ${s.note ? `<div class="note">${esc(s.note)}</div>` : ""}
        ${s.error ? `<div class="err">${esc(s.error)}</div>` : ""}</div>
      <span class="secs">${esc(fmtSecs(s.seconds))}</span>
    </li>`).join("");
  const err = run.error ? `<p class="err" style="color:var(--bad)">${esc(run.error)}</p>
    ${run.traceback ? `<details><summary class="muted">스택 트레이스</summary><pre class="trace">${esc(run.traceback)}</pre></details>` : ""}` : "";
  return `<article class="card"><h2>에이전트 진행</h2><ul class="timeline">${items}</ul>${err}</article>`;
}

function marketerCard(run) {
  const m = run.marketer;
  if (!m) return "";
  const chosen = run.plan?.chosen_rank;
  const risk = { low: ["ok", "낮음"], medium: ["warn", "중간"], high: ["bad", "높음"] };
  const rows = (m.topics || []).map((t) => `
    <tr class="${t.rank === chosen ? "chosen" : ""}">
      <td class="num">${esc(t.rank)}</td>
      <td><b>${esc(t.topic)}</b><div class="muted">${esc(t.angle || "")}</div></td>
      <td>${esc(t.keyword)}</td>
      <td class="num">${esc(t.traffic)}</td>
      <td class="num">${esc(t.fun_score)}</td>
      <td>${pill(risk, t.risk)}</td>
    </tr>`).join("");
  const excluded = (m.excluded || []).map((e) => `${esc(e.keyword)} <span class="muted">(${esc(e.blocked_by)})</span>`).join(", ");
  return `<article class="card">
    <h2>마케터 보고서 · 주제 ${m.topics?.length ?? 0}개</h2>
    <p class="muted" style="margin-bottom:10px">${esc(m.summary || "")} · 트렌드 ${esc(m.trend_count)}건 수집</p>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>주제</th><th>키워드</th><th>검색량</th><th>재미</th><th>리스크</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    ${excluded ? `<p class="muted" style="margin-top:10px">안전 필터로 제외: ${excluded}</p>` : ""}
  </article>`;
}

function storyboardCard(run) {
  const board = run.storyboard || [];
  if (!board.length) return "";
  const plan = run.plan || {};
  return `<article class="card">
    <h2>기획 · 스토리보드</h2>
    <div class="board">${board.map((s) => `
      <figure class="scene" style="margin:0">
        <img src="${DATA + esc(s.image)}" alt="장면 ${esc(s.id)}" loading="lazy">
        <span class="ost">${esc(s.id)}. ${esc(s.on_screen_text || "")}</span>
        <p>${esc(s.narration)}</p>
      </figure>`).join("")}</div>
    ${plan.description ? `<p class="muted" style="margin-top:12px;white-space:pre-line">${esc(plan.description)}</p>` : ""}
    ${plan.tags?.length ? `<div class="row" style="margin-top:8px">${plan.tags.map((t) => `<span class="pill mute">#${esc(t)}</span>`).join("")}</div>` : ""}
  </article>`;
}

function qaCard(run) {
  const attempts = run.qa || [];
  if (!attempts.length) return "";
  return `<article class="card"><h2>QA 검증 (${attempts.length}회)</h2><div class="qa-grid">${attempts.map((q) => `
    <section class="qa">
      <div class="qa-head">
        <h3>${esc(q.attempt)}차 검수</h3>
        <span class="row">${q.pass ? `<span class="pill ok">합격</span>` : `<span class="pill bad">불합격</span>`}
          <span class="score-big" style="color:${scoreColor(q.overall)}">${esc(q.overall)}</span></span>
      </div>
      ${Object.entries(SCORE_LABELS).map(([k, label]) => {
        const v = q.scores?.[k] ?? 0;
        return `<div class="bar"><span>${label}</span><span class="track"><span class="fill" style="display:block;width:${Math.max(0, Math.min(100, v))}%;background:${scoreColor(v)}"></span></span><span class="v">${esc(v)}</span></div>`;
      }).join("")}
      ${q.issues?.length ? `<ul>${q.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : ""}
      ${q.feedback ? `<p class="fb">${!q.pass && q.retry_target ? `<b>→ ${esc(TARGET_LABELS[q.retry_target] || q.retry_target)}</b> ` : ""}${esc(q.feedback)}</p>` : ""}
    </section>`).join("")}</div></article>`;
}

async function showRun(date) {
  document.querySelectorAll(".run-item").forEach((b) => b.setAttribute("aria-current", String(b.dataset.date === date)));
  $("#detail").innerHTML = `<p class="muted">불러오는 중…</p>`;
  try {
    const run = await getJSON(`runs/${date}.json`);
    $("#detail").innerHTML = heroCard(run) + timelineCard(run) + qaCard(run) + storyboardCard(run) + marketerCard(run);
    // 영상 파일이 없으면(보관 기간 지남 등) 썸네일로 대체
    const video = $("#detail video");
    video?.addEventListener("error", () => {
      const img = document.createElement("img");
      img.src = video.poster;
      img.alt = "썸네일";
      video.replaceWith(img);
    });
  } catch (e) {
    $("#detail").innerHTML = `<div class="card empty"><p class="muted">${esc(e.message)}</p></div>`;
  }
}

async function main() {
  let index = [];
  try {
    index = await getJSON("index.json");
  } catch {
    /* 아직 실행 기록 없음 */
  }
  renderStats(index);
  if (!index.length) {
    $("#detail").innerHTML = `<div class="card empty"><h2>아직 실행 기록이 없습니다</h2>
      <p class="muted">GitHub Actions의 daily-shorts 워크플로를 실행하면 여기에 결과가 표시됩니다.</p></div>`;
    return;
  }
  const current = decodeURIComponent(location.hash.slice(1)) || index[0].date;
  renderList(index, current);
  $("#run-list").addEventListener("click", (e) => {
    const btn = e.target.closest(".run-item");
    if (btn) location.hash = btn.dataset.date;
  });
  window.addEventListener("hashchange", () => showRun(decodeURIComponent(location.hash.slice(1))));
  showRun(current);
}

main();
