# Security policy

## Reporting

Please report suspected vulnerabilities privately via GitHub's
["Report a vulnerability"](../../security/advisories/new) on this repo —
not in public issues. You'll get a response within a few days.

## Scope notes for researchers

- `gusset serve` binds 127.0.0.1 only and is expected to enforce
  JSON-content-type, Origin, and Host checks on POSTs (CSRF/DNS-rebinding
  hardening) and 0600 atomic writes for `.env`. Bypasses of any of those
  are in scope and very welcome.
- The graph indexer treats repository contents as untrusted input; making
  the indexer or the drift/impact parsers execute or exfiltrate anything
  from a hostile repo is in scope.
- The GitHub Action runs with the permissions declared in the committed
  workflow file; anything letting a fork PR escalate beyond its read-only
  token is in scope.
