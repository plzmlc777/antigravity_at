"""대표님 보고 정본 표 — 머리글 가운데 · 데이터 왼쪽 · 비고는 줄바꿈 후 가운데.

⚠ 이 서식은 **대표님이 정한 것이다.** 지시 없이 바꾸지 않는다.
⚠ 한글은 두 칸이다. len() 으로 맞추면 깨진다.
"""
import unicodedata


def w(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in str(s))


def wrap(s, limit):
    s = str(s)
    if w(s) <= limit:
        return [s]
    out, cur = [], ""
    for tok in s.split(" "):
        cand = (cur + " " + tok).strip()
        if w(cand) > limit and cur:
            out.append(cur); cur = tok
        else:
            cur = cand
    if cur:
        out.append(cur)
    return out or [""]


def render(header, rows, wraps=None, wrap_center=None):
    n = len(header)
    wraps = wraps or [999] * n
    wrap_center = set(wrap_center or [])
    cells = [[wrap(c, wraps[i]) for i, c in enumerate(r)] for r in rows]
    width = [max([w(header[i])] + [w(x) for r in cells for x in r[i]])
             for i in range(n)]

    def pad(s, i, center):
        d = width[i] - w(s)
        if center:
            l = d // 2
            return " " * l + str(s) + " " * (d - l)
        return str(s) + " " * d

    def line(l, m, r):
        return l + m.join("─" * (width[i] + 2) for i in range(n)) + r

    out = [line("┌", "┬", "┐"),
           # 머리글은 가운데
           "│ " + " │ ".join(pad(header[i], i, True) for i in range(n)) + " │",
           line("├", "┼", "┤")]
    for j, r in enumerate(cells):
        if j:
            out.append(line("├", "┼", "┤"))
        h = max(len(x) for x in r)
        r = [x + [""] * (h - len(x)) for x in r]
        for k in range(h):
            # 데이터는 왼쪽. 단 줄바꿈된 칸(비고)은 가운데.
            out.append("│ " + " │ ".join(
                pad(r[i][k], i, (i in wrap_center and h > 1))
                for i in range(n)) + " │")
    out.append(line("└", "┴", "┘"))
    return "\n".join(out)


def render_md(header, rows):
    """GFM 마크다운 표. 데스크톱 앱처럼 **마크다운을 렌더링하는** 환경용.

    박스 문자 표는 한글을 정확히 2칸으로 그리는 고정폭 터미널을 전제한다.
    그 전제가 깨지는 곳(데스크톱 앱 · 텔레그램 HTML)에서는 세로선이 어긋난다.
    열·순서·값은 render() 와 **완전히 같다** — 그리는 방법만 다르다.
    비고처럼 긴 칸은 렌더러가 알아서 접으므로 wrap 하지 않는다.
    """
    def esc(c):
        return str(c).replace("|", "\\|")
    out = ["| " + " | ".join(esc(h) for h in header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(esc(c) for c in r) + " |")
    return "\n".join(out)
