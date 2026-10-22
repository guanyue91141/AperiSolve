Title: 隐写术 CTF（夺旗赛）速查表与决策树
Description: 面向 CTF（夺旗赛）选手和数字取证人员的隐写术排查指南：按文件类型分流，提供 PNG（便携式网络图形）、JPEG（联合图像专家组格式）、GIF（图形交换格式）、音频、文本和压缩包的优先检查清单、症状到工具的速查表，以及排查无果时的检查步骤。

# 隐写术速查表 {: #cheatsheet }

<button type="button" class="wiki-print-btn" onclick="window.print()"><i class="fa fa-print"></i> 打印 / 保存为 PDF</button>

## 免责声明 {: #disclaimer }

本速查表用于帮助 CTF（夺旗赛）选手和数字取证分析人员处理常见情况。它并不涵盖现代学术隐写术与隐写分析的全部内容；仅照着此表操作，也无法让你设计出有意思的挑战 😉。有关以下排查顺序的理由，请阅读[方法说明](/wiki/methodology)。

## 决策树 {: #triage }

先用 [`file`（文件类型识别工具）](/wiki/tools/file) 识别真实文件类型，再在下方地图中选择对应分支，并从上到下依次排查——每个分支都按**常见程度排序**。详细检查清单在地图之后。

[![隐写术决策树：先识别文件类型，再按顺序检查对应分支](/static/img/cheatsheet/decision-tree.svg)](/cheatsheet/map){: .decision-map }

[打开全屏交互式地图](/cheatsheet/map){: .decision-map-cta }

*将鼠标悬停在[交互式地图](/cheatsheet/map)的步骤上，即可查看完整命令、一句话说明和工具链接；也可以将整张图下载为 PNG 或 PDF。想要自行修改？下载适用于 [Excalidraw（在线手绘图工具）](https://excalidraw.com) 的[可编辑源文件](/static/img/cheatsheet/decision-tree.excalidraw)。*

**先对每个文件执行以下检查（适用于所有文件类型）：**

- `file target` — 相信 file（文件类型识别工具）的判断，不要只看扩展名。
- `exiftool -a -u -g1 target` — 使用 exiftool（元数据查看工具）检查 Comment（注释）、Artist（作者）、GPS（全球定位系统）等字段；提取缩略图：`exiftool -b -ThumbnailImage target > thumb.jpg`。
- `strings -n 8 target` — 使用 strings（字符串提取工具）查找可读文本；对 UTF-16 文本可加 `-e l` / `-e b`。
- `binwalk target` — 使用 binwalk（文件特征扫描工具）检查文件；如果列出了第二个文件，再执行 `binwalk -e target`。

## 图像挑战 {: #image }

无损格式 PNG（便携式网络图形）、BMP（位图）的数据可能藏在像素位中；有损 JPEG（联合图像专家组格式）则可能藏在 DCT（离散余弦变换）系数里，因此使用的工具不同。**完整命令清单：**[图像速查表](/wiki/cheatsheet/image)。背景知识：[图像技术页面](/wiki/techniques/images)。

### PNG / BMP {: #png }

1. **LSB（最低有效位）文本或文件** → `zsteg -a file.png`，再用 `zsteg -E 'b1,rgb,lsb,xy' file.png > out.bin` 提取可疑结果。[zsteg（图像隐写分析工具）](/wiki/tools/zsteg)
2. **结构损坏或被编辑** → `pngcheck -vtp7 file.png`。`IHDR`（图像头数据块）中的 CRC（循环冗余校验）错误通常表示文件头被修改；宽度或高度被缩小则可能隐藏了可见区域下方的像素。使用 [PCRT（PNG 尺寸与结构修复工具）](/wiki/tools/pcrt) 修复，或根据存储的 CRC 穷举尺寸。
3. **视觉检查** → 用 [decomposer（位平面分解器）](/wiki/tools/decomposer) 或 Stegsolve（隐写图像查看工具）浏览所有位平面和**包括 Alpha（透明度）在内的每个通道**；尝试 **MSB（最高有效位）**和按列读取顺序，而不只是 RGB 的 LSB。
4. **附加数据** → 检查 `IEND` 数据块之后的内容；使用 `binwalk` / [foremost（文件雕刻工具）](/wiki/tools/foremost)，或按偏移量提取文件尾部数据。
5. **调色板技巧**（索引色 PNG）→ 使用 [Color remapping（调色板颜色映射工具）](/wiki/tools/color_remapping)打乱或重映射调色板。
6. **随机化 LSB** → 使用 [OpenStego（开源隐写工具）](/wiki/tools/openstego)：`openstego extract`。

!!! tip "检查 Alpha 通道和 MSB"
    zsteg 会报告常见组合，但载荷也可能藏在 Alpha 通道、最高有效位或按列读取的数据中——这些都是“zsteg 什么也没找到”的经典原因。请浏览全部 32 个位平面。

### JPEG {: #jpg }

JPEG 重新压缩会破坏像素 LSB，因此 [zsteg](/wiki/tools/zsteg)**不适用于**此格式。

1. **带密码的载荷** → `steghide info file.jpg`，然后执行 `steghide extract -sf file.jpg -p ''`（先试空密码）。[steghide（隐写载荷提取工具）](/wiki/tools/steghide)
2. **未知密码** → `stegseek file.jpg /usr/share/wordlists/rockyou.txt`（几秒内即可尝试 rockyou）。[stegseek（steghide 密码破解工具）](/wiki/tools/stegseek)
3. **不是 steghide** → `outguess -r file.jpg out.txt`（[OutGuess（JPEG 隐写工具）](/wiki/tools/outguess)）、`jsteg reveal file.jpg out.txt`（[jsteg（DCT 系数隐写工具）](/wiki/tools/jsteg)）或 JPHide（[jpseek（JPHide 密码搜索工具）](/wiki/tools/jpseek)）。

!!! warning "先猜密码，再进行暴力破解"
    密码可能是文件名、挑战名称、图像主体，也可能是 `strings` / `exiftool` 输出中的字符串。尝试这些线索后再使用 rockyou。

### GIF（图形交换格式）/ APNG（动态图像扩展） {: #gif }

1. **隐藏帧** → 动画可能包含持续时间为零的帧。使用 ffmpeg（音视频处理工具）提取每一帧：`ffmpeg -i file.gif -vsync 0 out/f%d.png`（或用 gifsicle（GIF 动画处理工具）执行 `gifsicle --explode`）。
2. **帧间隔中的消息** → 每帧延迟时间可能编码了摩斯电码、二进制或 ASCII（美国信息交换标准代码）。
3. **比较相邻帧** → 载荷可能藏在两张几乎相同的帧的差异中。
4. **调色板** → 使用与 PNG 相同的索引色技巧。

## 音频 {: #audio }

**完整命令清单：**[音频速查表](/wiki/cheatsheet/audio)。背景知识：[音频技术页面](/wiki/techniques/audio)。

1. **频谱图**（始终先检查）→ 在 [Audacity（音频编辑器）](https://www.audacityteam.org/)、Sonic Visualiser（音频可视化工具）或 sox（音频处理工具）`sox file.wav -n spectrogram -o spec.png` 中查看频率域。文字和 QR（快速响应）码经常会被“画”在频谱图里；也要检查 20 kHz 以上和 20 Hz 以下的范围。
2. **波形 / Morse（摩斯电码）** → 波形中明显的开关脉冲可能对应摩斯电码。
3. **WAV（波形音频格式）LSB** → `stegolsb wavsteg -r -i file.wav -o out.txt -n 1 -b 1000`。
4. **SSTV（慢扫描电视）/ DTMF（双音多频）/ FSK（频移键控）** → 用 QSSTV（慢扫描电视解码器）解码图像，用 DTMF 解码器解码电话按键音，用 minimodem（软件调制解调器）/ multimon-ng（多协议音频解码器）解码调制解调器音。
5. **带密码的容器** → 使用 [steghide（隐写载荷提取工具）](/wiki/tools/steghide)（支持 WAV/AU）或 DeepSound（音频隐写工具）。

## 视频 {: #video }

完整说明：[视频技术页面](/wiki/techniques/video)。

1. **统计流数量** → 执行 ffprobe（多媒体流信息工具）`ffprobe file.mp4` / mediainfo（媒体文件信息查看器）。额外的字幕、附件或数据轨道往往就是关键线索。
2. **提取帧** → `ffmpeg -i file.mp4 -vsync 0 out/f%05d.png`，然后对无损帧执行 PNG 检查清单（zsteg、位平面）。
3. **字幕 / 附件轨道** → `ffmpeg -i file.mkv -map 0:s:0 subs.srt`；用 `ffmpeg -dump_attachment:t "" -i file.mkv` 提取附件。
4. **音轨** → `ffmpeg -i file.mp4 -vn audio.wav`，然后先查看频谱图。
5. **元数据与尾随数据** → 检查 `exiftool`、`binwalk` 和 `moov` atom 之后的字节。

## 文本与 Unicode（统一码） {: #text }

**完整命令清单：**[文本速查表](/wiki/cheatsheet/text) · [编码与 esolang（深奥编程语言）速查表](/wiki/cheatsheet/encodings)。背景知识：[文本与 Unicode 技术页面](/wiki/techniques/text)。

1. **空白字符编码** → 行末空格或制表符。用 `cat -A file.txt` 显示，用 `stegsnow -C file.txt` 提取。[stegsnow](/wiki/tools/stegsnow)
2. **零宽字符**（U+200B/C/D）→ 不可见；用 `xxd` 或零宽字符解码器检查码点。对比 `wc -c` 与可见文本长度。
3. **形近字符**（拉丁字母 `a` 与西里尔字母 `а`）→ 使用 Irongeek（形近字符解码器）工具。
4. **编码与 esolang** → 使用 [CyberChef](https://gchq.github.io/CyberChef/) 的 *Magic*；通过 [esolangs.org](https://esolangs.org/wiki/Language_list) 查找 Brainfuck/Whitespace/Piet/Malbolge 的解释器。

## 文件与压缩包 {: #polyglot }

**完整命令清单：**[文件与压缩包速查表](/wiki/cheatsheet/files) · [密码与暴力破解速查表](/wiki/cheatsheet/brute-force) · [网络 / PCAP（数据包捕获）速查表](/wiki/cheatsheet/network)。背景知识：[文件与压缩包技术页面](/wiki/techniques/files-archives)。

1. **附加压缩包** → `unzip file.png` / `7z l file.png` 通常可以直接读取；否则执行 `binwalk -e`。[binwalk（文件特征扫描工具）](/wiki/tools/binwalk)
2. **Polyglot（多格式文件）** → 一个文件同时符合两种格式（PDF/ZIP、JPEG/ZIP、GIF/JS）。`file` 不会提示这一点；需检查多个魔数（magic number）和尾随数据。
3. **文档** → `.docx`/`.pptx`/`.jar`/`.apk` 都是 ZIP：`7z x file.docx`。PDF：`pdfdetach -list` / `pdfdetach -saveall`，并检查数据流。
4. **受密码保护的 ZIP** → 使用 fcrackzip（ZIP 密码破解工具）执行 `fcrackzip -u -D -p rockyou.txt file.zip`（ZipCrypto（ZIP 传统加密方式）较弱；AES-256（高级加密标准）则不是）。

## 症状 → 工具速查 {: #tell-tool }

根据症状直接选择相应技术。

<input type="search" id="tell-tool-filter" class="form-control form-control-sm mb-3" placeholder="筛选症状和工具…" aria-label="筛选症状与工具表" autocomplete="off">

| 症状 | 可尝试的工具 |
|---------------------------------------------|--------------------------------------------|
| 文件体积远大于可见内容 | [`binwalk -e`](/wiki/tools/binwalk) · `unzip` |
| 普通 `strings` 输出中出现类似 `CTF{` 的字符串 | [`strings -n 8`](/wiki/tools/strings)，`-e l`/`-e b` |
| EXIF Comment 异常 / 元数据可疑 | [`exiftool -a -u -g1`](/wiki/tools/exiftool) |
| PNG/BMP，元数据中没有线索 | [`zsteg -a`](/wiki/tools/zsteg) |
| LSB 位平面看起来像随机噪声 | 可能是加密 LSB，需要对应工具和密码（[cloacked-pixel…](/wiki/techniques/images#lsb-bit-planes-and-channels)） |
| 图像无法打开 / 看起来被裁切 | [`pngcheck -vtp7`](/wiki/tools/pngcheck) · [PCRT](/wiki/tools/pcrt) |
| IHDR 中出现 CRC 错误 | 修改文件头 / 穷举图像尺寸 |
| JPEG 带有密码提示 | [`steghide`](/wiki/tools/steghide) · [`stegseek rockyou`](/wiki/tools/stegseek) |
| JPEG，steghide 提取失败 | [`outguess`](/wiki/tools/outguess) · [`jsteg`](/wiki/tools/jsteg) |
| 音频文件有静态噪声 / 块状图案 | 查看高分辨率频谱图（Audacity / `sox -X -Y`） |
| 立体声音频合成为单声道后静音 | 分离 / 相减通道（`sox … remix`） |
| WAV 干净，频谱图没有发现 | `stegolsb wavsteg` |
| WAV LSB 输出全是空字节 | 跳过开头的零值；试试 `-n 1` 和 `-n 2` |
| 视频文件（mp4/mkv/avi） | [`ffprobe`](/wiki/techniques/video) → 提取帧 · 检查字幕 / 附件轨道 |
| ELF（可执行与可链接格式）/ PE（可移植可执行格式）/ Mach-O（macOS 可执行文件格式） | [steg86](/wiki/techniques/files-archives#executables-and-binaries) · 检查 section（节）/ 附加数据 |
| `.txt` 中有不可见字符 / 行尾空格 | [`stegsnow -C`](/wiki/tools/stegsnow) · `cat -A` |
| 复制文本后内容“变了” / 字母体系混杂 | 零宽字符 / 形近字符解码器 |
| 文本很短 / emoji（表情符号）似乎“装着”数据 | Tag 字符（标签字符，U+E00xx）与变体选择符解码器 |
| `.docx` / `.jar` / `.apk` | `7z x`（这些格式实际是 ZIP） |
| ZipCrypto 压缩包中有已知文件 | [bkcrack](https://github.com/kimci86/bkcrack) 已知明文攻击 |
| PDF 中有多个 `%%EOF` | `pdfresurrect -w`（恢复旧版本） |
| 文件中有 QR 码 / 条形码 | `zbarimg --raw` |
| 找到了数据块，但还没找到 flag（竞赛答案） | [CyberChef Magic](/wiki/techniques/encodings) · [dcode.fr](https://www.dcode.fr/) |
| 都不起作用，数据块格式未知 | [binvis.io（字节数据可视化网站）](http://binvis.io/) · 以原始数据导入 GIMP（GNU 图像处理程序）/Audacity |

## 卡住时检查这些项目 {: #stuck }

CTF 解题报告中经常遗漏的地方：

1. 用 `-e l` / `-e b` 重新运行 `strings`，并提取 **EXIF（可交换图像文件格式）缩略图**——它有时保留着原始的、未打码图像。
2. 用 `binwalk` / `foremost` 检查**附加压缩包**；也可以直接尝试 `unzip file.png`。
3. 浏览**每个**位平面和**每个**通道（R/G/B/**Alpha**），并尝试 **MSB**、反色和按列读取顺序，而不只是 RGB LSB。
4. 对 JPEG，始终先试**空 steghide 密码**，再用 `stegseek rockyou`；文件名 / 挑战名称 / 元数据也可能是密码。
5. 执行 `pngcheck -vtp7`——`IHDR` 中的 **CRC 错误**表示文件头可能被编辑；检查宽度 / 高度是否被缩小以隐藏像素，并根据存储的 CRC 穷举尺寸。
6. 对索引色 PNG/GIF，尝试**打乱调色板**；对 GIF/APNG 检查**零时长帧**和**帧持续时间**。
7. 音频：先看**频谱图**，再看波形中的 **Morse**，然后检查 **WAV LSB**，最后尝试 SSTV/DTMF。
8. 文本文件：寻找**行尾空格 / 制表符**以及 **Unicode 零宽字符 / 形近字符**；将 `wc -c` 与可见文本长度对比。
9. 用 Google/Yandex 反向图片搜索寻找**原始封面图**，再在 Stegsolve 中将隐写图与原图 XOR（异或）以定位编辑内容。
10. 调小媒体文件的**头部尺寸**（WAV DataSize、PNG 高度），可能会显示原本裁切掉的区域。
11. **工具要匹配载体**：steghide 支持 JPEG/BMP/WAV，但**不支持** PNG/GIF；zsteg 支持 PNG/BMP，但**不支持** JPEG。选错工具是最常见的卡点。对损坏的 PNG，先运行 `pngcheck -f` 修复，再用 zsteg；还要记住，音频 LSB 载荷经常**并非从样本 0 开始**。

## 参考资料 {: #more }

- [Aperi'Kube Blog — 隐写术](https://www.aperikube.fr/cat/steg/)
- [CTFtime — 隐写术解题报告](https://ctftime.org/writeups?tags=steg&hidden-tags=stego%2Csteganography%2Cstega%2Csteg)
- [ctf.support — 隐写术](https://ctf.support/steganography/image-steganography/)
- [StegOnline CTF 图像检查清单](https://georgeom.net/StegOnline/checklist)
- [Root-Me — 隐写术挑战](https://www.root-me.org/en/Challenges/Steganography/)
- [Corkami — 文件格式海报](http://corkami.github.io/)
