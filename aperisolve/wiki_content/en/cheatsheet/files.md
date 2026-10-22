Title: 文件与压缩包隐写速查表 - 文件雕刻、多格式文件、ZIP（压缩包格式）
Description: 面向文件结构类 CTF（夺旗赛）挑战的命令清单：使用 binwalk/foremost 检查附加数据并雕刻文件，识别多格式文件，提取 ZIP/Office/PDF 内容，以及使用 bkcrack 对 ZIP 执行已知明文攻击，并按常见程度排序。
NavTitle: 文件 / 压缩包
Order: 40

# 文件与压缩包速查表 {: #files-archives-cheatsheet }

先把文件当作一种**数据结构**检查，再处理像素或采样值。很多所谓的“隐写”挑战其实是文件格式技巧。本页常用工具：file（文件类型识别工具）、binwalk（文件特征扫描工具）、foremost（文件雕刻工具）和 bkcrack（ZIP 已知明文攻击工具）。背景知识请阅读[文件与压缩包技术页面](/wiki/techniques/files-archives)；密码处理请看[暴力破解速查表](/wiki/cheatsheet/brute-force)。

## 附加与嵌入数据 {: #appended }

```console
$ file target
$ tail -c 200 target | xxd            # inspect the trailer
$ binwalk target                       # list embedded signatures
$ binwalk -e target                    # auto-extract known signatures
$ foremost -i target -o out/           # header/footer carving when binwalk misses
```

经典情况：图像后面拼接了 ZIP（压缩包格式）。`unzip` 会从文件**末尾**读取中央目录，因此往往可以直接打开：

```console
$ unzip target          # or: 7z x target
$ 7z l target           # list contents without extracting
```

## Polyglot（多格式文件） {: #polyglot }

一个文件同时符合两种解析器的格式（PDF（便携式文档格式）/ZIP、JPEG/ZIP、GIF/JS）。`file` 只读取文件开头，所以**不会**自动标记这种情况。

```console
$ binwalk target                       # multiple signatures at nonzero offsets
$ xxd target | grep -iE '25504446|504b0304|ffd8ff|47494638'   # PDF/ZIP/JPEG/GIF magic
```

可以使用 [mitra（多格式文件构造工具）](https://github.com/corkami/mitra) 或 [truepolyglot（多格式文件测试工具）](https://github.com/ansemjo/truepolyglot) 构造 / 验证多格式文件；Corkami（文件格式研究项目）的[海报](https://github.com/corkami/pics)展示了各文件格式允许哪些位置包含无关数据。

## ZIP 压缩包 {: #zip }

```console
$ 7z l target.zip                      # list; note encryption + compression method
$ unzip -l target.zip
```

- **受密码保护** → 查看[暴力破解速查表](/wiki/cheatsheet/brute-force)（`zip2john` + `john`，或 `fcrackzip`）。
- **ZipCrypto + 已知压缩包内文件** → 执行已知明文攻击，无需密码：

```console
$ bkcrack -L target.zip                # list entries + which are ZipCrypto
$ bkcrack -C target.zip -c secret.txt -P plain.zip -p plain.txt   # recover keys
$ bkcrack -C target.zip -k KEY0 KEY1 KEY2 -d out.txt              # decrypt
```

- **AES-256（高级加密标准）ZIP** → 不受 bkcrack 已知漏洞影响；只能尝试暴力破解。

## 文档（Office 办公套件 / PDF / Java / Android） {: #documents }

`.docx` / `.pptx` / `.xlsx` / `.jar` / `.apk` 都是 ZIP 压缩包——解压后检查内容。

```console
$ 7z x report.docx -o docx/            # media/, embeddings/, and XML parts
$ grep -rInE 'flag|CTF|http' docx/
$ unzip -o app.apk -d apk/ && cat apk/AndroidManifest.xml
```

PDF 文件：

```console
$ pdfdetach -list target.pdf && pdfdetach -saveall target.pdf   # attachments
$ pdf-parser --search flag target.pdf          # objects/streams
$ pdfresurrect -w target.pdf                    # recover overwritten revisions
$ mutool extract target.pdf                      # dump embedded images/fonts
```

## 其他容器 {: #other }

- **SVG（可缩放矢量图形）** → 它是 XML；`<script>` 或画布外的 `<text>` 可能藏有 flag——请检查源代码，而不只是渲染结果。
- **NTFS ADS（NTFS 备用数据流）** → 在 Windows 中运行 `dir /R`，或使用 `getfattr` / `7z` 查看备用数据流。
- **`.git`** → `git log -p`、`git stash list` 和未引用对象（`git fsck --lost-found`）中可能藏有历史内容。

## 相关内容 {: #related }

- 工具：[binwalk](/wiki/tools/binwalk) · [foremost](/wiki/tools/foremost) · [file](/wiki/tools/file) · [strings](/wiki/tools/strings)。
- 深入阅读：[文件与压缩包技术页面](/wiki/techniques/files-archives)。
- 密码：[暴力破解速查表](/wiki/cheatsheet/brute-force)。
- 数据包捕获：[网络 / PCAP 速查表](/wiki/cheatsheet/network)。
