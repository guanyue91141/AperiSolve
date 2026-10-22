Title: 编码与 esolang（深奥编程语言）速查表 - CyberChef（编码转换工具）、Base-N（N 进制）、Morse（摩斯电码）、QR（快速响应码）
Description: 对恢复出的 CTF（夺旗赛）载荷进行识别与解码：Base-N（N 进制）、十六进制、Morse（摩斯电码）、Braille（盲文）、QR（快速响应码）/条形码和 esoteric language（深奥编程语言），并提供 CyberChef、dcode 与命令行解码方法。
NavTitle: 编码
Order: 60

# 编码与 esolang 速查表 {: #encodings-esolangs-cheatsheet }

你已经恢复了一段内容，但它还不是 flag。先识别编码，再进行解码。本页涵盖 Base-N（N 进制编码）、hex（十六进制）、Morse（摩斯电码）、Braille（盲文）、QR（快速响应码）和 esolang（深奥编程语言）。如果不确定，可以将内容粘贴到 [CyberChef（在线数据转换工具）](https://gchq.github.io/CyberChef/)并运行 **Magic（自动识别）**操作——它能自动识别并解码下面的大多数内容。

## Base-N 与十六进制 {: #base }

```console
$ echo "SGVsbG8=" | base64 -d
$ echo "NBSWY3DP" | base32 -d
$ echo "48656c6c6f" | xxd -r -p                 # hex → bytes
$ echo "Q0lZ..." | base64 -d | xxd | head       # decode then inspect bytes
```

- **base58 / base62 / base85（ascii85/z85）** → 使用 CyberChef，或运行 `python3 -c "import base64;print(base64.b85decode(b'...'))"`。
- **未知进制的 base-N / Bacon（培根密码）/ Atbash（倒序替换密码）/ ROT-N（N 位凯撒移位）** → [dcode.fr（在线密码解码网站）](https://www.dcode.fr/) 为每种密码提供了解码器；ROT13（13 位凯撒移位）示例：`tr 'A-Za-z' 'N-ZA-Mn-za-m'`。

## 数字、Morse 与 Braille {: #symbols }

- **二进制 / 十进制 / 八进制 ASCII** → 按 8 位分组并转换；可使用 CyberChef 的 *From Binary（从二进制转换）* / *From Decimal（从十进制转换）*。
- **Morse（摩斯电码）**（`.- -...`）→ 使用 CyberChef 的 *From Morse Code（从摩斯电码转换）*，或 [dcode Morse](https://www.dcode.fr/morse-code)。
- **Braille（盲文）**（`⠓⠑⠇⠇⠕` 或 `.`/`,` 图案）→ 使用 CyberChef 的 *From Braille（从盲文转换）*。
- **长度为完全平方数的数据块** → 可能是 **QR（快速响应）码**位图；请按下方方法渲染，而不是当作文本解码。

## QR 码与条形码 {: #qr }

```console
$ zbarimg --raw code.png                    # QR / EAN / Code128 / DataMatrix
$ zbarimg --raw -q code.png | xxd | head     # inspect binary QR payloads
```

可以使用在线“二进制转 QR”工具，根据位字符串生成 QR 码；也可以使用 qrencode（QR 码生成器）/ segno（Python QR 码生成库）验证猜测。

## 密码与密钥 {: #ciphers }

- **XOR（异或，单字节 / 多字节）** → 使用 CyberChef 的 *XOR Brute Force（异或暴力破解）*，或运行 xortool（XOR 密钥分析工具）`xortool -c 20 payload.bin` 恢复密钥长度和密钥。
- **Vigenère（维吉尼亚密码）/ 替换密码** → 使用 [quipqiup（单表替换密码求解器）](https://quipqiup.com/)，或使用 dcode Vigenère 解码器（可尝试有密钥或无密钥）。

## esoteric language（深奥编程语言） {: #esolangs }

识别代码后，使用解释器运行（多数可在 [tio.run（在线代码运行环境）](https://tio.run/) 上使用）：

- **Brainfuck（符号指令编程语言）** — 仅使用 `+-<>[].,`。
- **Whitespace（空白字符编程语言）** — 仅由空格 / 制表符 / 换行符组成（可与 SNOW 检测结果相互印证）。
- **Malbolge（极难阅读的编程语言）** — 密集且难以阅读的 ASCII 字符串。
- **Piet（图像式编程语言）** — 一张“图片”：由 20 种颜色块组成（可用 `npiet` 解码）。
- **Ook! / Rockstar / Chef（基于单词的编程语言）** — 可通过 [esolangs.org 语言列表](https://esolangs.org/wiki/Language_list)识别。

!!! tip "编码可能层层嵌套"
    载荷可能经过两层包装（base64 → hex → gzip）。每次解开一层后，用 `file` / `xxd` 检查结果，再继续处理。CyberChef 的 *Magic* 搭配“Intensive mode（深度模式）”可以自动跟进多层编码。

## 相关内容 {: #related }

- 先恢复载荷：[文本速查表](/wiki/cheatsheet/text) · [图像速查表](/wiki/cheatsheet/image)。
- 方法：[方法说明 → 接近隐写术的编码](/wiki/methodology)。
