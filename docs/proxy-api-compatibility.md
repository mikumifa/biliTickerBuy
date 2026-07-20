# 代理 API 兼容说明

代理 API 模块支持直接粘贴代理服务商后台生成的提取 API/demo 链接，并把不同服务商的返回统一转换成 `ProxyManager` 使用的代理地址格式。

## 兼容模型

1. **自动识别**：根据域名、路径和参数名识别常见服务商。
2. **服务商 Profile**：只在已知规则下补齐为空或缺失的数量、返回格式、协议参数。
3. **通用兜底解析**：从 JSON、数组、嵌套对象、XML、纯文本、CSV 样式文本中提取代理。

模块不会再把所有 URL 强行改写成 `count/format/protocol`。很多服务商后台生成的链接带签名或特殊参数，随意改写可能导致链接失效。

## 初始 Profile

| Profile | 常见域名 | 数量参数 | 格式参数 | 说明 |
| --- | --- | --- | --- | --- |
| `youdaili` | `youdaili.com` | `count` | `format` | 保留已有有代理 JSON 结构支持。 |
| `kuaidaili` | `kdlapi.com`, `kuaidaili.com` | `num` | `format` | 支持文本和 JSON 返回。 |
| `zhima` | `zhimacangku.com`, `zhimahttp.com` | `num` | `type` | 常见 demo 中 `type=2` 表示 JSON。 |
| `xiaoxiang` | `xiaoxiangdaili.com` | `cnt` | `wt` | 常见 demo 中 `wt=json` 表示 JSON。 |
| `xiequ` | `xiequ.cn` | `num` | `type` | 后台生成链接包含较多服务商开关，默认保留。 |
| `juliang` | `juliangip.com` | `num` | `result_type` | 常见返回把代理放在 `data.proxy_list`。 |
| `qingguo` | `qg.net`, `qingguo` 相关域名 | `num`, `count` | 通用兜底 | 强兼容常见青果代理链接。 |
| `yiniuyun` | `16yun.cn`, `yiniuyun` 相关域名 | `num`, `count` | 通用兜底 | 强兼容常见亿牛云代理链接。 |
| `pinyi` | `pyhttp`, `pinyi` 相关域名 | `count`, `num` | `type` | 文本返回较常见。 |
| `taiyang` | `taiyang` 相关域名 | `num`, `count` | 通用兜底 | 走历史/通用兜底解析。 |
| `mogu` | `mogu`, `mogumiao` 相关域名 | `num`, `count` | 通用兜底 | 走历史/通用兜底解析。 |
| `xundaili` | `xundaili` 相关域名 | `num`, `count` | 通用兜底 | 走历史/通用兜底解析。 |
| `zdaye` | `zdaye.com` | `count`, `num` | `returnType` | 将服务商成功码 `10001` 视为成功，再走通用提取。 |
| `generic` | 未识别 | 只补已有且为空的兼容参数 | 只补已有且为空的兼容参数 | 不强行添加服务商参数。 |

## 标准输出

解析器返回以下格式：

```text
http://192.0.2.10:15818
socks5://192.0.2.11:1080
```

非法条目会被忽略。重复代理会去重，并保留第一次出现的顺序。

`fetch_proxy_api()` 仍返回兼容旧调用方的 `proxies: list[str]`，同时在 `proxy_records` 中保留解析到的结构化代理元数据，例如 `ttl`、`expire_time`、`deadline` 等有效期字段。

设置页获取代理 API 后会展示脱敏后的 API URL，常见凭据参数如 `key`、`token`、`signature` 会显示为 `***`。
