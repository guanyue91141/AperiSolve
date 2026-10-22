Title: 密码与暴力破解速查表 - stegseek（steghide 密码破解工具）、John（密码审计工具）、fcrackzip（ZIP 密码破解工具）
Description: 面向 CTF（夺旗赛）隐写和压缩包密码的命令清单：先猜密码，再进行暴力破解；使用 stegseek 处理 steghide，使用 John/hashcat 处理 ZIP/PDF/Office，另含 fcrackzip 和 bkcrack 已知明文攻击，并按成功可能性排序。
NavTitle: 暴力破解
Order: 70

# 密码与暴力破解速查表 {: #passwords-brute-force-cheatsheet }

遇到带密码的载荷时，**先猜密码，再进行暴力破解**——然后再使用密码字典。以下命令按成功可能性排序。

## 先猜密码 {: #guess }

密码通常来自以下线索；使用密码字典前，先尝试这些内容及其大小写 / leet（用相似数字和符号替换字母）变体：

- **文件名**（带或不带扩展名）和**挑战名称**；
- 图像 / 音频中的**主体**或作者；
- [`strings`](/wiki/tools/strings) / [`exiftool`](/wiki/tools/exiftool) 输出中已有的字符串；
- 空密码 `''`（这是使用 steghide（音视频隐写提取工具）时最容易漏掉的一步）。

```console
$ steghide extract -sf image.jpg -p ''                 # always try this
$ for p in "$(basename image.jpg .jpg)" "$(cat clue.txt)"; do \
    steghide extract -sf image.jpg -p "$p" && break; done
```

## 密码字典 {: #wordlists }

```console
$ ls -la /usr/share/wordlists/rockyou.txt              # the default CTF list
$ gunzip -k /usr/share/wordlists/rockyou.txt.gz        # if it's still gzipped
```

如果 rockyou（常用密码字典）无法破解，可使用 cewl（网页词汇提取工具）从网页 / 挑战文本生成定制密码字典：`cewl https://challenge.example -w words.txt`；也可以用 John（密码审计与破解工具）运行 `john --wordlist=words.txt --rules --stdout` 生成变体。

## steghide（JPEG/BMP/WAV/AU 隐写工具） {: #steghide }

```console
$ stegseek image.jpg /usr/share/wordlists/rockyou.txt   # ~seconds on rockyou
$ stegseek --seed image.jpg                              # detect payload, no wordlist
```

[stegseek（steghide 密码快速破解工具）](/wiki/tools/stegseek) 比经典工具 `stegcracker` 快得多。破解成功后，它会显示密码并写出提取的文件。

## ZIP 压缩包 {: #zip }

```console
$ zip2john secret.zip > zip.hash && john --wordlist=rockyou.txt zip.hash
$ fcrackzip -u -D -p /usr/share/wordlists/rockyou.txt secret.zip   # -u verifies
$ fcrackzip -b -c 'a1' -l 1-6 secret.zip                            # brute force
```

fcrackzip（ZIP 密码破解工具）支持字典和字符集穷举模式。

- **ZipCrypto（ZIP 传统加密方式）+ 已知压缩包内文件** → 无需破解密码，直接用 bkcrack（ZIP 已知明文攻击工具）执行已知明文攻击（参见[文件速查表](/wiki/cheatsheet/files#zip)）。

## PDF / Office / 其他 {: #other }

```console
$ pdf2john secret.pdf   > h && john --wordlist=rockyou.txt h
$ office2john secret.docx > h && john --wordlist=rockyou.txt h
$ john --show h                                        # print the cracked password
```

RAR（`rar2john`）、7z（`7z2john.pl`）、KeePass（`keepass2john`）等也有对应的 `*2john` 工具。使用 GPU（图形处理器）时，将相同哈希交给 hashcat（GPU 密码恢复工具）并选择对应模式（`hashcat --help | grep -i zip`）。

## WPA（Wi-Fi Protected Access，无线网络安全协议）握手 {: #wpa }

使用 aircrack-ng（无线网络握手密码破解工具）检查 WPA 握手：

```console
$ aircrack-ng -w rockyou.txt capture.pcap             # or hcxpcapngtool → hashcat -m 22000
```

!!! warning "知道何时应该停止"
    强加密（AES-256（高级加密标准 256 位）ZIP、现代 Office、WPA3（第三代 Wi-Fi Protected Access））无法用 rockyou 字典破解。如果密码一直无效，请重新阅读挑战描述——密钥通常可以通过线索、复用字符串或已知明文文件找到，而不是靠暴力猜出。

## 相关内容 {: #related }

- 工具：[stegseek](/wiki/tools/stegseek) · [steghide](/wiki/tools/steghide) · [strings](/wiki/tools/strings) · [exiftool](/wiki/tools/exiftool)。
- 压缩包与已知明文攻击：[文件与压缩包速查表](/wiki/cheatsheet/files)。
