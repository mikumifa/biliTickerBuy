## 总体改动

本次改动新增了“代理 API 获取与自动补充代理池”能力。用户可以填写代理 API 地址，选择 HTTP/HTTPS 或 SOCKS5 代理类型；程序会自动拉取代理，也会在抢票过程中代理池耗尽时自动请求新的代理并替换当前代理池。目前指针对“有代理”代理商的API做了适配，如果认为此PR有用，可以提供其他代理服务商的APIdemo进行适配。

## 改动位置

### 代理 API 配置项

位置：`app_cmd/config/BuyConfig.py:63`

新增字段：

- `proxy_api_url`
- `proxy_api_protocol`
- `proxy_api_request_count`

这些字段分别支持环境变量、运行时配置、数据库字段和 CLI 参数：

- `BTB_PROXY_API_URL` / `--proxy-api-url`
- `BTB_PROXY_API_PROTOCOL` / `--proxy-api-protocol`
- `BTB_PROXY_API_REQUEST_COUNT` / `--proxy-api-request-count`

### 运行时配置同步

位置：`interface/config.py:37`

`RuntimeOptions` 新增代理 API 相关字段：

- `proxy_api_url`
- `proxy_api_protocol`
- `proxy_api_request_count`

位置：`interface/config.py:305`

`build_runtime_options()` 新增这些入参，并对 `proxy_api_request_count` 做非负数归一化。

### 代理 API 请求与解析模块

位置：`util/proxy/ProxyApiProvider.py:1`

新增模块包含：

- `ProxyApiError`
- `ProxyApiResult`
- `normalize_proxy_api_protocol()`
- `build_proxy_api_url()`
- `parse_proxy_api_response()`
- `fetch_proxy_api()`

主要行为：

- 自动把代理 API URL 中的 `count`、`format`、`protocol` 参数规范为请求需要的值。
- 支持解析常见 JSON 返回结构，例如 `data.proxy_list`、`list`、`proxies`、`items`。
- 支持从 `ip + port` 字段或 `host:port` 字符串中提取代理。
- 自动去重，并输出程序可使用的代理地址格式。

### 设置页 UI

位置：`tab/config.py:49`

新增读取代理 API 配置的辅助函数：

- `get_proxy_api_url()`
- `get_proxy_api_protocol()`

位置：`tab/config.py:82`

新增 UI 回调：

- `fetch_proxy_from_api()`：从代理 API 获取代理，并写入现有代理列表。
- `save_proxy_api_config()`：保存代理 API 地址和代理类型。

位置：`tab/config.py:394`

在“代理”设置页新增“通过代理 API 获取”区域，包括：

- 代理 API 地址输入框
- 代理地址类型下拉框
- “保存 API 配置”按钮
- “获取并填入代理”按钮
- 代理 API 结果显示框

位置：`tab/config.py:722`

绑定“保存 API 配置”和“获取并填入代理”按钮事件。

位置：`tab/config.py:875`

设置页加载配置时同步回填代理 API 地址和代理类型。

### 抢票流程自动补充代理池

位置：`task/buy.py:27`

引入 `fetch_proxy_api()`。

位置：`task/buy.py:230`

在 `handle_proxy_failure()` 内新增 `replenish_proxy_pool()`。当代理 API 已配置，并且当前代理池不可用时，会按配置数量请求新代理。

位置：`task/buy.py:263`

调用 `_handle_proxy_failure()` 时传入 `replenish_proxy_pool` 回调，让代理失败处理流程可以触发自动补池。

### 代理失败处理扩展点

位置：`task/buy_helpers.py:257`

`handle_proxy_failure()` 新增参数：

- `replenish_proxy_pool`

位置：`task/buy_helpers.py:281`

当没有可用代理时，优先调用 `replenish_proxy_pool()`。如果补池成功，会重置代理退避时间并立即返回补池成功消息；如果补池失败，则继续原有的退避等待流程。

### 替换代理池能力

位置：`util/proxy/ProxyManager.py:106`

新增 `replace_proxy_list()`，用于整体替换代理列表并重建代理状态注册表。

位置：`util/request/BiliRequest.py:110`

新增 `replace_proxy_pool()`，用于：

- 调用 `ProxyManager.replace_proxy_list()`
- 将新代理池应用到当前 session
- 失效化 HTTP/2 client，避免继续沿用旧连接状态

### 示例文件

位置：`demo/proxy_ip_request_api_demo.py:1`

新增代理 API 请求示例，用于快速验证代理服务商 API 的原始返回。

### 测试

位置：`tests/test_proxy_api_provider.py:1`

新增代理 API provider 单元测试，覆盖：

- URL 参数覆盖和规范化
- HTTP 代理解析
- SOCKS5 代理解析
- API 失败响应抛错

验证命令：

```bash
uv run pytest tests/test_proxy_api_provider.py
```
