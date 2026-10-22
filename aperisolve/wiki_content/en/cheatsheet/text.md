Title: 文本与 Unicode（统一码）隐写速查表 - SNOW（空白字符隐写术）、零宽字符
Description: 面向文本隐写 CTF（夺旗赛）的可复制命令清单：空白字符/SNOW 提取、零宽字符与 Tag 字符 Unicode 隐藏、变体选择符 emoji 载荷、双向文本控制和形近字符技巧，并列出对应的检测与解码工具。
NavTitle: 文本
Order: 30

# 文本速查表 {: #text-cheatsheet }

纯文本和 Unicode（统一码）挑战的命令参考。常见迹象是**字节数大于可见文本长度**，或复制后文本内容“发生变化”。本页涵盖空白字符、Unicode 标签字符、变体选择符和双向文本控制等技巧。深入内容请参阅[文本与 Unicode 技术页面](/wiki/techniques/text)；对于恢复出的载荷，请查看[编码速查表](/wiki/cheatsheet/encodings)。

## 初步检查 {: #first }

```console
$ wc -c file.txt && wc -m file.txt        # bytes vs characters — a gap = hidden code points
$ cat -A file.txt                          # $ at line ends, ^I tabs, M-… high bytes
$ hexdump -C file.txt | less               # see the raw code points
```

## 空白字符编码（SNOW，空白字符隐写术） {: #whitespace }

数据可能藏在行末的**空格和制表符**中——大多数编辑器不会显示它们。

```console
$ cat -A file.txt                          # reveal trailing whitespace / tabs
$ stegsnow -C file.txt                      # extract, no password
$ stegsnow -p 'secret' -C file.txt          # extract with a password
```

## 零宽字符 {: #zero-width }

零宽空格（U+200B）、零宽非连接符（U+200C）和零宽连接符（U+200D）不会显示出来，但可能携带数据位。

```console
$ python3 -c "print([hex(ord(c)) for c in open('file.txt').read() if ord(c)>0x2000])"
```

在线解码：[330k 零宽字符解码器](https://330k.github.io/misc_tools/unicode_steganography.html)；受 AES（高级加密标准）保护的变体可使用 [StegCloak（Unicode 隐写工具）](https://stegcloak.surge.sh/)。

## Tag 字符与变体选择符 {: #tags }

- **Tag block（标签字符区块，U+E0000–U+E007F）** → 可用不可见字符隐藏 ASCII（美国信息交换标准代码）；每个 Tag 字符可通过屏蔽 `& 0x7F` 映射到可打印 ASCII。用于“承载”隐藏文本的 emoji（表情符号）会包含这类字符。
- **Variation selectors（变体选择符，U+FE00–U+FE0F、U+E0100–U+E01EF）** → 将字节附加到载体字符上；读取选择符索引即可解码。

```console
$ python3 -c "s=open('f.txt').read(); print(''.join(chr(ord(c)&0x7f) for c in s if 0xE0000<=ord(c)<=0xE007F))"
```

## 双向文本控制与形近字符 {: #homoglyphs }

- **Bidi（双向文本）controls（控制符，U+202A–U+202E、U+2066–U+2069）** → 调换显示顺序以隐藏 / 伪装内容；可以搜索这些码点。
- **Homoglyphs（形近字符）**（拉丁字母 `a` 与西里尔字母 `а`，U+0430）→ 文本中混用了不同字母体系；可使用 [Irongeek 形近字符解码器](https://www.irongeek.com/)，或列出非 ASCII 码点进行检查。

```console
$ grep -nP "[^\x00-\x7F]" file.txt          # any non-ASCII characters
$ python3 -c "import unicodedata as u,sys; [print(hex(ord(c)),u.name(c,'?')) for c in open('f.txt').read() if ord(c)>127]"
```

!!! tip "先标准化，再比较差异"
    `python3 -c "import unicodedata;print(unicodedata.normalize('NFKC',open('f.txt').read()))"` 会折叠形近字符和兼容字符形式；将结果与原文比较，即可准确找出被替换的字符。

## 相关内容 {: #related }

- 工具：[stegsnow（空白字符隐写提取工具）](/wiki/tools/stegsnow) · [strings（字符串提取工具）](/wiki/tools/strings)。
- 深入阅读：[文本与 Unicode 技术页面](/wiki/techniques/text)。
- 解码结果：[编码与 esolang 速查表](/wiki/cheatsheet/encodings)。
