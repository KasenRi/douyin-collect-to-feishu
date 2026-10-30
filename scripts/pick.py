#!/usr/bin/env python3
"""按点赞阈值筛选并随机挑选：python3 pick.py search.json [阈值=500] [K=2] [--exclude id1,id2] > picked.json"""
import json, random, sys
args = sys.argv[1:]; ex = set()
if "--exclude" in args:
    i = args.index("--exclude"); ex = set(args[i + 1].split(",")); del args[i:i + 2]
items = json.load(open(args[0]))["items"]
th = int(args[1]) if len(args) > 1 else 500; k = int(args[2]) if len(args) > 2 else 2
ok = [x for x in items if (x.get("digg_count") or 0) > th and x["aweme_id"] not in ex]
print(json.dumps({"total": len(items), "over_threshold": len(ok), "picked": random.sample(ok, min(k, len(ok)))}, ensure_ascii=False, indent=2))
