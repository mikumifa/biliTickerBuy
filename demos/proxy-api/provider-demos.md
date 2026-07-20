# Proxy API Provider Demos

All examples are sanitized. Credential-like query values are intentionally left blank.

## Youdaili

Demo URL shape, with credential values omitted:

```text
http://api.youdaili.com/v1/proxy/get?count=5&format=json&protocol=http
```

Representative JSON:

```json
{
  "code": 0,
  "msg": "OK",
  "data": {
    "count": 1,
    "proxy_list": [
      { "ip": "8.8.8.8", "port": 12234 }
    ]
  }
}
```

## Kuaidaili

Demo URL shape, with credential and signature values omitted:

```text
https://dps.kdlapi.com/api/getdps/?num=5&format=json&sep=1
```

Text output often uses one proxy per line:

```text
192.0.2.10:15818
192.0.2.11:15819
```

## Zhima HTTP

Demo URL shape:

```text
https://webapi.http.zhimacangku.com/getip?num=5&type=2&pro=&city=0&yys=0&port=1&ts=1&ys=0&cs=0&lb=1&sb=0&pb=4&mr=1&regions=
```

Representative JSON:

```json
{
  "code": 0,
  "success": true,
  "data": [
    { "ip": "192.0.2.20", "port": 15820 }
  ]
}
```

## Xiaoxiang

Demo URL shape:

```text
https://api.xiaoxiangdaili.com/ip/get?cnt=5&wt=json
```

Representative JSON:

```json
{
  "code": 200,
  "success": true,
  "data": [
    { "ip": "192.0.2.30", "port": 15830 }
  ]
}
```

## Xiequ

Demo URL shape, with account values omitted:

```text
http://api.xiequ.cn/VAD/GetIp.aspx?act=get&num=5&time=30&plat=0&re=0&type=2&so=1&ow=1&spl=1&addr=&db=1
```

Text output can be plain `ip:port` lines.

## Juliang

Demo URL shape:

```text
https://v2.api.juliangip.com/dynamic/getips?filter=1&num=5&pt=1&result_type=json
```

Representative JSON:

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "proxy_list": [
      "192.0.2.40:15840"
    ]
  }
}
```

## Pinyi

Demo URL shape:

```text
http://tiqu.pyhttp.taolop.com/getflowip?count=5&neek=NEEK&type=1&yys=0&port=1&sb=&mr=1&sep=1
```

Text output can be plain `ip:port` lines.

## Zdaye

Demo URL shape:

```text
https://www.zdaye.com/dayProxy/ip/PORT/?count=5&returnType=2
```

Representative JSON:

```json
{
  "code": "10001",
  "msg": "获取成功",
  "data": {
    "proxy_list": [
      { "ip": "192.0.2.50", "port": 15850 }
    ]
  }
}
```

Response formats vary by package; generic JSON and text parsing are used as fallback.
