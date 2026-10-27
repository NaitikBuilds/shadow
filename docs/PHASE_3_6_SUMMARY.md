# Phase 3.6 — Vision Understanding

**Status:** Implementation complete; final verification pending
**Phase:** 3.6
**Focus:** Privacy-aware visual perception, image understanding, and region-based queries

---

## 1. Overview

Phase 3.6 extends SHADOW's perception system beyond text and structured UI information by introducing visual understanding.

The phase integrates local vision capabilities, supports image and screen-context queries, adds configurable cloud vision routing, and enables users to select a screen region and ask questions about it.

The implementation preserves SHADOW's local-first design through explicit consent, application exclusions, privacy checks, and user approval before cloud image uploads.

## 2. Major Features

### 2.1 Local Vision Understanding

* Integrates visual analysis through the vision service.
* Supports image-based queries using a prompt and image input.
* Provides a local vision path for supported visual tasks.
* Integrates vision with SHADOW's existing perception architecture.

### 2.2 Image Ingestion and Screen Context

* Supports image-file ingestion for visual understanding.
* Enables questions about the current screen.
* Combines visual context with relevant memory where supported.
* Adds intent routing for requests to describe or interpret visual content.

### 2.3 Cloud Vision and Routing

* Adds cloud vision support through the cloud backend.
* Supports configurable cloud providers and provider ordering.
* Uses vision routing to choose between cloud and local analysis.
* Supports local fallback when configured and available.
* Keeps vision routing separate from ordinary text-generation routing where required by the architecture.

### 2.4 Privacy and Consent

* Adds a vision indicator and first-use consent flow.
* Supports persistent per-application vision exclusions.
* Classifies windows before visual processing.
* Provides a per-window preview and approval flow before cloud uploads.
* Supports local-only analysis when the user chooses that option.
* Retains privacy checks for sensitive applications and SHADOW's own window.

### 2.5 Region Capture

* Adds a configurable region-capture feature.
* Uses a screen overlay to select a rectangular region.
* Provides a question prompt for the selected region.
* Captures and encodes the selected crop for visual analysis.
* Routes the query through the existing vision service or router.
* Displays the resulting answer in SHADOW's interface.
* Stores the question and answer as a text-only region observation rather than persisting the captured image.

## 3. Architecture

The implementation spans the following components:

* **Vision service:** Provides the visual-analysis interface.
* **Vision router:** Selects the appropriate vision-analysis path.
* **Cloud backend and provider pool:** Provide cloud-based visual understanding and provider fallback.
* **Screen vision:** Connects visual analysis with screen perception and window classification.
* **Region-analysis worker:** Runs region queries asynchronously.
* **Region overlay:** Provides the interactive selection interface.
* **Image observation store:** Records region questions and answers in memory.

The region-capture workflow uses window metadata for privacy checks and passes the selected image through the existing consent and cloud-approval path.

## 4. Testing

The repository includes tests for region-analysis worker behavior, routing options, invalid inputs, model responses, and text-only region-observation storage.

Additional vision tests cover relevant vision services, cloud behavior, routing, and privacy controls.

Final phase verification should record the actual results of:

* Region-analysis tests
* Vision-related tests
* Full test suite
* Ruff checks, where available
* Network-isolation checks, where applicable
* Manual region-capture testing in a separate application

No benchmark or accuracy figure should be reported unless it is supported by recorded test or benchmark output.

## 5. Privacy Guarantees and Limitations

The implementation is designed to avoid storing region screenshots as image files. Region observations retain textual question-and-answer information.

Cloud analysis requires the applicable consent and approval path. Local analysis remains available where supported and configured.

Privacy behavior still depends on correct window classification, exclusion configuration, and the active vision-routing configuration. Region capture should be tested against ordinary applications, SHADOW's own window, and sensitive or excluded applications.

## 6. Completion Criteria

Phase 3.6 can be considered fully verified when:

* Relevant vision and region-analysis tests pass.
* The full test suite has been reviewed.
* Cloud and local routing behave as configured.
* Consent and application-exclusion checks remain effective.
* Region capture works in an external application.
* SHADOW's own window and sensitive applications remain protected.
* Documentation matches the implementation.

## 7. Next Steps

With vision understanding in place, subsequent work can build on the new visual context capabilities. The next development phase should follow the current roadmap and should not be considered complete until its implementation and tests are verified.
