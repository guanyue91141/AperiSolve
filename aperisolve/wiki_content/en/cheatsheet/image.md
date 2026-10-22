Title: 图像隐写速查表 - PNG（便携式网络图形）、JPEG（联合图像专家组格式）、GIF（图形交换格式）命令
Description: 面向图像隐写 CTF（夺旗赛）的可复制命令清单：PNG 和 BMP 的 zsteg/pngcheck/位平面方法，JPEG 的 steghide/stegseek/outguess，以及 GIF 和 APNG 的帧与调色板技巧，并按常见程度排序。
NavTitle: 图像
Order: 10

# 图像速查表 {: #image-cheatsheet }

图像挑战命令参考，按**常见程度排序**。常用工具：zsteg（图像隐写分析工具）、pngcheck（PNG 结构检查工具）、PCRT（PNG 尺寸与结构修复工具）、decomposer（位平面分解器）、Stegsolve（隐写图像查看工具）、Color remapping（调色板颜色映射工具）、OpenStego（开源隐写工具）、stegoveritas（自动化图像隐写检查工具）、steghide（隐写载荷提取工具）、stegseek（steghide 密码破解工具）、OutGuess（JPEG 隐写工具）、jsteg（DCT 系数隐写工具）、jpseek（JPHide 密码搜索工具）、stegdetect（JPEG 隐写检测器）、identify（图像信息查看工具）、gifsicle（GIF 动画处理工具）、dwebp（WebP 转换工具）、exiftool（元数据查看工具）和 ImageMagick（图像处理套件）。了解每种方法的原理，请阅读[图像技术页面](/wiki/techniques/images)；跨文件类型进行初步排查，请使用[决策树](/cheatsheet#triage)。

**首先识别真实格式——后续检查取决于文件类型：**

```console
$ file image.*
$ identify -verbose image.png | head -n 40   # GraphicsMagick/ImageMagick
```

## PNG（便携式网络图形）/ BMP（位图） {: #png-bmp }

PNG 和 BMP 是无损格式：数据可能藏在原始像素位中，因此可以使用 LSB（最低有效位）工具。

```console
$ zsteg image.png                       # common bit/channel combos
$ zsteg -a image.png                     # ALL combos: every channel, bit, order
$ zsteg -E 'b1,rgb,lsb,xy' image.png > out.bin   # extract one combo to a file
$ file out.bin && binwalk out.bin        # what did we pull?
```

```console
$ pngcheck -vtp7f image.png              # structure, CRCs, text chunks
$ zlib-flate -uncompress < idat.bin      # manually inflate a raw IDAT if needed
```

- **`IHDR` 中的 CRC 错误** → 文件头被编辑；宽度或高度被缩小则可能隐藏可见图像下方的像素行。使用 [PCRT](/wiki/tools/pcrt) 修复，或根据存储的 CRC 穷举尺寸。
- **`IEND` 之后的数据** → PNG 在 `IEND` 处结束；之后的内容都是附加数据。执行 `binwalk -e image.png`，或按偏移量提取文件尾部。
- **位平面 / 通道** → 浏览**全部 32 个位平面**（R/G/B/Alpha × 8 位），可使用[decomposer](/wiki/tools/decomposer)或 Stegsolve（*Analyse（分析）→ Data Extract（数据提取）*）。尝试 **MSB（最高有效位）**、反色和按列读取顺序，而不只是 RGB LSB。
- **索引色（调色板）PNG/BMP** → 使用 [Color remapping](/wiki/tools/color_remapping) 重映射调色板；两个颜色相近的调色板条目可能藏着一张二值图。
- **随机化 LSB（伪随机数生成器顺序）** → zsteg 无法检测；试试 [OpenStego（开源隐写工具）](/wiki/tools/openstego) 的 `extract -sf image.png`（需要密码），或运行 `stegoveritas image.png` 一次执行整套检查。

!!! tip "小心这些‘zsteg 什么也没找到’的情况"
    载荷可能藏在 **Alpha 通道**、**MSB** 或**按列读取顺序**中，这些是常见漏检原因。`zsteg -a` 能覆盖大多数情况，但仍应逐个位平面进行视觉检查。

## JPEG（联合图像专家组格式） {: #jpeg }

JPEG 是有损格式：重新压缩会破坏像素 LSB，因此 [zsteg](/wiki/tools/zsteg)**不适用**。以下工具检查的是 DCT（离散余弦变换）系数。

```console
$ steghide info image.jpg                 # is there a steghide payload?
$ steghide extract -sf image.jpg -p ''    # ALWAYS try the empty password first
$ steghide extract -sf image.jpg -p 'guess'
```

```console
$ stegseek image.jpg /usr/share/wordlists/rockyou.txt   # cracks rockyou in seconds
$ stegseek --seed image.jpg               # detect a steghide payload w/o wordlist
```

```console
$ outguess -r image.jpg out.txt           # OutGuess payload
$ jsteg reveal image.jpg out.txt          # jsteg LSB of DCT coeffs
$ stegdetect -t opjf image.jpg            # statistical: outguess/jphide/jsteg/f5
```

- **JPHide** → 使用 `jphide` / [jpseek](/wiki/tools/jpseek) 提取，或运行 `stegbreak -t p -f rockyou.txt image.jpg` 破解。
- **特殊格式 / F5** → 执行 `java -jar f5.jar x -p password image.jpg`（提取），或在[隐写分析页面](/wiki/techniques/steganalysis)查看检测工具。

!!! warning "先猜口令，再进行暴力破解"
    密码通常是**文件名**、**挑战名称**、图像**主体**，或 `strings` / `exiftool` 输出中的字符串。尝试这些线索后再用 rockyou。另请参阅[暴力破解速查表](/wiki/cheatsheet/brute-force)。

## GIF（图形交换格式）/ APNG（动态图像扩展） {: #gif }

GIF 和 APNG 可以通过帧、时序和调色板隐藏数据。

```console
$ identify image.gif                      # lists every frame + delay
$ convert image.gif -coalesce out/f%03d.png   # explode to full frames
$ ffmpeg -i image.gif -vsync 0 out/f%d.png     # alternative
$ gifsicle --explode image.gif -o frame       # frame-per-file (frame.000…)
```

- **零时长 / 隐藏帧** → 延迟为 `0` 的帧会瞬间闪过、肉眼难以察觉；检查 `identify` 输出中的 delay（延迟）列。
- **帧持续时间中的消息** → 每帧延迟可能编码了 Morse（摩斯电码）/ 二进制 / ASCII（美国信息交换标准代码）；可运行 `identify -format "%T " image.gif`。
- **比较相邻帧** → `compare f000.png f001.png diff.png` — 载荷可能存在于两张几乎相同帧的差异中。
- **调色板技巧** → 使用与 PNG 相同的索引色调色板重映射方法。

## WebP（网络图像格式）/ TIFF（标记图像文件格式）/ 其他格式 {: #other }

```console
$ dwebp image.webp -o image.png           # convert, then treat as PNG
$ exiftool -a -u -g1 image.tiff           # TIFF hides plenty in tags
$ magick image.bmp image.png              # normalise odd BMP variants
```

## 相关内容 {: #related }

- 工具：[zsteg](/wiki/tools/zsteg) · [pngcheck](/wiki/tools/pngcheck) · [PCRT](/wiki/tools/pcrt) · [decomposer](/wiki/tools/decomposer) · [Color remapping](/wiki/tools/color_remapping) · [steghide](/wiki/tools/steghide) · [stegseek](/wiki/tools/stegseek) · [OutGuess](/wiki/tools/outguess) · [jsteg](/wiki/tools/jsteg) · [jpseek](/wiki/tools/jpseek) · [OpenStego](/wiki/tools/openstego)。
- 深入阅读：[图像技术页面](/wiki/techniques/images) · [隐写分析](/wiki/techniques/steganalysis)。
