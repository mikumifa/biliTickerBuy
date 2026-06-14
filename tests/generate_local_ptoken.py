import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from util.PTokenUtil import generate_inferred_ptoken_without_prepare  # noqa: E402


def _load_tickets_info(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("tickets_info must be a JSON object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="本地生成推断版 ptoken，不调用 prepare 接口"
    )
    parser.add_argument(
        "tickets_file", help="配置文件路径，仅用于读取 is_hot_project 等上下文"
    )
    parser.add_argument(
        "--collection-second",
        type=int,
        help="自定义本地 collection 起点秒级时间戳，默认当前秒",
    )
    parser.add_argument(
        "--current-second",
        type=int,
        help="自定义当前秒级时间戳，默认当前秒",
    )
    parser.add_argument(
        "--stay-time",
        type=int,
        default=3000,
        help="生成 prepare ctoken 时使用的 stay_time，默认 3000",
    )
    args = parser.parse_args()

    tickets_info = _load_tickets_info(args.tickets_file)
    collection_second = args.collection_second
    current_second = args.current_second
    if collection_second is None:
        collection_second = int(time.time())
    if current_second is None:
        current_second = collection_second

    generated = generate_inferred_ptoken_without_prepare(
        collection_second=collection_second,
        current_second=current_second,
        stay_time=args.stay_time,
    )
    result = {
        "tickets_file": args.tickets_file,
        "is_hot_project": bool(tickets_info.get("is_hot_project", False)),
        "local_generation_mode": "no_prepare_request",
        "assumption": {
            "ptoken_prefix_is_mapped_from_locally_generated_prepare_ctoken": True,
            "ptoken_tail_is_elapsed_seconds_from_collection_second": True,
        },
        "generated": generated,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
