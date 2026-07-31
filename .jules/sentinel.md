## 2024-05-18 - [CRITICAL] Hardcoded API Keys in Documentation
**Vulnerability:** A live or structured dummy API key (`new1_03ba774bd5d7490cb30aaa8f63e6a135`) was hardcoded directly inside a documentation file (`social-media/twitterapi-io/SKILL.md`) as an example.
**Learning:** Documentation files (`README.md`, `SKILL.md`) are often overlooked during security audits but can expose actual production secrets or structured tokens if developers copy-paste working configurations directly into them for examples.
**Prevention:** Use generic, clearly identifiable placeholders (like `YOUR_API_KEY_HERE`, `sk_live_12345...`) in all documentation. Ensure secret scanning tools are configured to also scan `.md` files, not just source code.

## 2026-06-25 - [CRITICAL] Path Traversal in Secret Store
**Vulnerability:** The `_resolve` function in `devops/secret-store/scripts/secrets.py` directly appended user-provided secret names to the store path without validation, allowing directory traversal attacks (e.g., `../something`).
**Learning:** Always resolve paths and check if they are relative to the intended base directory using `pathlib`'s `is_relative_to` method to prevent directory traversal. String prefix checks (`startswith`) are vulnerable to sibling directory traversal.
**Prevention:** Use `resolved_path.is_relative_to(resolved_root)` for all user-provided file paths.

## 2026-07-04 - Fixed SSRF vulnerability in urllib urlopen calls
**Vulnerability:** Found `urllib.request.urlopen` calls receiving user-provided or external URLs without explicitly checking if the URL scheme is HTTP/HTTPS. This can lead to SSRF and Local File Read vulnerabilities via `file://` or other schemes.
**Learning:** Python's `urllib.request.urlopen` allows protocols beyond HTTP (e.g. `file://`). We need to proactively validate URLs against a whitelist of safe schemes.
**Prevention:** Explicitly validate URL schemes when fetching remote resources (e.g., `url.lower().startswith(("http://", "https://"))`). Add `# nosec B310` only after careful validation.

## 2026-07-07 - [CRITICAL] SSRF vulnerability in opener.open calls
**Vulnerability:** Found `urllib.request.build_opener().open()` calls receiving external URLs without explicit HTTP/HTTPS validation. This can lead to SSRF via `file://` or other schemes, similar to `urllib.request.urlopen`.
**Learning:** Bandit currently has a blind spot and does not flag `opener.open()` for SSRF (B310). We must proactively audit for both `urlopen` and `opener.open` to prevent SSRF vulnerabilities.
**Prevention:** Explicitly validate URL schemes when fetching remote resources using `opener.open()` (e.g., `url.lower().startswith(("http://", "https://"))`). Add `# nosec B310` only after careful validation.

## 2026-07-11 - [HIGH] Unencrypted transmission of credentials over HTTP
**Vulnerability:** MCP client scripts (`research/msgvault_mcp/scripts/search_vault.py` and `research/superhuman_mcp/scripts/draft_email.py`) accepted user-provided URLs without enforcing HTTPS. If a user provided an `http://` URL, Bearer tokens and Basic Auth credentials would be sent in plaintext over the network.
**Learning:** Local dev tools often default to accepting HTTP for ease of use (e.g., pointing to `http://localhost`). However, when these tools also accept remote URLs and attach sensitive auth headers, failing to restrict HTTP to loopback addresses creates a massive footgun for unencrypted credential leakage.
**Prevention:** When sending sensitive authentication tokens, always parse the URL using `urllib.parse.urlparse` and enforce `scheme == "https"`, except when the hostname is explicitly a local loopback (`localhost`, `127.0.0.1`, `::1`) or the user explicitly passes an `--insecure` override.

## 2026-07-26 - [HIGH] Bandit blind spot for SSRF in requests
**Vulnerability:** Found `requests.get` and `requests.Session().get` calls receiving external URLs without explicit HTTP/HTTPS scheme validation, leading to potential SSRF and Local File Read (e.g., `file://`).
**Learning:** While `bandit` rule B310 correctly flags `urllib.request.urlopen()` for SSRF, it currently has a blind spot and does not flag `requests` usage. We must manually audit for `requests` in addition to standard `urllib` usage.
**Prevention:** Explicitly validate URL schemes when fetching remote resources via `requests` (e.g., `url.lower().startswith(("http://", "https://"))`). Add `# nosec B310` to indicate manual validation.
