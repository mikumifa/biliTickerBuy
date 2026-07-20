# Proxy API Compatibility Design

## Goal

Refactor proxy API fetching into an automatic recognition, provider profile, and generic fallback parser pipeline. Users should be able to paste a provider's generated extraction API demo URL and get a normalized proxy list without hand-editing provider-specific parameters.

## Architecture

The public entry point remains `fetch_proxy_api(api_url, count, protocol, timeout=15)` so UI and buy-task code do not need broad changes. Internally it will resolve a `ProxyApiProfile`, build a conservative request URL, fetch text, and parse the response through provider-aware success checks plus a generic extractor.

The request builder will preserve the user's URL by default. A profile may fill blank or missing count, format, or protocol parameters only when that behavior is known for that provider. Unknown providers use `generic`, which never forces `count/format/protocol` onto the URL unless an existing compatible key is blank.

The parser accepts JSON objects, JSON arrays, and plain text. It extracts proxies from common fields and free-form text, normalizes them to `scheme://[user[:pass]@]host:port`, de-duplicates while preserving order, and raises clear Chinese errors when the provider reports failure or no proxy can be parsed.

## Provider Profiles

Initial first-class profiles:

- `youdaili`
- `kuaidaili`
- `zhima`
- `xiaoxiang`
- `xiequ`
- `juliang`
- `pinyi`
- `zdaye`
- `generic`

Profiles recognize URL domains and known parameter names. Profiles should stay small: host/path matching, request parameter aliases, success-code hints, and optional protocol mapping.

## Data Flow

1. UI or buy task calls `fetch_proxy_api`.
2. `detect_proxy_api_profile(api_url)` chooses a profile.
3. `build_proxy_api_request(api_url, count, protocol)` returns a URL and profile metadata.
4. `requests.get` fetches the provider response as text.
5. The parser tries JSON first, then text.
6. Parsed proxies are passed unchanged to `ProxyManager.replace_proxy_list` or displayed in the UI.

## Error Handling

- Empty API URL raises `ProxyApiError("请先填写代理 API 地址")`.
- HTTP status errors continue to use `requests` exceptions.
- Provider failure payloads surface `msg`, `message`, `reason`, `ERRORMSG`, or similar fields.
- Successful responses without parseable proxies raise `ProxyApiError("代理 API 返回成功，但没有解析到代理 IP 和端口")`.
- Invalid proxy entries are ignored rather than aborting the whole response.

## Testing

Tests cover request-building conservatism, profile detection, JSON extraction, text extraction, provider failure detection, auth formats, IPv6, de-duplication, and the unchanged public `fetch_proxy_api` interface.

## Documentation Artifacts

Provider API demos and sanitized response samples live under `demos/proxy-api/`. Compatibility notes live in `docs/proxy-api-compatibility.md`.
