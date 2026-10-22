Title: 网络与 PCAP（数据包捕获）取证速查表 - tshark（Wireshark 命令行工具）、USB（通用串行总线）、DNS（域名系统）外传
Description: 面向网络抓包类 CTF（夺旗赛）的命令清单：使用 capinfos 和 tshark 初步排查、提取文件与 HTTP 对象、解码 USB 键盘 / 鼠标 HID 数据，并发现 DNS/ICMP 外传，按常见程度排序。
NavTitle: 网络 / PCAP
Order: 50

# 网络 / PCAP 速查表 {: #network-pcap-cheatsheet }

用于 PCAP（数据包捕获）文件（`.pcap` / `.pcapng`）挑战的命令参考。捕获文件中可能包含文件、凭据，或藏在协议字段里的载荷。常用工具：capinfos（捕获文件信息查看工具）、tshark（Wireshark 命令行工具）和 tcpflow（TCP（传输控制协议）数据流提取工具）。本页还会涉及 HTTP（超文本传输协议）、USB（通用串行总线）、HID（人机接口设备）、DNS（域名系统）和 ICMP（互联网控制消息协议）。

## 初步检查 {: #triage }

```console
$ capinfos capture.pcap                 # size, packet count, time range
$ tshark -r capture.pcap -q -z io,phs   # protocol hierarchy — what's in here?
$ tshark -r capture.pcap -q -z conv,tcp # TCP conversations (endpoints, bytes)
```

在 [Wireshark（网络协议分析器）](https://www.wireshark.org/)中进行交互式检查：打开 *Statistics（统计）→ Protocol Hierarchy（协议分级）*，再使用 *Follow（跟踪）→ TCP/HTTP Stream（数据流）*。

## 提取文件与字符串 {: #extract }

```console
$ strings -n 8 capture.pcap | grep -iE 'flag|CTF|pass|user'
$ binwalk -e capture.pcap                          # embedded files in payloads
$ tshark -r capture.pcap --export-objects http,out/   # carve HTTP objects
$ tshark -r capture.pcap --export-objects smb,out/    # SMB / TFTP / IMF too
$ foremost -i capture.pcap -o carved/                 # carve by signature
```

重组单条数据流：

```console
$ tshark -r capture.pcap -qz follow,tcp,raw,0 | tr -d '\n' | xxd -r -p > stream0.bin
$ tcpflow -r capture.pcap -o flows/               # one file per direction per flow
```

## 凭据与 HTTP {: #http }

```console
$ tshark -r capture.pcap -Y http.request -T fields -e http.host -e http.request.uri
$ tshark -r capture.pcap -Y 'http.authbasic' -T fields -e http.authbasic
$ tshark -r capture.pcap -Y 'ftp.request.command==PASS' -T fields -e ftp.request.arg
```

## USB HID {: #usb }

捕获文件可能泄露按键输入和鼠标移动轨迹。

```console
# Keyboard: 8-byte HID reports on usb.capdata
$ tshark -r capture.pcap -Y 'usb.capdata && usb.data_len==8' -T fields -e usb.capdata > keys.txt
```

使用解码脚本将 HID（人机接口设备）使用编号转换为字符（可搜索“USB keyboard HID CTF decoder”）；鼠标捕获数据则可以绘制成移动轨迹图。

`--export-objects` 也支持 SMB（服务器消息块）、TFTP（简易文件传输协议）和 IMF（互联网邮件格式）等协议。

## 隐蔽信道 {: #covert }

- **DNS（域名系统）外传** → 较长或异常的子域名中可能包含 base32/十六进制数据：`tshark -r c.pcap -Y 'dns.qry.name' -T fields -e dns.qry.name | sort -u`。
- **ICMP（互联网控制消息协议）外传** → 数据可能藏在 echo 请求的负载中：`tshark -r c.pcap -Y 'icmp' -T fields -e data.data`。
- **TLS（传输层安全协议）** → 需要密钥：设置 `SSLKEYLOGFILE` / *Wireshark → Preferences（首选项）→ TLS → (Pre)-Master-Secret log（预主密钥日志）*，然后即可解密数据流。

## 无线网络 {: #wifi }

WPA（Wi-Fi Protected Access，无线网络安全协议）握手可用 aircrack-ng（无线网络握手密码破解工具）尝试恢复密码。

```console
$ aircrack-ng -w rockyou.txt capture.pcap          # crack a WPA handshake
$ tshark -r capture.pcap -Y eapol                   # confirm a 4-way handshake exists
```

## 相关内容 {: #related }

- 工具：[binwalk](/wiki/tools/binwalk) · [foremost](/wiki/tools/foremost) · [strings](/wiki/tools/strings)。
- 捕获文件中的文件：[文件与压缩包速查表](/wiki/cheatsheet/files)。
- 破解握手 / ZIP：[暴力破解速查表](/wiki/cheatsheet/brute-force)。
