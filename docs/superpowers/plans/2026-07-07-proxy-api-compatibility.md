# Proxy API Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-layer proxy API compatibility system with automatic provider recognition, provider profiles, and generic fallback parsing.

**Architecture:** Keep `fetch_proxy_api` as the stable public entry point. Split request preparation, profile detection, success detection, and response extraction into focused helpers inside `util/proxy/ProxyApiProvider.py` unless the file becomes too large, then extract profile constants to a sibling module.

**Tech Stack:** Python 3.11, `requests`, `pytest`, existing `ProxyManager` normalized proxy strings.

## Global Constraints

- Preserve existing callers in `tab/config.py` and `task/buy.py`.
- Do not force all provider URLs into `count/format/protocol`.
- Keep sanitized demos only; never commit real tokens, app keys, or secrets.
- Every behavior change must have a focused pytest case.

---

### Task 1: Compatibility Fixtures And Docs

**Files:**
- Create: `demos/proxy-api/provider-demos.md`
- Create: `docs/proxy-api-compatibility.md`
- Modify: `tests/test_proxy_api_provider.py`

**Interfaces:**
- Consumes: existing `build_proxy_api_url`, `parse_proxy_api_response`, `fetch_proxy_api`.
- Produces: failing tests for `detect_proxy_api_profile`, `build_proxy_api_request`, `parse_proxy_api_response_text`, and widened `fetch_proxy_api`.

- [x] **Step 1: Add sanitized provider demo notes**

- [x] **Step 2: Add failing tests for new request and parsing behavior**

- [x] **Step 3: Run focused tests and verify failures are from missing new behavior**

### Task 2: Profile Detection And Conservative Request Builder

**Files:**
- Modify: `util/proxy/ProxyApiProvider.py`
- Test: `tests/test_proxy_api_provider.py`

**Interfaces:**
- Produces:
  - `detect_proxy_api_profile(api_url: str) -> ProxyApiProfile`
  - `build_proxy_api_request(api_url: str, *, count: int, protocol: str) -> ProxyApiRequest`
  - `build_proxy_api_url(api_url: str, *, count: int, protocol: str) -> str`

- [ ] **Step 1: Implement dataclasses and profile table**

- [ ] **Step 2: Preserve existing `build_proxy_api_url` as a compatibility wrapper**

- [ ] **Step 3: Run request-builder tests**

### Task 3: Generic JSON And Text Parser

**Files:**
- Modify: `util/proxy/ProxyApiProvider.py`
- Test: `tests/test_proxy_api_provider.py`

**Interfaces:**
- Produces:
  - `parse_proxy_api_response(payload: Any, *, protocol: str, profile: ProxyApiProfile | str | None = None) -> list[str]`
  - `parse_proxy_api_response_text(text: str, *, protocol: str, profile: ProxyApiProfile | str | None = None) -> list[str]`

- [ ] **Step 1: Add text response support**

- [ ] **Step 2: Broaden JSON traversal and provider failure detection**

- [ ] **Step 3: Run parser tests**

### Task 4: Fetch Integration And UI Copy

**Files:**
- Modify: `util/proxy/ProxyApiProvider.py`
- Modify: `tab/config.py`
- Test: `tests/test_proxy_api_provider.py`

**Interfaces:**
- Consumes: `build_proxy_api_request`, `parse_proxy_api_response_text`.
- Produces: `fetch_proxy_api` that supports JSON and text responses while returning existing `ProxyApiResult`.

- [ ] **Step 1: Update `fetch_proxy_api` to parse response text**

- [ ] **Step 2: Update proxy API UI help copy to describe demo URL support**

- [ ] **Step 3: Run integration-facing tests**

### Task 5: Regression Verification

**Files:**
- Existing tests only unless failures reveal a bug.

- [ ] **Step 1: Run focused proxy tests**

- [ ] **Step 2: Run local fanout proxy strategy tests**

- [ ] **Step 3: Run full pytest suite**

- [ ] **Step 4: Inspect git diff for accidental unrelated changes**
