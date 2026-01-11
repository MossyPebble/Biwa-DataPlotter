from __future__ import annotations
from typing import List, Tuple
import math, re

def trim(s: str) -> str:
    return s.strip()

def detect_column_starts(lines: List[str]) -> List[int]:

    """
        C++의 gutter detection과 동일한 방식:
        - 블록의 모든 줄을 보고, 특정 문자 위치 i가 '모든 줄에서 공백'이면 gutter(True)
        - gutter -> text로 바뀌는 지점을 column start로 기록
    """

    if not lines:
        return []

    max_width = max(len(l) for l in lines)
    is_gutter = [True] * max_width

    for l in lines:
        for i, ch in enumerate(l):
            if not ch.isspace():
                is_gutter[i] = False

    column_starts: List[int] = []
    in_gutter = True
    for i in range(max_width):
        if in_gutter and not is_gutter[i]:
            column_starts.append(i)
            in_gutter = False
        elif (not in_gutter) and is_gutter[i]:
            in_gutter = True

    return column_starts


def parse_line_by_starts(line: str, starts: List[int]) -> List[str]:

    """
        column_starts를 기준으로 고정폭 slicing.
        - starts[i] ~ starts[i+1] (마지막은 line 끝까지)
        - start가 line보다 크면 "" 반환
    """

    out: List[str] = []
    n = len(line)
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else n
        if s >= n:
            out.append("")
        else:
            out.append(line[s:e].strip())
    return out


_NUM_PREFIX = re.compile(
    r"""
    ^[ \t]*                      # leading spaces
    (?P<num>
        [+-]?(
            (?:\d+(?:\.\d*)?)    # 12, 12., 12.3
            |
            (?:\.\d+)            # .3
        )
        (?:[eE][+-]?\d+)?        # exponent
    )
    """,
    re.VERBOSE,
)

_UNIT_SCALE = {
    "a": 1e-18,
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "Meg": 1e6,
    "meg": 1e6,
    "G": 1e9,
    "T": 1e12,
}

def parse_value(str_val: str) -> float:
    # C++: if (str_val.empty()) return 0.0;
    if not str_val:
        return 0.0

    s = str_val.strip()
    if not s:
        return 0.0

    # stod(str_val, &chars_processed) 동작처럼 "앞에서부터 숫자"만 파싱
    m = _NUM_PREFIX.match(s)
    if not m:
        return 0.0  # invalid_argument

    num_str = m.group("num")
    try:
        numeric_val = float(num_str)
    except ValueError:
        return 0.0

    chars_processed = len(num_str)
    unit_part = s[chars_processed:]  # C++: substr(chars_processed)
    # C++는 unit_part_str가 정확히 남은 부분과 같아야 함(공백 없다고 가정)
    # 혹시 남은 부분에 공백이 있을 수 있으면 strip()을 켜도 되는데,
    # C++ 동작에 맞추려면 그대로 두는 편이 더 동일함.
    # unit_part = unit_part.strip()

    if unit_part == "":
        return numeric_val

    scale = _UNIT_SCALE.get(unit_part)
    if scale is not None:
        return numeric_val * scale

    return numeric_val


def HSPICEParser(text: str) -> Tuple[List[List[str]], List[List[List[float]]]]:

    """
        반환:
        all_final_headers: 블록별 최종 헤더 (list of columns)
        all_data_blocks:   블록별 데이터 (list of rows, each row is list of floats)
    """

    lines = text.splitlines()
    i = 0

    all_final_headers: List[List[str]] = []
    all_data_blocks: List[List[List[float]]] = []

    while i < len(lines):
        line = lines[i]
        if trim(line) != "x":
            i += 1
            continue

        # 블록 시작
        i += 1

        # 헤더 1
        while i < len(lines) and trim(lines[i]) == "":
            i += 1
        if i >= len(lines):
            break
        header_line_1 = lines[i]
        i += 1

        # 헤더 2
        while i < len(lines) and trim(lines[i]) == "":
            i += 1
        if i >= len(lines):
            break
        header_line_2 = lines[i]
        i += 1

        # 데이터 줄들: y 만날 때까지
        data_lines: List[str] = []
        while i < len(lines) and trim(lines[i]) != "y":
            data_lines.append(lines[i])
            i += 1

        # y가 있으면 소비
        if i < len(lines) and trim(lines[i]) == "y":
            i += 1

        block_for_gutter = [header_line_1, header_line_2, *data_lines]
        # (C++ 코드처럼 empty면 continue)
        if not block_for_gutter:
            continue

        # column start 검출
        column_starts = detect_column_starts(block_for_gutter)
        if not column_starts:
            continue

        # 헤더 결합
        parsed_h1 = parse_line_by_starts(header_line_1, column_starts)
        parsed_h2 = parse_line_by_starts(header_line_2, column_starts)

        final_headers: List[str] = []
        ncols = len(column_starts)
        for c in range(ncols):
            h1_part = parsed_h1[c] if c < len(parsed_h1) else ""
            h2_part = parsed_h2[c] if c < len(parsed_h2) else ""
            final_headers.append(trim(f"{h1_part} {h2_part}"))
        all_final_headers.append(final_headers)

        # 데이터 파싱
        current_data_rows: List[List[float]] = []
        for d_line in data_lines:
            if trim(d_line) == "":
                continue
            parsed_cols = parse_line_by_starts(d_line, column_starts)
            if len(parsed_cols) == ncols:
                row = [parse_value(s) for s in parsed_cols]
                current_data_rows.append(row)
        all_data_blocks.append(current_data_rows)

    return all_final_headers, all_data_blocks


# -------------------- 사용 예시 --------------------
if __name__ == "__main__":
    sample = """
    garbage
    x

    Time      Drain
    (ns)      (A)
    0.0       1.0e-6
    1.0       2.0e-6
    y

    x
    Vg        Id
    (V)       (A)
    0.0       1.0E-12
    1.0       2.0D-12
    y
    """

    headers_blocks, data_blocks = HSPICEParser(sample)

    for b, (headers, rows) in enumerate(zip(headers_blocks, data_blocks), start=1):
        print(f"\n=== BLOCK {b} ===")
        print("headers:", headers)
        print("rows:")
        for r in rows:
            print(" ", r)
