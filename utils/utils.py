from __future__ import annotations
import os, subprocess, logging, re, math
from PyQt6.QtWidgets import QLayout
from PyQt6.QtGui import QImage
import numpy as np

def qimage_to_rgba_numpy(img_path: str) -> np.ndarray:

    """
        PNG/JPG 등 이미지를 RGBA uint8 numpy(H, W, 4)로 변환.
        Qt 버퍼 lifetime/stride 이슈 방지 위해 반드시 copy() 수행.
    """

    qimg = QImage(img_path)
    if qimg.isNull():
        raise FileNotFoundError(f"이미지 로드 실패: {img_path}")

    qimg = qimg.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = qimg.width(), qimg.height()

    ptr = qimg.bits()
    ptr.setsize(qimg.sizeInBytes())

    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4)).copy()

    # Qt ARGB32는 메모리상 BGRA인 경우가 많음 -> RGBA로 스왑
    arr = arr[:, :, [2, 1, 0, 3]]
    return arr

def lisToCSV(path) -> None:

    """
        .lis 파일을 CSV로 변환하는 함수입니다.

        Args:
            path (str): 변환할 .lis 파일의 경로
    """

    # eishin을 실행해 .lis를 CSV로. "Usage: " << argv[0] << " <input_lis_file> <output_csv_file>"
    if not os.path.exists(path):
        logging.info(f"File not found: {path}")
        return
    
    output_path = path.replace('.lis', '.csv')
    command = f"eishin {path} {output_path}"
    try:
        subprocess.run(command, shell=True, check=True)
        logging.info(f"Converted {path} to {output_path}")
    except subprocess.CalledProcessError as e:
        logging.info(f"Error converting {path} to CSV: {e}")

def parseParamsFile(content) -> dict:

    """
        Params 파일을 파싱하여 딕셔너리로 반환하는 함수입니다.
        파일은 다음과 같은 형식이 라고 가정:
            +version = 4.3             binunit = 1               paramchk= 1               mobmod  = 0
            +capmod  = 0             igcmod  = 0               igbmod  = 0               geomod  = 0
            *+sample = 0  <-- 해당 줄은 주석 처리됨
        저런 형식을 파싱하여, 각 파라미터를 다음과 같은 딕셔너리로 반환합니다:
            {
                "version": {"value": "4.3", "favorite": False},
                "binunit": {"value": "1", "favorite": False},
                ...
            }

        Args:
            content (str): 파일 내용

        Returns:
            dict: 파싱된 파라미터 딕셔너리
    """

    params: dict[str, str] = {}

    # 예: "+version = 4.3", "paramchk= 1", "mobmod  = 0" 등
    # key: 공백/ = 를 제외한 토큰, value: 다음 공백 전까지(예: 4.3, 0, 1)
    pattern = re.compile(r'([^\s=]+)\s*=\s*([^\s]+)')

    for line in content.splitlines():
        if line.lstrip().startswith('*'): continue
        for key, value in pattern.findall(line):
            key = key.strip().lstrip("+")
            params[key.strip()] = {
                "value": value.strip(),
                "favorite": False
            }

    return params

def clear_layout(layout: QLayout, *, delete_widgets: bool = True):

    """
        layout 안의 모든 항목(위젯/서브레이아웃/스페이서)을 제거한다.
        delete_widgets=True면 위젯은 deleteLater()로 안전하게 삭제 예약.
    """

    while layout.count():
        item = layout.takeAt(0)

        w = item.widget()
        if w is not None:
            if delete_widgets:
                w.deleteLater()
            else:
                w.setParent(None)
            continue

        child_layout = item.layout()
        if child_layout is not None:
            clear_layout(child_layout, delete_widgets=delete_widgets)
            # child_layout 자체도 QWidget에 붙어있던 게 아니면 GC 대상이지만,
            # 명시적으로 제거하고 싶으면 아래처럼 parent 끊어두면 됨.
            child_layout.setParent(None)
            continue

def patch_modelcard_content_inplace(
    template_content: str,
    params: dict[str, str],
    section: tuple[str, str] | None = None,          # (start_marker, end_marker)면 그 구간만 교체
    insert_missing: bool = False,
    insert_after_line_contains: str | None = None
) -> str:
    
    """
        template_content 안에서 params에 있는 key들의 value만 '기존 위치에서' 교체.
        - '*'로 시작하는 주석 줄은 그대로 유지.
        - section 지정 시: start_marker ~ end_marker 사이에서만 교체.
        - insert_missing=True면: 파일에 없던 key는 +key = value 형태로 삽입 가능.
    """

    lines = template_content.splitlines(True)  # keep line endings

    params_lc = {k.lower(): str(v) for k, v in params.items()}
    keys = sorted(params_lc.keys(), key=len, reverse=True)
    if not keys:
        return template_content

    key_alt = "|".join(re.escape(k) for k in keys)
    pattern = re.compile(
        rf'(?P<plus>\+)?(?P<key>{key_alt})(?P<ws1>\s*)=(?P<ws2>\s*)(?P<val>[^\s]+)',
        re.IGNORECASE
    )

    in_section = (section is None)
    start_marker, end_marker = section if section else ("", "")
    found: set[str] = set()

    def repl(m: re.Match) -> str:
        key_in_file = m.group("key")
        key_lc = key_in_file.lower()
        if key_lc in params_lc:
            found.add(key_lc)
            return (
                (m.group("plus") or "") +
                key_in_file +
                m.group("ws1") + "=" + m.group("ws2") +
                params_lc[key_lc]
            )
        return m.group(0)

    out_lines: list[str] = []
    for line in lines:
        raw = line.lstrip()

        # 섹션 제한
        if section is not None:
            if (not in_section) and (start_marker in line):
                in_section = True
            elif in_section and (end_marker in line):
                in_section = False

        # 주석 줄은 그대로 / 섹션 밖이면 그대로
        if raw.startswith("*") or (not in_section):
            out_lines.append(line)
            continue

        out_lines.append(pattern.sub(repl, line))

    # 없던 키 삽입 옵션
    if insert_missing:
        missing = [k for k in keys if k not in found]
        if missing:
            insert_block = "".join(f"+{k} = {params_lc[k]}\n" for k in missing)

            if insert_after_line_contains:
                new_out: list[str] = []
                inserted = False
                for line in out_lines:
                    new_out.append(line)
                    if (not inserted) and (insert_after_line_contains in line):
                        new_out.append(insert_block)
                        inserted = True
                out_lines = new_out if inserted else out_lines + [insert_block]
            else:
                out_lines.append(insert_block)

    return "".join(out_lines)

def fmt_hybrid(v: float,
               sci_digits: int = 3,     # scientific에서 소수자리
               fixed_digits: int = 6,   # 일반표기에서 소수자리(최대)
               sci_min_exp: int = -3,   # 10^(-3) 보다 작으면 scientific
               sci_max_exp: int = 6,    # 10^(6)  이상이면 scientific
               trim_zeros: bool = True # 1.230000 -> 1.23
               ) -> str:
    # 특수값
    if not math.isfinite(v):
        return "nan" if math.isnan(v) else ("inf" if v > 0 else "-inf")
    if v == 0.0:
        return "0"

    av = abs(v)
    exp10 = int(math.floor(math.log10(av)))

    use_sci = (exp10 <= sci_min_exp) or (exp10 >= sci_max_exp)

    if use_sci:
        s = f"{v:.{sci_digits}e}"     # e.g. 1.235e+10, 1.235e-07
        s = s.replace("e+", "e")      # e+10 -> e10
        # e-07 -> e-7 (선택)
        s = re.sub(r"e(-?)0+(\d+)", r"e\1\2", s)
        if trim_zeros:
            # 1.230e10 -> 1.23e10
            s = re.sub(r"(\.\d*?[1-9])0+(e)", r"\1\2", s)
            s = s.replace(".e", "e")
        return s

    # 일반 표기(고정소수) + 불필요한 0 제거
    s = f"{v:.{fixed_digits}f}"
    if trim_zeros:
        s = s.rstrip("0").rstrip(".")
    return s

if __name__ == "__main__":

    # 테스트용 코드
    test_lis_path = "test.lis"
    lisToCSV(test_lis_path)

    test_params_content = """
    +version = 4.3             binunit = 1               paramchk= 1               mobmod  = 0
    +capmod  = 0             igcmod  = 0               igbmod  = 0               geomod  = 0
    """
    parsed_params = parseParamsFile(test_params_content)
    for k, v in parsed_params.items():
        print(f"{k}: {v}")