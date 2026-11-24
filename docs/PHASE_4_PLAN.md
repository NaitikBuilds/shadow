# SHADOW — Phase 4 Master Implementation Plan
**Version:** 1.0  
**Target Release:** v0.4.0-vision-modes  
**Source Specification:** PRD Version 3.6 (Section 22)

---

## 1. Executive Summary & Goals

Phase 4 (**Advanced Proactive + Vision Modes**) delivers complete **Level 4 Proactive Intelligence** and local-only background vision for SHADOW. It bridges passive/observant memory with anticipatory, cross-project, and visual intelligence — while maintaining strict local privacy and user agency.

### Key Goals:
- **Zero Memory Pollution:** Shadow Cloning allows what-if exploration in isolated ephemeral sessions without polluting primary memory.
- **Ethical Alignment:** Ethical Mirror captures user values and provides advisory reflections during decision points.
- **Synthesized Intelligence:** Cross-Project Insight Weaver and Silent Pair Partner surface non-obvious connections and contextual assistance.
- **Meeting Intelligence:** Local Whisper-based post-meeting transcription, prep notes, and evidence-grounded summaries.
- **Review Surfaces:** Daily Digest, Weekly Review, Notification Summarization, Timeline View, and Entity Browser.
- **Local Background Vision:** 10-minute Auto-Summary and 1/3/5-minute Continuous background vision using local VLMs (Florence-2 / Moondream2) with mandatory purple indicators.

### Hard Privacy & Security Boundaries:
- **No Cloud Background Execution:** Continuous vision, Auto-Summary vision, and background ASR MUST run 100% locally on-device.
- **Read-Only / Advisory:** No autonomous desktop actions or Action Registry execution in Phase 4.
- **Fail-Closed Consent:** All background sensing requires explicit user consent and respects Do Not Disturb (DND) / Focus Shield.

---

## 2. Milestone Overview & Implementation Status

Phase 4 spans **38 commits (C01–C38)** across **10 Milestones (M1–M10)**.

```
M1: Foundations (C01–C06)             [COMPLETED ✅]
M2: Ethical Mirror (C07–C09)           [COMPLETED ✅]
M3: Shadow Cloning (C10–C12)           [COMPLETED ✅]
---------------------------- CURRENT POINT ----------------------------
M4: Cross-Project Weaver (C13–C15)     [PLANNED ⏳]
M5: Silent Pair Partner (C16–C18)      [PLANNED ⏳]
M6: Meeting Intelligence (C19–C23)     [PLANNED ⏳]
M7: Digests & Notifications (C24–C27)  [PLANNED ⏳]
M8: Review UIs (C28–C29)               [PLANNED ⏳]
M9: Local Background Vision (C30–C35)  [PLANNED ⏳]
M10: Hardening & Release (C36–C38)     [PLANNED ⏳]
```

---

## 3. Completed Work (Commits C01–C12 / Milestones M1–M3)

### Milestone 1: Phase 4 Foundations (C01–C06) — COMPLETED ✅
- **C01 (`0a98873`)**: Repository baseline and architecture audit.
- **C02 (`668f2ab`)**: Privacy test harness and zero-cost vision spy fixtures (`tests/test_phase4_spies.py`).
- **C03 (`9360789`)**: Phase 4 consent gate and channel registration (`src/shadow/security/consent_gate.py`).
- **C04 (`63578ae`)**: Phase 4 configuration registry with schema validation (`src/shadow/config/phase4_config.py`).
- **C05 / C05b (`496a4ec`, `d69384b`)**: Shared `BackgroundTaskRegistry` task registration and application lifecycle wiring in `main.py`.
- **C06 (`a181394`, `b59a0b8`, `5689da1`, `3af89ca`)**: Migration `007_phase4_schema.sql`, database wipe harness, retention registry, and G1 VLM benchmark scaffold.

### Milestone 2: Ethical Mirror (C07–C09) — COMPLETED ✅
- **C07 (`cf63120`)**: User values store with CRUD, history, and wipe (`src/shadow/memory/ethical_store.py`).
- **C08 (`bae003b`)**: 10-prompt onboarding wizard and settings panel in PySide6 (`src/shadow/ui/ethical_mirror_dialog.py`).
- **C09 / C09b / C09c (`da1b4b1`, `16192c2`, `75cace0`)**: Advisory reflection generator, 2-step prompt decomposition for small models, and two-layer cloud opt-in.

### Milestone 3: Shadow Cloning (C10–C12) — COMPLETED ✅
- **C10 (`a89e806`)**: Clone session registry, ephemeral SQLite store, and read-only memory facade (`src/shadow/agent/clone_registry.py`).
- **C11 / C11b (`732e957`, `0b0b552`)**: Clone list, create, chat UI, simulation labeling, and SHADOW self-window observation exclusion filter.
- **C12 (`e3f20a9`)**: Promotion engine with duplicate rejection, session discard, and stale crash recovery (`src/shadow/agent/clone_promote.py`).

---

## 4. Remaining Work Roadmap (Commits C13–C38 / Milestones M4–M10)

### Milestone 4: Cross-Project Insight Weaver (C13–C15)

#### **Commit C13: Weaver Candidate Generation & Exclusions**
- **Type / Message:** `feat(weaver): eligibility, exclusions and candidate generation`
- **Requirements:** `FR-P4-WVR-03`, `FR-P4-WVR-05`, `FR-P4-WVR-08`
- **Objective:** Scan knowledge graph entities across distinct project boundaries to find semantic overlap (vector similarity ≥ 0.78). Apply exclusions for password managers, banking, and private projects.
- **Target Files:**
  - `src/shadow/proactive/weaver_engine.py`
  - `tests/test_weaver_engine.py`

#### **Commit C14: Weaver Provenance, Deduplication & Persistence**
- **Type / Message:** `feat(weaver): provenance, dedupe, staleness, persistence`
- **Requirements:** `FR-P4-WVR-01`, `FR-P4-WVR-02`, `FR-P4-WVR-06`, `FR-P4-WVR-07`
- **Objective:** Attach clear source provenance to every generated insight (citing project A and project B source items). Filter out duplicate or stale insights. Store in `weaver_insights` table.
- **Target Files:**
  - `src/shadow/proactive/weaver_store.py`
  - `tests/test_weaver_store.py`

#### **Commit C15: Weaver Insights UI & Feedback Loop**
- **Type / Message:** `feat(weaver): insights UI and feedback`
- **Requirements:** `FR-P4-WVR-04`, `FR-P4-WVR-06`
- **Objective:** Render Weaver insights cards in the proactive side panel with provenance links and explicit feedback actions (Helpful / Dismiss / Never link these projects).
- **Target Files:**
  - `src/shadow/ui/weaver_panel.py`
  - `tests/test_weaver_panel.py`

---

### Milestone 5: Silent Pair Partner (C16–C18)

#### **Commit C16: Context Selection & Gate Checks**
- **Type / Message:** `feat(pair): context selection and consent/exclusion gates`
- **Requirements:** `FR-P4-SPP-04`
- **Objective:** Detect when user is stuck on a document/editor using UIA snapshot and typing pause analysis. Verify `silent_pair` consent channel and Focus Shield state.
- **Target Files:**
  - `src/shadow/proactive/silent_pair.py`
  - `tests/test_silent_pair_gates.py`

#### **Commit C17: Silent Pair PromptBuilder & Ranking**
- **Type / Message:** `feat(pair): PromptBuilder integration and ranking`
- **Requirements:** `FR-P4-SPP-03`, `FR-P4-SPP-05`
- **Objective:** Construct guarded prompts with `PromptBuilder` retrieving related past solutions or code snippets from memory. Rank candidates by relevance score.
- **Target Files:**
  - `src/shadow/proactive/silent_pair_prompts.py`
  - `tests/test_silent_pair_prompts.py`

#### **Commit C18: Silent Pair UI Cards & Rate Limiting**
- **Type / Message:** `feat(pair): suppression, rate limits and cards`
- **Requirements:** `FR-P4-SPP-01`, `FR-P4-SPP-02`, `FR-P4-SPP-05`, `FR-P4-SPP-06`, `FR-P4-SPP-07`, `FR-P4-SPP-08`
- **Objective:** Display non-intrusive suggestion cards. Implement exponential cooldown on dismissal (max 1 suggestion per 30 minutes unless explicit user request).
- **Target Files:**
  - `src/shadow/ui/silent_pair_card.py`
  - `tests/test_silent_pair_ui.py`

---

### Milestone 6: Meeting Intelligence & ASR (C19–C23)

#### **Commit C19: Meeting Entity & Audio File Import**
- **Type / Message:** `feat(meetings): meetings entity, recording import and validation`
- **Requirements:** `FR-P4-ASR-01`, `FR-P4-ASR-04`, `FR-P4-ASR-05`
- **Objective:** Support post-meeting audio file import (.wav, .mp3, .m4a). Validate audio duration and format under `meeting_audio` consent. Store metadata in `meetings` table.
- **Target Files:**
  - `src/shadow/perception/meeting_importer.py`
  - `tests/test_meeting_importer.py`

#### **Commit C20: Local Whisper Transcription Pipeline**
- **Type / Message:** `feat(asr): local Whisper tiny.en transcription pipeline`
- **Requirements:** `FR-P4-ASR-01`, `FR-P4-ASR-02`, `FR-P4-ASR-06`, `FR-P4-ASR-07`, `FR-P4-ASR-08`, `NFR-P4-06`
- **Objective:** Run post-meeting speech-to-text using local Whisper `tiny.en` via ONNX or `whisper.cpp`. Format output into timestamped transcript segments.
- **Target Files:**
  - `src/shadow/models/whisper_asr.py`
  - `tests/test_whisper_asr.py`

#### **Commit C21: Meeting Prep Generation**
- **Type / Message:** `feat(meetings): Meeting Prep with explicit gaps`
- **Requirements:** `FR-P4-MPR-01` through `FR-P4-MPR-07`
- **Objective:** Before an upcoming calendar meeting, aggregate recent memory, open threads, and past interactions with attendees. Surface explicit context gaps if memory is partial.
- **Target Files:**
  - `src/shadow/proactive/meeting_prep.py`
  - `tests/test_meeting_prep.py`

#### **Commit C22: Post-Meeting Summary with Evidence Validation**
- **Type / Message:** `feat(meetings): Post-Meeting Summary with evidence validation`
- **Requirements:** `FR-P4-PMS-01` through `FR-P4-PMS-07`
- **Objective:** Generate concise meeting summaries, key decisions, and action items grounded strictly in transcript evidence (no hallucinated assignees or auto-sending emails).
- **Target Files:**
  - `src/shadow/proactive/meeting_summary.py`
  - `tests/test_meeting_summary.py`

#### **Commit C23: Meeting Deletion Cascade & Retention**
- **Type / Message:** `feat(meetings): deletion cascade and retention`
- **Requirements:** `FR-P4-ASR-03`, `FR-P4-MPR-07`, `FR-P4-PMS-06`
- **Objective:** Support full deletion of meeting recordings, transcripts, prep notes, and summaries in a single atomic cascade transaction.
- **Target Files:**
  - `src/shadow/memory/meeting_store.py`
  - `tests/test_meeting_store.py`

---

### Milestone 7: Digests & Notification Summarization (C24–C27)

#### **Commit C24: Daily Digest Pipeline**
- **Type / Message:** `feat(digest): Daily Digest on-demand and optional schedule`
- **Requirements:** `FR-P4-DIG-01` through `FR-P4-DIG-07`
- **Objective:** Synthesize daily activity, completed tasks, key topics, and unresolved threads into a calm, structured daily overview. Support manual refresh or optional time trigger.
- **Target Files:**
  - `src/shadow/proactive/daily_digest.py`
  - `tests/test_daily_digest.py`

#### **Commit C25: Weekly Review Retrospective**
- **Type / Message:** `feat(digest): Weekly Review retrospective`
- **Requirements:** `FR-P4-WRV-01` through `FR-P4-WRV-06`
- **Objective:** Aggregate daily digests into a weekly retrospective highlight reel, highlighting long-term progress, focus distribution, and project momentum.
- **Target Files:**
  - `src/shadow/proactive/weekly_review.py`
  - `tests/test_weekly_review.py`

#### **Commit C26: Notification API Feasibility Spike**
- **Type / Message:** `docs(notify): OS notification API feasibility spike`
- **Requirements:** `FR-P4-NTF-04`
- **Objective:** Document Windows WinRT / Notification listener API feasibility, limitations, and security boundaries (`docs/design/phase4_g2_notification_spike.md`).
- **Target Files:**
  - `docs/design/phase4_g2_notification_spike.md`

#### **Commit C27: Opt-In Notification Summarization Pipeline**
- **Type / Message:** `feat(notify): opt-in notification summarization pipeline`
- **Requirements:** `FR-P4-NTF-01` through `FR-P4-NTF-07`
- **Objective:** Capture incoming OS notifications under `notification_access` consent. Filter sensitive apps (banking/passwords), deduplicate, and present batched summaries.
- **Target Files:**
  - `src/shadow/perception/notification_listener.py`
  - `tests/test_notifications.py`

---

### Milestone 8: Review UIs — Timeline & Entity Browser (C28–C29)

#### **Commit C28: Timeline View UI**
- **Type / Message:** `feat(timeline): Timeline view`
- **Requirements:** `FR-P4-TML-01` through `FR-P4-TML-06`
- **Objective:** Interactive PySide6 chronological timeline view showing past observations, sessions, meetings, and insights with time-scrubbing and search filtering.
- **Target Files:**
  - `src/shadow/ui/timeline_view.py`
  - `tests/test_timeline_view.py`

#### **Commit C29: Entity Browser UI**
- **Type / Message:** `feat(entities): Entity Browser`
- **Requirements:** `FR-P4-ENT-01` through `FR-P4-ENT-06`
- **Objective:** Interactive Knowledge Graph entity browser displaying projects, topics, documents, and people with provenance relationships.
- **Target Files:**
  - `src/shadow/ui/entity_browser.py`
  - `tests/test_entity_browser.py`

---

### Milestone 9: Local Background Vision (C30–C35)

#### **Commit C30: Background VLM Adapter & Model Selection**
- **Type / Message:** `feat(vision): background VLM adapter and selection`
- **Requirements:** `FR-P4-VAS-07`
- **Objective:** Lightweight background VLM adapter utilizing Florence-2-base ONNX or quantized Moondream2. Enforce strict local-only execution path.
- **Target Files:**
  - `src/shadow/models/background_vlm.py`
  - `tests/test_background_vlm.py`

#### **Commit C31: Auto-Summary Background Vision Mode**
- **Type / Message:** `feat(vision): Auto-Summary background mode`
- **Requirements:** `FR-P4-VAS-01` through `FR-P4-VAS-07`
- **Objective:** Run background screen captioning every 10 minutes when active. Store text captions into `observation_store`. Raw screenshots are NEVER saved to disk.
- **Target Files:**
  - `src/shadow/perception/auto_summary_vision.py`
  - `tests/test_auto_summary_vision.py`

#### **Commit C32: Continuous Vision Background Mode**
- **Type / Message:** `feat(vision): Continuous mode with cadence, cap, idle disable`
- **Requirements:** `FR-P4-VCN-01` through `FR-P4-VCN-09`
- **Objective:** High-cadence (1, 3, or 5 min) background screen observation. Pause on idle/battery saver. Hardcoded local-only backend. Mandate active purple system tray indicator.
- **Target Files:**
  - `src/shadow/perception/continuous_vision.py`
  - `tests/test_continuous_vision.py`

#### **Commit C33: Vision Settings UI with Truthful Status**
- **Type / Message:** `feat(ui): Vision Settings UI with truthful status`
- **Requirements:** `FR-P4-VUI-01` through `FR-P4-VUI-05`
- **Objective:** Dedicated Vision Settings tab exposing backend status, cadences, privacy exclusions, and truthful status (Local / Off).
- **Target Files:**
  - `src/shadow/ui/vision_settings_panel.py`
  - `tests/test_vision_settings_panel.py`

#### **Commit C34: Vision Revocation, Shutdown & Restart Hardening**
- **Type / Message:** `feat(vision): revocation, shutdown and restart hardening`
- **Requirements:** `FR-P4-VAS-06`, `FR-P4-VCN-08`, `FR-P4-SEC-05`
- **Objective:** Ensure revoking `vision` consent instantly cancels in-flight VLM tasks within < 200 ms and unloads background models from RAM.
- **Target Files:**
  - `src/shadow/perception/vision_lifecycle.py`
  - `tests/test_vision_lifecycle.py`

#### **Commit C35: Background Vision Privacy Regression Pack**
- **Type / Message:** `test(vision): background vision privacy regression pack`
- **Requirements:** `FR-P4-VAS-01`, `FR-P4-VCN-02`, `FR-P4-SEC-01`
- **Objective:** Automated regression suite asserting that zero background vision calls touch network stacks, sensitive windows are masked, and raw images are discarded.
- **Target Files:**
  - `tests/test_vision_privacy_pack.py`

---

### Milestone 10: Security, Privacy & Release Hardening (C36–C38)

#### **Commit C36: Security & Prompt Injection Test Suite**
- **Type / Message:** `test(security): injection, logging and phase-boundary security pack`
- **Requirements:** `FR-P4-SEC-06`, `FR-P4-SEC-07`, `FR-P4-SEC-09`, `FR-P4-SEC-10`, `FR-P4-SEC-11`
- **Objective:** Run 10+ prompt injection attack scenarios against PromptBuilder tags. Verify logs contain zero user data or plaintext secrets. Confirm Phase 4 cannot trigger Level 5 agent actions.
- **Target Files:**
  - `tests/test_phase4_security_pack.py`

#### **Commit C37: Wipe, Retention & Performance Validation**
- **Type / Message:** `test(p4): wipe, retention, integrity and performance validation`
- **Requirements:** `FR-P4-SEC-08`, `FR-P4-SEC-15`, `NFR-P4-01` through `NFR-P4-10`
- **Objective:** Validate that one-click Shadow wipe deletes all Phase 4 tables in < 5 seconds. Verify database retention policies and benchmark proactive response times (< 6s on CPU).
- **Target Files:**
  - `tests/test_phase4_performance_pack.py`

#### **Commit C38: Final Documentation & Release Validation**
- **Type / Message:** `docs(p4): documentation, acceptance review and release candidate validation`
- **Requirements:** Complete Phase 4 Exit Criteria
- **Objective:** Update system architecture diagrams, update `ROADMAP.md` and `DECISIONS.md`, compile release notes, and verify all 10 milestones pass for `v0.4.0-vision-modes`.
- **Target Files:**
  - `docs/PHASE_4_SUMMARY.md`
  - `docs/ROADMAP.md`

---

## 5. Verification & Testing Strategy

Every commit in Phase 4 requires strict verification before merging:

1. **Unit & Integration Tests:** Run `pytest` across all test suites (`1267+` tests passing).
2. **Network Isolation Enforcer:** Run `python scripts/check_network_isolation.py` to guarantee zero unauthorized outbound calls from background vision, ASR, or proactive engines.
3. **Privacy & Redaction Checks:** Verify credentials, passwords, and sensitive window titles are stripped before embedding or storing.
4. **Data Wipe Integrity:** Verify `MemoryManager.wipe_all()` clears all Phase 4 SQLite tables completely in < 5 seconds.

---

## 6. Execution Guidelines for AI Coding Agents

- **Human Review Required:** Every commit requires human review of the diff. Do NOT run automated `git commit` or `git tag` commands without explicit approval.
- **Preserve Existing Code:** Always maintain backwards compatibility with existing Phase 0–3.6 features and tests.
- **Keep Tests Green:** Ensure no regressions in existing test suites before declaring any commit complete.
