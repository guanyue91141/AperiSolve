#!/usr/bin/env python3
"""Generate the steganography decision-tree mindmap for the cheatsheet.

Emits three artifacts from a single node/edge model so they never drift:

* ``decision-tree.svg``        — hand-drawn (Excalidraw-style) mindmap. Used as
                                 the thumbnail on ``/cheatsheet`` and, inlined,
                                 as the interactive map on ``/cheatsheet/map``.
* ``decision-tree.json``       — the same model as data: powers the hover
                                 tooltips (full command, detail, wiki link) on
                                 the interactive map page.
* ``decision-tree.excalidraw`` — the editable Excalidraw scene; open it at
                                 https://excalidraw.com to refine the diagram
                                 and re-export.

The SVG carries a transparent "hit" overlay per step (``class="ds-step"`` with
``data-b``/``data-s`` indices into the JSON) so the map page can attach hover,
keyboard focus and export handlers without a second renderer.

Run: ``python scripts/gen_decision_tree.py`` (pure standard library).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "aperisolve" / "static" / "img" / "cheatsheet"

# --- Diagram model -------------------------------------------------------

ROOT_TITLE = "任意文件"
ROOT_SUB = "先检查：file · exiftool · strings · binwalk"
ROOT_DETAIL = (
    "先用 file（文件类型识别工具）识别真实格式，不要轻信扩展名，再选择下方分支。"
    "每个文件都先运行 exiftool（元数据查看工具）-a -u -g1、strings（字符串提取工具）-n 8 "
    "（UTF-16 文本可加 -e l / -e b）以及 binwalk（文件特征扫描工具）。"
)

# Each branch: label, accent color, and an ordered list of steps. A step is
# (cmd, hint, full, detail, href):
#   cmd    short mono label shown in the pill (line 1)
#   hint   dim sub-label in the pill (line 2, may be "")
#   full   the concrete command / action, copyable from the tooltip
#   detail one-sentence explanation shown on hover
#   href   a wiki path (client prepends the language prefix) or absolute URL;
#          "" for none.
Step = tuple[str, str, str, str, str]
Branch = tuple[str, str, list[Step]]

BRANCHES: list[Branch] = [
    (
        "PNG / BMP 图像",
        "#9fef00",
        [
            (
                "zsteg -a",
                "LSB 文本 / 文件",
                "zsteg -a file.png",
                (
                    "PNG（便携式网络图形）/ BMP（位图）中可能藏有数据；使用 zsteg（图像隐写分析工具）扫描常见 LSB（最低有效位）通道和位序，查找隐藏文本或文件，再用 zsteg -E 提取可疑行。"
                ),
                "/wiki/tools/zsteg",
            ),
            (
                "pngcheck -vtp7f",
                "CRC / IHDR 尺寸",
                "pngcheck -vtp7f file.png",
                (
                    "IHDR（图像头数据块）中的 CRC（循环冗余校验）错误表示文件头可能被改过；缩小宽高会隐藏可见区域下方的像素。"
                ),
                "/wiki/tools/pngcheck",
            ),
            (
                "位平面",
                "全通道 + MSB",
                "decomposer（位平面分解器）/ Stegsolve（隐写图像查看工具）",
                (
                    "浏览全部位平面和通道（包括 Alpha 透明度）；尝试 MSB（最高有效位）和按列读取，不要只看 RGB LSB。"
                ),
                "/wiki/tools/decomposer",
            ),
            (
                "IEND 后附加数据",
                "提取文件尾部",
                "binwalk -e file.png",
                (
                    "IEND 数据块之后可能附加了数据；可用 binwalk/foremost（文件雕刻工具）或按字节偏移提取。"
                ),
                "/wiki/tools/foremost",
            ),
            (
                "调色板重映射",
                "索引色 PNG",
                "Color remapping（颜色映射）/ 随机打乱调色板",
                (
                    "索引色 PNG 可能把图像藏在调色板中；随机打乱或重映射调色板即可显现隐藏图案。"
                ),
                "/wiki/tools/color_remapping",
            ),
            (
                "OpenStego",
                "随机化 LSB",
                "openstego extract -sf file.png",
                "处理 zsteg 未发现的随机化 LSB 载荷；需要 OpenStego（开源隐写工具），有时还需要密钥。",
                "/wiki/tools/openstego",
            ),
        ],
    ),
    (
        "JPEG 图像",
        "#ffa657",
        [
            (
                "steghide -p ''",
                "先试空密码",
                "steghide extract -sf file.jpg -p ''",
                (
                    "JPEG（联合图像专家组格式）中常见 steghide（隐写载荷提取工具）；先试空密码，再试文件名或挑战名称。"
                ),
                "/wiki/tools/steghide",
            ),
            (
                "stegseek rockyou",
                "破解密码",
                "stegseek file.jpg rockyou.txt",
                "stegseek 可用 rockyou 字典在数秒内尝试破解 steghide 密码。",
                "/wiki/tools/stegseek",
            ),
            (
                "outguess / jsteg",
                "JPHide / 其他工具",
                "outguess -r file.jpg out.txt",
                (
                    "如果不是 steghide 载荷，可尝试 OutGuess、jsteg 或 JPHide（jpseek）；zsteg 不适用于 JPEG。"
                ),
                "/wiki/tools/outguess",
            ),
            (
                "stegdetect",
                "统计检测",
                "stegdetect file.jpg",
                "统计检测器，可提示 JPEG 文件可能使用了哪种隐写工具。",
                "/wiki/techniques/images",
            ),
        ],
    ),
    (
        "GIF / APNG 动图",
        "#d2a8ff",
        [
            (
                "提取帧",
                "ffmpeg -vsync 0",
                "ffmpeg -i file.gif -vsync 0 out/f%d.png",
                (
                    "GIF（图形交换格式）/ APNG（动态图像扩展）动画可能包含零时长帧；先提取每一帧，再逐帧运行 PNG 检查清单。"
                ),
                "/wiki/techniques/images",
            ),
            (
                "帧持续时间",
                "摩斯码 / 二进制",
                "identify -verbose file.gif",
                "每帧延迟可能编码 Morse（摩斯电码）/ 二进制 / ASCII 文本。",
                "/wiki/tools/identify",
            ),
            (
                "比较帧差异",
                "相邻帧",
                "比较第 N 帧与第 N+1 帧",
                "载荷可能藏在两张几乎相同的相邻帧的差异中。",
                "/wiki/techniques/images",
            ),
            (
                "调色板技巧",
                "",
                "随机打乱 / 重映射调色板",
                "与 PNG 相同的索引色调色板检查技巧。",
                "/wiki/tools/color_remapping",
            ),
        ],
    ),
    (
        "音频",
        "#79c0ff",
        [
            (
                "先看频谱图",
                "Audacity / sox",
                "sox file.wav -n spectrogram -o spec.png",
                (
                    "优先查看频率域；文字和 QR（快速响应码）经常被绘制在频谱图中，也要检查 20 kHz 以上和 20 Hz 以下。"
                ),
                "/wiki/tools/spectrogram",
            ),
            (
                "波形",
                "解读 Morse",
                "audacity file.wav",
                "波形中明显的开关脉冲可能组成 Morse（摩斯电码）。",
                "/wiki/techniques/audio",
            ),
            (
                "WAV LSB",
                "stegolsb wavsteg",
                "stegolsb wavsteg -r -i file.wav -o out.txt -n 1 -b 1000",
                "WAV（波形音频格式）样本中可能藏有 LSB 载荷；数据通常并非从样本 0 开始。",
                "/wiki/techniques/audio",
            ),
            (
                "SSTV / DTMF / FSK",
                "QSSTV / minimodem",
                "minimodem --rx 1200",
                (
                    "SSTV（慢扫描电视）、DTMF（双音多频）和 FSK（频移键控）信号可分别用 QSSTV、DTMF 解码器及 minimodem / multimon-ng 处理。"
                ),
                "/wiki/techniques/audio",
            ),
            (
                "steghide",
                "DeepSound",
                "steghide extract -sf file.wav",
                "带密码的容器可用 steghide（支持 WAV/AU）或 DeepSound 提取。",
                "/wiki/tools/steghide",
            ),
        ],
    ),
    (
        "视频",
        "#f778ba",
        [
            (
                "ffprobe 轨道",
                "统计轨道",
                "ffprobe file.mp4",
                "MP4（MPEG-4 视频格式）中的额外字幕、附件或数据轨道往往就是关键线索。",
                "/wiki/techniques/video",
            ),
            (
                "提取帧",
                "ffmpeg -vsync 0",
                "ffmpeg -i file.mp4 -vsync 0 out/f%05d.png",
                "对提取出的无损帧运行 PNG 检查清单（zsteg、位平面）。",
                "/wiki/techniques/video",
            ),
            (
                "字幕 / 附件",
                "-map 0:s / 提取",
                "ffmpeg -i file.mkv -map 0:s:0 subs.srt",
                "提取字幕轨道和附件文件（字体、图像等）。",
                "/wiki/techniques/video",
            ),
            (
                "提取音轨",
                "→ 查看频谱图",
                "ffmpeg -i file.mp4 -vn audio.wav",
                "提取音轨后按音频挑战检查（先查看频谱图）。",
                "/wiki/techniques/audio",
            ),
            (
                "moov / 尾随数据",
                "exiftool · binwalk",
                "binwalk file.mp4",
                "检查元数据以及 moov atom（MP4 媒体数据索引结构）之后的字节。",
                "/wiki/tools/exiftool",
            ),
        ],
    ),
    (
        "文本",
        "#56d4bc",
        [
            (
                "cat -A → stegsnow",
                "空白字符",
                "stegsnow -C file.txt",
                "行尾空格 / 制表符可用 cat -A 显示，再用 stegsnow（空白字符隐写提取工具）提取。",
                "/wiki/tools/stegsnow",
            ),
            (
                "零宽字符",
                "U+200B / C / D",
                "比较 wc -c 输出与可见文本长度",
                (
                    "不可见的零宽字符；使用 xxd 或零宽字符解码器检查码点。",
                ),
                "/wiki/techniques/text",
            ),
            (
                "形近字符",
                "混用字母体系",
                "Irongeek 形近字符解码器",
                "拉丁字母 a 与西里尔字母 а 外观相近；这种 homoglyph（形近字符）可用解码器区分。",  # noqa: RUF001
                "/wiki/techniques/text",
            ),
            (
                "编码 / 奇特语言",
                "CyberChef Magic",
                "CyberChef → Magic",
                "Brainfuck、Whitespace、Piet、Malbolge（特殊编程语言）和多层 base-N 编码可尝试 CyberChef（数据分析与编码转换工具）的 Magic 操作。",
                "/wiki/techniques/encodings",
            ),
        ],
    ),
    (
        "压缩包 / 文档",
        "#ff7b72",
        [
            (
                "unzip / 7z",
                "附加 ZIP",
                "unzip file.png",
                "文件可能附加了压缩包；unzip / 7z l 通常可以直接读取。",
                "/wiki/tools/binwalk",
            ),
            (
                "binwalk -e",
                "提取嵌入文件",
                "binwalk -e file.bin",
                "从容器中雕刻出嵌入文件或压缩数据。",
                "/wiki/tools/binwalk",
            ),
            (
                "多格式文件？",
                "检查多个魔数",
                "检查是否存在多个文件魔数",
                "同一文件可能同时符合两种格式（PDF/ZIP、JPEG/ZIP、GIF/JS），这类 polyglot（多格式文件）不会被 file 自动标记。",
                "/wiki/techniques/files-archives",
            ),
            (
                "PDF / DOCX / APK",
                "本质是 ZIP",
                "7z x file.docx",
                ".docx / .pptx / .jar / .apk 本质是 ZIP；PDF 可用 pdfdetach -saveall。",
                "/wiki/tools/pdfinfo",
            ),
            (
                "fcrackzip -u -D",
                "破解 ZIP 密码",
                "fcrackzip -u -D -p rockyou.txt file.zip",
                "ZipCrypto（ZIP 传统加密方式）较弱（也可用 bkcrack 执行已知明文攻击）；AES-256（高级加密标准）则不适用。",
                "/wiki/cheatsheet/brute-force",
            ),
        ],
    ),
    (
        "PCAP / 网络",
        "#e3b341",
        [
            (
                "tshark -qz io,phs",
                "查看协议组成",
                "tshark -r file.pcap -qz io,phs",
                "PCAP（数据包捕获）中的协议层级可显示捕获数据包含哪些网络协议。",
                "/wiki/cheatsheet/network",
            ),
            (
                "--export-objects",
                "提取 HTTP/SMB",
                "tshark -r file.pcap --export-objects http,out/",
                "从 HTTP（超文本传输协议）/ SMB（服务器消息块）/ TFTP（简易文件传输协议）通信中提取传输文件。",
                "/wiki/cheatsheet/network",
            ),
            (
                "usb.capdata",
                "按键记录",
                "tshark -r f.pcap -Y usb.capdata -T fields -e usb.capdata",
                "USB（通用串行总线）HID（人机接口设备）捕获数据可还原按键输入和鼠标移动。",
                "/wiki/cheatsheet/network",
            ),
            (
                "dns.qry.name",
                "子域名中的外传数据",
                "tshark -r f.pcap -Y dns -T fields -e dns.qry.name",
                "DNS（域名系统）子域名中可能藏有外传数据。",
                "/wiki/cheatsheet/network",
            ),
        ],
    ),
    (
        "未知 / 原始数据",
        "#8b949e",
        [
            (
                "file / 十六进制",
                "识别格式",
                "file target",
                "以 file（文件类型识别工具）的识别结果为准，不要轻信扩展名；使用十六进制编辑器检查字节。",
                "/wiki/tools/file",
            ),
            (
                "binvis.io",
                "可视化字节",
                "打开 binvis.io（字节数据可视化网站）",
                "通过字节熵和模式的可视化结果寻找隐藏结构。",
                "https://binvis.io/",
            ),
            (
                "按原始数据导入",
                "GIMP / Audacity",
                "按原始数据导入",
                "将未知数据块作为原始图像（GIMP）或原始音频（Audacity）导入。",
                "/wiki/techniques/steganalysis",
            ),
            (
                "QR / 盲文",
                "解码数据块",
                "zbarimg --raw img.png",
                "使用 zbarimg 解码 QR（快速响应码）/ 条形码；Braille（盲文）/ 旗语可手动识别。",
                "/wiki/techniques/encodings",
            ),
        ],
    ),
]

# --- Geometry ------------------------------------------------------------

# Fixed column width so pills never overlap; the canvas grows with the number
# of branches instead of squeezing them.
MARGIN_X = 20
COL_W = 172
W = MARGIN_X * 2 + COL_W * len(BRANCHES)
PILL_W = 154
ROOT_W, ROOT_H = 480, 66
ROOT_X, ROOT_Y = (W - ROOT_W) / 2, 20
HEADER_Y, HEADER_H = 150, 40
STEP_Y0, STEP_H, STEP_PITCH = 214, 50, 62
MAX_STEPS = max(len(steps) for _, _, steps in BRANCHES)
H = int(STEP_Y0 + MAX_STEPS * STEP_PITCH + 18)

DARK_TEXT = "#0b121f"
LIGHT_TEXT = "#d4dbe6"
DIM_TEXT = "#8a97ab"
PANEL = "#0d1522"
PILL_FILL = "#16233a"


def col_center(i: int) -> float:
    return MARGIN_X + COL_W * (i + 0.5)


# --- SVG renderer --------------------------------------------------------

FONT = "'Noto Sans CJK SC','Segoe UI',sans-serif"
MONO = "'Noto Sans Mono CJK SC','Fira Code',ui-monospace,monospace"


def svg() -> str:
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" class="decision-tree-svg" '
        f'aria-label="按文件类型排查隐写术的决策树" '
        f'font-family="{FONT}">'
    )
    parts.append(
        '<defs><filter id="rough" filterUnits="userSpaceOnUse" '
        f'x="0" y="0" width="{W}" height="{H}">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.013" '
        'numOctaves="2" seed="7" result="n"/>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="2.4" '
        'xChannelSelector="R" yChannelSelector="G"/></filter></defs>'
    )
    # Backdrop panel + title.
    parts.append(
        f'<rect x="4" y="4" width="{W - 8}" height="{H - 8}" rx="16" '
        f'fill="{PANEL}" stroke="#9fef0022" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="24" y="34" font-family="{MONO}" font-size="17" '
        f'fill="#9fef00" font-weight="700">隐写术排查：从哪里开始</text>'
    )
    parts.append(
        f'<text x="{W - 24}" y="34" text-anchor="end" font-family="{MONO}" '
        f'font-size="12" fill="{DIM_TEXT}">数字表示推荐顺序 · 悬停查看说明</text>'
    )

    shapes: list[str] = []
    labels: list[str] = []
    # Transparent interaction overlays, drawn last so they sit on top and
    # receive pointer/keyboard events on the map page (invisible otherwise).
    hits: list[str] = []

    # Connectors root -> headers (drawn first, behind).
    rbx, rby = W / 2, ROOT_Y + ROOT_H
    for i in range(len(BRANCHES)):
        cx = col_center(i)
        htop = HEADER_Y
        shapes.append(
            f'<path d="M {rbx:.0f} {rby:.0f} C {rbx:.0f} {rby + 34:.0f}, '
            f'{cx:.0f} {htop - 28:.0f}, {cx:.0f} {htop:.0f}" '
            f'fill="none" stroke="#8a97ab" stroke-width="1.6" opacity="0.6"/>'
        )

    # Root node.
    shapes.append(
        f'<rect x="{ROOT_X:.0f}" y="{ROOT_Y}" width="{ROOT_W}" height="{ROOT_H}" '
        f'rx="14" fill="#101a2b" stroke="#9fef00" stroke-width="2.4"/>'
    )
    labels.append(
        f'<text x="{W / 2:.0f}" y="{ROOT_Y + 28}" text-anchor="middle" '
        f'font-family="{MONO}" font-size="20" font-weight="700" fill="#9fef00">{ROOT_TITLE}</text>'
    )
    labels.append(
        f'<text x="{W / 2:.0f}" y="{ROOT_Y + 50}" text-anchor="middle" '
        f'font-family="{MONO}" font-size="12.5" fill="{LIGHT_TEXT}">{html.escape(ROOT_SUB)}</text>'
    )
    root_aria = f"{ROOT_TITLE}：先执行初步检查 — {ROOT_SUB}"
    hits.append(
        f'<rect class="ds-step" data-root="1" x="{ROOT_X:.0f}" y="{ROOT_Y}" '
        f'width="{ROOT_W}" height="{ROOT_H}" rx="14" fill="#9fef00" stroke="#9fef00" '
        f'fill-opacity="0" stroke-opacity="0" pointer-events="all" tabindex="0" '
        f'role="button" aria-label="{html.escape(root_aria)}"/>'
    )

    for i, (label, color, steps) in enumerate(BRANCHES):
        cx = col_center(i)
        hx = cx - PILL_W / 2
        # Column spine behind the pills.
        last_cy = STEP_Y0 + (len(steps) - 1) * STEP_PITCH + STEP_H / 2
        shapes.append(
            f'<path d="M {cx:.0f} {HEADER_Y + HEADER_H} L {cx:.0f} {last_cy:.0f}" '
            f'stroke="{color}" stroke-width="1.6" opacity="0.5" fill="none"/>'
        )
        # Category header (filled accent).
        shapes.append(
            f'<rect x="{hx:.0f}" y="{HEADER_Y}" width="{PILL_W}" height="{HEADER_H}" '
            f'rx="12" fill="{color}" stroke="{color}" stroke-width="1.5"/>'
        )
        labels.append(
            f'<text x="{cx:.0f}" y="{HEADER_Y + 25}" text-anchor="middle" '
            f'font-size="15" font-weight="700" fill="{DARK_TEXT}">{html.escape(label)}</text>'
        )
        # Steps.
        for j, (l1, l2, _full, _detail, _href) in enumerate(steps):
            sy = STEP_Y0 + j * STEP_PITCH
            shapes.append(
                f'<rect x="{hx:.0f}" y="{sy}" width="{PILL_W}" height="{STEP_H}" '
                f'rx="11" fill="{PILL_FILL}" stroke="{color}" stroke-width="1.4" opacity="0.98"/>'
            )
            # Order badge.
            bx, byc = hx + 15, sy + STEP_H / 2
            shapes.append(f'<circle cx="{bx:.0f}" cy="{byc:.0f}" r="10" fill="{color}"/>')
            labels.append(
                f'<text x="{bx:.0f}" y="{byc + 4:.0f}" text-anchor="middle" '
                f'font-size="12" font-weight="700" fill="{DARK_TEXT}">{j + 1}</text>'
            )
            tx = hx + 32
            if l2:
                labels.append(
                    f'<text x="{tx:.0f}" y="{sy + 21}" font-family="{MONO}" '
                    f'font-size="11.5" fill="{LIGHT_TEXT}" font-weight="600">'
                    f"{html.escape(l1)}</text>"
                )
                labels.append(
                    f'<text x="{tx:.0f}" y="{sy + 37}" font-size="11" '
                    f'fill="{DIM_TEXT}">{html.escape(l2)}</text>'
                )
            else:
                labels.append(
                    f'<text x="{tx:.0f}" y="{sy + 30}" font-family="{MONO}" '
                    f'font-size="11.5" fill="{LIGHT_TEXT}" font-weight="600">'
                    f"{html.escape(l1)}</text>"
                )
            aria = f"{label} 第 {j + 1} 步：{l1}" + (f" — {l2}" if l2 else "")
            hits.append(
                f'<rect class="ds-step" data-b="{i}" data-s="{j}" x="{hx:.0f}" y="{sy}" '
                f'width="{PILL_W}" height="{STEP_H}" rx="11" fill="{color}" stroke="{color}" '
                f'fill-opacity="0" stroke-opacity="0" pointer-events="all" tabindex="0" '
                f'role="button" aria-label="{html.escape(aria)}"/>'
            )

    parts.append(f'<g filter="url(#rough)">{"".join(shapes)}</g>')
    parts.append("".join(labels))
    parts.append(f'<g class="ds-hits">{"".join(hits)}</g>')
    parts.append("</svg>")
    return "".join(parts)


# --- Data (JSON) renderer ------------------------------------------------


def data() -> dict:
    """The diagram model as data, consumed by the interactive map page."""
    return {
        "root": {"title": ROOT_TITLE, "sub": ROOT_SUB, "detail": ROOT_DETAIL},
        "branches": [
            {
                "label": label,
                "color": color,
                "steps": [
                    {
                        "n": j + 1,
                        "cmd": l1,
                        "hint": l2,
                        "full": full,
                        "detail": detail,
                        "href": href,
                    }
                    for j, (l1, l2, full, detail, href) in enumerate(steps)
                ],
            }
            for label, color, steps in BRANCHES
        ],
    }


# --- Excalidraw scene renderer ------------------------------------------


def _el(idx: int, **kw) -> dict:
    base = {
        "id": kw["id"],
        "type": kw["type"],
        "x": kw["x"],
        "y": kw["y"],
        "width": kw.get("width", 0),
        "height": kw.get("height", 0),
        "angle": 0,
        "strokeColor": kw.get("strokeColor", "#1e1e1e"),
        "backgroundColor": kw.get("backgroundColor", "transparent"),
        "fillStyle": "solid",
        "strokeWidth": kw.get("strokeWidth", 2),
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "index": f"a{idx}",
        "roundness": kw.get("roundness", {"type": 3}),
        "seed": 1000 + idx * 7,
        "version": 1,
        "versionNonce": 100000 + idx * 13,
        "isDeleted": False,
        "boundElements": kw.get("boundElements"),
        "updated": 1,
        "link": None,
        "locked": False,
    }
    for extra in (
        "points",
        "text",
        "fontSize",
        "fontFamily",
        "textAlign",
        "verticalAlign",
        "containerId",
        "originalText",
        "lineHeight",
        "autoResize",
        "startBinding",
        "endBinding",
        "startArrowhead",
        "endArrowhead",
    ):
        if extra in kw:
            base[extra] = kw[extra]
    return base


def _box(idx, eid, x, y, w, h, stroke, bg, text, fontsize=16, textcolor=None):
    """A rectangle plus its bound text label -> two elements."""
    tid = f"{eid}-t"
    rect = _el(
        idx,
        id=eid,
        type="rectangle",
        x=x,
        y=y,
        width=w,
        height=h,
        strokeColor=stroke,
        backgroundColor=bg,
        boundElements=[{"type": "text", "id": tid}],
    )
    txt = _el(
        idx + 1,
        id=tid,
        type="text",
        x=x + 6,
        y=y + h / 2 - fontsize / 2,
        width=w - 12,
        height=fontsize + 4,
        strokeColor=textcolor or "#1e1e1e",
        roundness=None,
        text=text,
        originalText=text,
        fontSize=fontsize,
        # Helvetica's CJK fallback keeps the editable scene readable in Chinese.
        fontFamily=2,
        textAlign="center",
        verticalAlign="middle",
        containerId=eid,
        lineHeight=1.25,
        autoResize=True,
        boundElements=None,
    )
    return [rect, txt]


def excalidraw() -> dict:
    els: list[dict] = []
    idx = 0
    # Root.
    els += _box(
        idx,
        "root",
        ROOT_X,
        ROOT_Y,
        ROOT_W,
        ROOT_H,
        "#2f9e00",
        "#f7ffe6",
        f"{ROOT_TITLE}\n{ROOT_SUB}",
        fontsize=16,
    )
    idx += 2
    for i, (label, color, steps) in enumerate(BRANCHES):
        cx = col_center(i)
        hx = cx - PILL_W / 2
        hid = f"h{i}"
        els += _box(
            idx,
            hid,
            hx,
            HEADER_Y,
            PILL_W,
            HEADER_H,
            color,
            color,
            label,
            fontsize=15,
            textcolor="#0b121f",
        )
        idx += 2
        # Root -> header arrow.
        els.append(
            _el(
                idx,
                id=f"e-root-{i}",
                type="arrow",
                x=W / 2,
                y=ROOT_Y + ROOT_H,
                width=cx - W / 2,
                height=HEADER_Y - (ROOT_Y + ROOT_H),
                strokeColor="#8a97ab",
                roundness={"type": 2},
                points=[[0, 0], [cx - W / 2, HEADER_Y - (ROOT_Y + ROOT_H)]],
                startBinding=None,
                endBinding=None,
                startArrowhead=None,
                endArrowhead=None,
                boundElements=None,
            )
        )
        idx += 1
        for j, (l1, l2, _full, _detail, _href) in enumerate(steps):
            sy = STEP_Y0 + j * STEP_PITCH
            sid = f"s{i}-{j}"
            text = f"{j + 1}. {l1}" + (f"\n{l2}" if l2 else "")
            els += _box(
                idx,
                sid,
                hx,
                sy,
                PILL_W,
                STEP_H,
                color,
                "#16233a",
                text,
                fontsize=12,
                textcolor="#d4dbe6",
            )
            idx += 2
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://github.com/Zeecka/AperiSolve",
        "elements": els,
        "appState": {"gridSize": None, "viewBackgroundColor": "#0d1522"},
        "files": {},
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "decision-tree.svg").write_text(svg(), encoding="utf-8")
    (OUT_DIR / "decision-tree.json").write_text(
        json.dumps(data(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "decision-tree.excalidraw").write_text(
        json.dumps(excalidraw(), indent=2), encoding="utf-8"
    )
    print(
        f"wrote decision-tree.svg ({W}x{H}), decision-tree.json and "
        f"decision-tree.excalidraw to {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
