import argparse
import base64
import json
import sys
import time
from collections import Counter
from copy import deepcopy
from json import JSONDecodeError
from pathlib import Path
from random import randint
from base64 import urlsafe_b64encode

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task.buy import (  # noqa: E402
    _build_order_payload,
    _build_order_token,
    _build_token_payload,
    base_url,
)
from util.BiliRequest import BiliRequest  # noqa: E402
from util.CTokenUtil import CTokenGenerator  # noqa: E402


def _decode_base64_u16(token: str | None) -> list[int] | None:
    if not token:
        return None
    raw = base64.b64decode(token)
    if len(raw) % 2 != 0:
        raise ValueError(f"token 长度不是 2 的倍数: {len(raw)}")
    return [
        int.from_bytes(raw[index : index + 2], "big") for index in range(0, len(raw), 2)
    ]


def _decode_base64_interleaved_u8(
    token: str | None, *, value_on_even_index: bool
) -> list[int] | None:
    if not token:
        return None
    raw = base64.b64decode(token)
    if len(raw) % 2 != 0:
        raise ValueError(f"token 长度不是 2 的倍数: {len(raw)}")
    if value_on_even_index:
        return [raw[index] for index in range(0, len(raw), 2)]
    return [raw[index + 1] for index in range(0, len(raw), 2)]


def _infer_ptoken_candidate_from_prepare_ctoken(
    prepare_ctoken_u8: list[int] | None,
) -> list[int] | None:
    if not prepare_ctoken_u8 or len(prepare_ctoken_u8) < 12:
        return None
    return [
        17,
        prepare_ctoken_u8[1],
        8,
        prepare_ctoken_u8[3],
        1,
        99,
        prepare_ctoken_u8[6],
        4,
        prepare_ctoken_u8[8],
        prepare_ctoken_u8[9],
        prepare_ctoken_u8[10],
        prepare_ctoken_u8[11],
    ]


def _semantic_view_from_prepare_ctoken_u8(
    prepare_ctoken_u8: list[int] | None,
) -> dict | None:
    if not prepare_ctoken_u8 or len(prepare_ctoken_u8) < 12:
        return None
    return {
        "touchend": prepare_ctoken_u8[1],
        "visibilitychange": prepare_ctoken_u8[3],
        "beforeunload_or_openwindow": prepare_ctoken_u8[6],
        "short_8_9": (prepare_ctoken_u8[8] << 8) | prepare_ctoken_u8[9],
        "short_10_11": (prepare_ctoken_u8[10] << 8) | prepare_ctoken_u8[11],
    }


def _infer_full_ptoken_u8(
    prepare_ctoken_u8: list[int] | None,
    prepare_token_second: int | None,
    base_second: int | None,
) -> list[int] | None:
    prefix = _infer_ptoken_candidate_from_prepare_ctoken(prepare_ctoken_u8)
    if prefix is None or prepare_token_second is None or base_second is None:
        return None
    tail_counter = prepare_token_second - base_second
    if tail_counter < 0 or tail_counter > 0xFFFF:
        return None
    return prefix + [4, 1, (tail_counter >> 8) & 0xFF, tail_counter & 0xFF]


def _decode_prepare_token_second(token: str | None) -> int | None:
    if not token:
        return None
    prefix = token[1:7]
    now_sec = int(time.time())
    for sec in range(now_sec - 7200, now_sec + 7200):
        encoded = urlsafe_b64encode(sec.to_bytes(5, "big")).decode("ascii").rstrip("=")
        if encoded[1:7] == prefix:
            return sec
    return None


def _load_tickets_info(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        tickets_info = json.load(file)
    if not isinstance(tickets_info, dict):
        raise ValueError("tickets_info 文件内容必须是 JSON 对象")
    return tickets_info


def _prepare_runtime_tickets_info(
    raw_tickets_info: dict,
) -> tuple[dict, list | dict | str]:
    tickets_info = dict(raw_tickets_info)
    cookies = tickets_info["cookies"]
    tickets_info.pop("cookies", None)
    tickets_info["_prepare_buyer_info"] = deepcopy(tickets_info["buyer_info"])
    tickets_info["buyer_info"] = json.dumps(
        tickets_info["buyer_info"], ensure_ascii=False
    )
    tickets_info["deliver_info"] = json.dumps(
        tickets_info["deliver_info"], ensure_ascii=False
    )
    return tickets_info, cookies


def _build_debug_snapshot(
    *,
    is_hot_project: bool,
    prepare_url: str | None,
    prepare_payload: dict | None,
    prepare_result: dict | None,
    prepare_response,
    generator_start_second: int | None,
    create_url: str,
    create_payload: dict,
    create_result: dict | None,
) -> dict:
    prepare_data = (prepare_result or {}).get("data", {})
    prepare_ptoken = prepare_data.get("ptoken")
    prepare_ctoken = prepare_payload.get("token") if prepare_payload else None
    prepare_ctoken_u8 = _decode_base64_interleaved_u8(
        prepare_ctoken, value_on_even_index=True
    )
    create_ctoken = create_payload.get("ctoken")
    inferred_ptoken_prefix = _infer_ptoken_candidate_from_prepare_ctoken(
        prepare_ctoken_u8
    )
    prepare_ctoken_semantic = _semantic_view_from_prepare_ctoken_u8(prepare_ctoken_u8)
    prepare_ptoken_u8 = _decode_base64_interleaved_u8(
        prepare_ptoken, value_on_even_index=False
    )
    prepare_token_second = _decode_prepare_token_second(prepare_data.get("token"))
    ptoken_tail_counter = None
    inferred_tail_base_second = None
    if prepare_ptoken_u8 is not None:
        ptoken_tail_counter = (prepare_ptoken_u8[14] << 8) | prepare_ptoken_u8[15]
    if prepare_token_second is not None and ptoken_tail_counter is not None:
        inferred_tail_base_second = prepare_token_second - ptoken_tail_counter
    inferred_full_ptoken_u8 = _infer_full_ptoken_u8(
        prepare_ctoken_u8,
        prepare_token_second,
        inferred_tail_base_second,
    )
    return {
        "is_hot_project": is_hot_project,
        "prepare": {
            "url": prepare_url,
            "payload": prepare_payload,
            "result": prepare_result,
            "response_headers": (
                dict(prepare_response.headers) if prepare_response is not None else None
            ),
            "response_cookies": (
                prepare_response.cookies.get_dict()
                if prepare_response is not None
                else None
            ),
            "prepare_ctoken_u8": prepare_ctoken_u8,
            "prepare_ctoken_semantic": prepare_ctoken_semantic,
            "token": prepare_data.get("token"),
            "ptoken": prepare_ptoken,
            "ptoken_u16": _decode_base64_u16(prepare_ptoken),
            "ptoken_u8": prepare_ptoken_u8,
            "inferred_ptoken_prefix_u8": inferred_ptoken_prefix,
            "inferred_prefix_matches": (
                prepare_ptoken_u8[:12] == inferred_ptoken_prefix
                if prepare_ptoken_u8 is not None and inferred_ptoken_prefix is not None
                else None
            ),
            "inferred_full_ptoken_u8": inferred_full_ptoken_u8,
            "inferred_full_matches": (
                prepare_ptoken_u8 == inferred_full_ptoken_u8
                if prepare_ptoken_u8 is not None and inferred_full_ptoken_u8 is not None
                else None
            ),
            "tail_u8": prepare_ptoken_u8[12:16] if prepare_ptoken_u8 else None,
            "prepare_token_second": prepare_token_second,
            "ptoken_tail_counter": ptoken_tail_counter,
            "inferred_tail_base_second": inferred_tail_base_second,
            "generator_start_second": generator_start_second,
            "generator_start_matches_base": (
                generator_start_second == inferred_tail_base_second
                if generator_start_second is not None
                and inferred_tail_base_second is not None
                else None
            ),
        },
        "create": {
            "url": create_url,
            "payload": {
                "project_id": create_payload.get("project_id"),
                "screen_id": create_payload.get("screen_id"),
                "sku_id": create_payload.get("sku_id"),
                "count": create_payload.get("count"),
                "order_type": create_payload.get("order_type"),
                "pay_money": create_payload.get("pay_money"),
                "again": create_payload.get("again"),
                "timestamp": create_payload.get("timestamp"),
                "token": create_payload.get("token"),
                "ctoken": create_ctoken,
                "ctoken_u16": _decode_base64_u16(create_ctoken),
                "ctoken_u8": _decode_base64_interleaved_u8(
                    create_ctoken, value_on_even_index=True
                ),
                "ptoken": create_payload.get("ptoken"),
                "orderCreateUrl": create_payload.get("orderCreateUrl"),
            },
            "result": create_result,
        },
        "relation": {
            "prepare_token_to_create_token": (
                prepare_data.get("token") == create_payload.get("token")
                if prepare_result is not None
                else None
            ),
            "prepare_ptoken_to_create_body_ptoken": (
                prepare_data.get("ptoken") == create_payload.get("ptoken")
                if prepare_result is not None
                else None
            ),
            "prepare_ptoken_in_create_url": (
                f"ptoken={prepare_data.get('ptoken')}" in create_url
                if prepare_result is not None and prepare_data.get("ptoken")
                else None
            ),
        },
    }


def _analyze_samples(samples: list[dict]) -> dict:
    ptoken_u16_rows = [sample["prepare"].get("ptoken_u16") for sample in samples]
    ptoken_u16_rows = [row for row in ptoken_u16_rows if row is not None]
    ctoken_u16_rows = [
        sample["create"]["payload"].get("ctoken_u16") for sample in samples
    ]
    ctoken_u16_rows = [row for row in ctoken_u16_rows if row is not None]

    slot_analysis = []
    if ptoken_u16_rows:
        width = len(ptoken_u16_rows[0])
        for index in range(width):
            values = [row[index] for row in ptoken_u16_rows]
            unique_values = sorted(set(values))
            slot_analysis.append(
                {
                    "slot": index,
                    "unique_count": len(unique_values),
                    "is_constant": len(unique_values) == 1,
                    "values": unique_values[:12],
                }
            )

    ctoken_slot_analysis = []
    if ctoken_u16_rows:
        width = len(ctoken_u16_rows[0])
        for index in range(width):
            values = [row[index] for row in ctoken_u16_rows]
            unique_values = sorted(set(values))
            ctoken_slot_analysis.append(
                {
                    "slot": index,
                    "unique_count": len(unique_values),
                    "is_constant": len(unique_values) == 1,
                    "values": unique_values[:12],
                }
            )

    ptoken_counter = Counter(sample["prepare"].get("ptoken") for sample in samples)
    return {
        "sample_count": len(samples),
        "unique_ptoken_count": len([value for value in ptoken_counter if value]),
        "repeated_ptokens": {
            token: count
            for token, count in ptoken_counter.items()
            if token and count > 1
        },
        "ptoken_slot_analysis": slot_analysis,
        "ctoken_slot_analysis": ctoken_slot_analysis,
        "samples_brief": [
            {
                "index": index + 1,
                "prepare_token": sample["prepare"].get("token"),
                "ptoken": sample["prepare"].get("ptoken"),
                "ptoken_u16": sample["prepare"].get("ptoken_u16"),
                "ctoken": sample["create"]["payload"].get("ctoken"),
                "ctoken_u16": sample["create"]["payload"].get("ctoken_u16"),
            }
            for index, sample in enumerate(samples)
        ],
    }


def _parse_variant_values(raw_values: str) -> list[int | str]:
    values: list[int | str] = []
    for part in raw_values.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            values.append(int(item))
        except ValueError:
            values.append(item)
    if not values:
        raise ValueError("variant-values 不能为空")
    return values


def _normalize_variant_value(value: int | str, original: object) -> int | str:
    if isinstance(original, str):
        return str(value)
    if isinstance(original, bool):
        return bool(value)
    if isinstance(original, int):
        return int(value)
    return value


def _build_variant_file(
    tickets_file: str, field: str, value: int | str, output_dir: Path
) -> Path:
    raw_tickets_info = _load_tickets_info(tickets_file)
    if field not in raw_tickets_info:
        raise KeyError(f"字段不存在: {field}")
    variant = deepcopy(raw_tickets_info)
    variant[field] = _normalize_variant_value(value, raw_tickets_info[field])
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_value = str(variant[field]).replace("\\", "_").replace("/", "_")
    variant_file = output_dir / f"variant_{field}_{safe_value}.json"
    variant_file.write_text(
        json.dumps(variant, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return variant_file


def run_variant_analysis(
    tickets_file: str,
    field: str,
    values: list[int | str],
    sample_count: int,
    proxy: str = "none",
) -> dict:
    output_dir = Path("tmp") / "variant_inputs"
    variant_results = []
    for value in values:
        variant_file = _build_variant_file(tickets_file, field, value, output_dir)
        analysis = run_sample_analysis(
            tickets_file=str(variant_file),
            sample_count=sample_count,
            proxy=proxy,
        )
        variant_results.append(
            {
                "field": field,
                "value": value,
                "tickets_file": str(variant_file),
                "analysis": analysis["analysis"],
            }
        )

    slot_summary: dict[int, dict[str, object]] = {}
    for result in variant_results:
        value_label = str(result["value"])
        for slot_info in result["analysis"]["ptoken_slot_analysis"]:
            slot = int(slot_info["slot"])
            summary = slot_summary.setdefault(
                slot,
                {
                    "slot": slot,
                    "by_value": {},
                },
            )
            by_value = summary["by_value"]
            assert isinstance(by_value, dict)
            by_value[value_label] = {
                "unique_count": slot_info["unique_count"],
                "is_constant": slot_info["is_constant"],
                "values": slot_info["values"],
            }

    changing_slots = []
    for slot, summary in sorted(slot_summary.items()):
        signatures = {
            json.dumps(detail, ensure_ascii=False, sort_keys=True)
            for detail in summary["by_value"].values()  # type: ignore[index]
        }
        if len(signatures) > 1:
            changing_slots.append(summary)

    return {
        "base_tickets_file": tickets_file,
        "field": field,
        "values": values,
        "sample_count_per_variant": sample_count,
        "variant_results": variant_results,
        "changing_slots": changing_slots,
    }


def run_debug(
    tickets_file: str,
    proxy: str = "none",
    skip_create: bool = False,
) -> dict:
    raw_tickets_info = _load_tickets_info(tickets_file)
    tickets_info, cookies = _prepare_runtime_tickets_info(raw_tickets_info)
    request = BiliRequest(cookies=cookies, proxy=proxy)

    is_hot_project = bool(tickets_info.get("is_hot_project", False))
    prepare_url: str | None = None
    prepare_payload: dict | None = None
    prepare_result: dict | None = None
    prepare_response = None
    generator_start_second: int | None = None

    if is_hot_project:
        prepare_url = f"{base_url}/api/ticket/order/prepare?project_id={tickets_info['project_id']}"
        prepare_payload = _build_token_payload(tickets_info)
        generator_start_second = int(time.time())
        ctoken_generator = CTokenGenerator(
            generator_start_second, 0, randint(2000, 10000)
        )
        prepare_payload["token"] = ctoken_generator.generate_ctoken(
            touchend=randint(1, 5),
            beforeunload=randint(1, 3),
            openWindow=randint(1, 3),
        )
        prepare_response = request.post(
            url=prepare_url,
            data=prepare_payload,
            isJson=True,
        )
        prepare_result = prepare_response.json()
        order_token = prepare_result["data"]["token"]
    else:
        ctoken_generator = None
        order_token = _build_order_token(tickets_info)

    create_payload = _build_order_payload(tickets_info, order_token)
    create_url = (
        f"{base_url}/api/ticket/order/createV2?project_id={tickets_info['project_id']}"
    )

    if is_hot_project:
        ptoken = prepare_result["data"]["ptoken"]
        create_payload["ctoken"] = ctoken_generator.generate_ctoken(  # type: ignore[union-attr]
            timer=10 + 2 * int(time.time()) - 2 * int(generator_start_second)
        )
        create_payload["ptoken"] = ptoken
        create_payload["orderCreateUrl"] = (
            "https://show.bilibili.com/api/ticket/order/createV2"
        )
        create_url += f"&ptoken={ptoken}"

    create_result = None
    if not skip_create:
        create_response = request.post(
            url=create_url,
            data=create_payload,
            isJson=True,
        )
        create_result = create_response.json()

    return _build_debug_snapshot(
        is_hot_project=is_hot_project,
        prepare_url=prepare_url,
        prepare_payload=prepare_payload,
        prepare_result=prepare_result,
        prepare_response=prepare_response,
        generator_start_second=generator_start_second,
        create_url=create_url,
        create_payload=create_payload,
        create_result=create_result,
    )


def run_sample_analysis(
    tickets_file: str,
    sample_count: int,
    proxy: str = "none",
) -> dict:
    samples = [
        run_debug(tickets_file=tickets_file, proxy=proxy, skip_create=True)
        for _ in range(sample_count)
    ]
    return {
        "tickets_file": tickets_file,
        "analysis": _analyze_samples(samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="独立调试 prepare -> createV2 的入参与出参关系"
    )
    parser.add_argument(
        "tickets_file",
        help="包含 tickets_info 的 JSON 文件路径",
    )
    parser.add_argument(
        "--proxy",
        default="none",
        help="代理配置，默认直连",
    )
    parser.add_argument(
        "--skip-create",
        action="store_true",
        help="只请求 prepare 并构造 createV2 入参，不真正发 createV2 请求",
    )
    parser.add_argument(
        "--output",
        help="可选，输出结果到 JSON 文件",
    )
    parser.add_argument(
        "--sample-count",
        type=int,
        default=1,
        help="重复采样 prepare 次数。大于 1 时自动进入批量分析模式，并隐含 skip-create",
    )
    parser.add_argument(
        "--variant-field",
        help="可选，指定要变动分析的字段，如 count / sku_id / order_type",
    )
    parser.add_argument(
        "--variant-values",
        help="与 --variant-field 配合使用，逗号分隔，如 1,2,3",
    )
    args = parser.parse_args()

    try:
        if args.variant_field:
            if not args.variant_values:
                raise SystemExit("--variant-field 需要同时提供 --variant-values")
            result = run_variant_analysis(
                tickets_file=args.tickets_file,
                field=args.variant_field,
                values=_parse_variant_values(args.variant_values),
                sample_count=max(args.sample_count, 2),
                proxy=args.proxy,
            )
        elif args.sample_count > 1:
            result = run_sample_analysis(
                tickets_file=args.tickets_file,
                sample_count=args.sample_count,
                proxy=args.proxy,
            )
        else:
            result = run_debug(
                tickets_file=args.tickets_file,
                proxy=args.proxy,
                skip_create=args.skip_create,
            )
    except JSONDecodeError as exc:
        raise SystemExit(f"接口返回不是合法 JSON: {exc}") from exc

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            file.write(rendered)
            file.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
