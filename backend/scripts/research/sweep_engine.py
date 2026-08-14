"""스윕 공용 엔진 — 축 해석과 스펙 주입.

왜 분리하나
    2026-08-14 첫 판에서 축을 `variant/sl/tp/window` 네 개로 화이트리스트했다.
    그러면 `entry_threshold` 나 `vol_cliff_threshold` 는 스윕할 수 없고, 2군
    계열은 아예 못 돌린다 — 결국 계열마다 임시 스크립트를 또 만들게 된다.
    오늘 손계산 스크립트 6개가 정확히 그렇게 생겼다.

    배선 자체는 `ps["policy"]["kwargs"][k] = v` 한 줄이다. 막고 있던 건
    화이트리스트뿐이었다.

축 이름
    `policy.sl_pct`        정책 kwargs
    `source.entry_window_days`   **그 키를 가진 모든 소스**에 적용
    `source[0].max_age_days`     인덱스 지정
    `config.forward_bars`  파이프라인 config
    `sl_pct`               점 없으면 policy → source 순으로 찾는다.
                           없으면 오류(조용히 버리지 않는다 — 교훈 #88)

값 `keep`
    그 축을 스펙 기본값 그대로 둔다. 익절처럼 "끄는 것도 후보"인 축에 쓴다
    (신상저격수 스펙의 `tp_pct=1.0` 이 곧 비활성이다).
"""
from __future__ import annotations

import copy
import re
from typing import Any

KEEP = ("keep", "none", "default", "")

_IDX = re.compile(r"^source\[(\d+)\]\.(.+)$")


def parse_axis(spec: str) -> tuple[str, list]:
    """`policy.sl_pct=0.3,0.5` → ("policy.sl_pct", [0.3, 0.5])."""
    if "=" not in spec:
        raise ValueError(f"--axis 형식은 이름=값,값 이다: {spec!r}")
    name, raw = spec.split("=", 1)
    vals: list[Any] = []
    for x in raw.split(","):
        x = x.strip()
        if not x:
            continue
        try:
            vals.append(int(x) if "." not in x and "e" not in x.lower() else float(x))
        except ValueError:
            vals.append(x)
    if not vals:
        raise ValueError(f"--axis 값이 비었다: {spec!r}")
    return name.strip(), vals


def apply_axis(ps: dict, name: str, value: Any) -> dict:
    """파이프라인 스펙 **사본**에 축 값을 주입한다.

    ⚠ 적용 대상을 못 찾으면 **예외를 던진다.** 조용히 버리면 교훈 #88 이
      그대로 재발한다 — 스펙에 넣은 값이 팩토리에서 사라져 재진입 차단이
      한 번도 동작하지 않았던 사고다.
    """
    if isinstance(value, str) and value.lower() in KEEP:
        return ps                                   # 기본값 유지
    out = copy.deepcopy(ps)

    m = _IDX.match(name)
    if m:
        i, key = int(m.group(1)), m.group(2)
        srcs = out.get("sources") or []
        if i >= len(srcs):
            raise KeyError(f"소스 인덱스 {i} 없음 (총 {len(srcs)}개)")
        srcs[i].setdefault("kwargs", {})[key] = value
        return out

    if name.startswith("policy."):
        out.setdefault("policy", {}).setdefault("kwargs", {})[name[7:]] = value
        return out

    if name.startswith("source."):
        key = name[7:]
        hit = 0
        for s in out.get("sources") or []:
            kw = s.setdefault("kwargs", {})
            if key in kw:
                kw[key] = value
                hit += 1
        if not hit:
            raise KeyError(f"`{key}` 를 가진 소스가 없다 — 스펙 오타이거나 "
                           f"이 계열에 없는 파라미터다")
        return out

    if name.startswith("config."):
        out.setdefault("config", {})[name[7:]] = value
        return out

    # 점 없는 이름 — policy 먼저, 그다음 source
    pk = (out.get("policy") or {}).get("kwargs") or {}
    if name in pk:
        out["policy"]["kwargs"][name] = value
        return out
    hit = 0
    for s in out.get("sources") or []:
        kw = s.setdefault("kwargs", {})
        if name in kw:
            kw[name] = value
            hit += 1
    if hit:
        return out
    raise KeyError(
        f"축 `{name}` 을 스펙에서 찾지 못했다. policy.kwargs 키: {sorted(pk)} · "
        f"source.kwargs 키: "
        f"{sorted({k for s in (out.get('sources') or []) for k in (s.get('kwargs') or {})})}")


def apply_all(ps: dict, values: dict) -> dict:
    for k, v in values.items():
        ps = apply_axis(ps, k, v)
    return ps


def describe(ps: dict) -> dict:
    """이 스펙에서 스윕 가능한 축 후보. `--list-axes` 가 쓴다."""
    out = {"policy": sorted((ps.get("policy") or {}).get("kwargs") or {}),
           "sources": {}, "config": sorted(ps.get("config") or {})}
    for i, s in enumerate(ps.get("sources") or []):
        out["sources"][f"source[{i}] {s.get('type')}"] = sorted(s.get("kwargs") or {})
    return out
