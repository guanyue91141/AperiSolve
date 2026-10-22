Title: 音频隐写速查表 - 频谱图、WAV（波形音频格式）LSB（最低有效位）、SSTV（慢扫描电视）
Description: 面向音频隐写 CTF（夺旗赛）的命令清单：优先查看频谱图、立体声与相位技巧、WAV 样本 LSB、SSTV（慢扫描电视）/DTMF（双音多频）/FSK（频移键控）信号解码以及带密码的容器，并按常见程度排序。
NavTitle: 音频
Order: 20

# 音频速查表 {: #audio-cheatsheet }

音频挑战命令参考，按**常见程度排序**。背景知识请阅读[音频技术页面](/wiki/techniques/audio)。

**先查看频率域，再检查字节。**

本页常用 sox（音频处理工具）和 ffmpeg（音视频处理工具）生成频谱图。

## 频谱图（先检查） {: #spectrogram }

文字和 QR（快速响应）码经常会被“画”在频谱图里；也要查看 20 kHz 以上和 20 Hz 以下的范围。

```console
$ sox audio.wav -n spectrogram -o spec.png        # quick spectrogram
$ sox audio.wav -n spectrogram -X 500 -y 1025 -o spec.png   # higher resolution
$ ffmpeg -i audio.wav -lavfi showspectrumpic=s=1280x720 spec.png
```

交互式检查：在 [Audacity（音频编辑器）](https://www.audacityteam.org/)中打开文件并切换到 *Spectrogram（频谱图）*轨道视图，或使用 Sonic Visualiser（音频可视化工具），然后放大频率轴。

## 波形、通道与相位 {: #waveform }

```console
$ audacity audio.wav          # eyeball the waveform for Morse on/off bursts
```

- **立体声通道技巧** → 载荷可能只在一个声道中，也可能存在于两个声道的*差值*中。可在 Audacity 中分离 / 相减通道，也可以执行：

```console
$ sox audio.wav left.wav remix 1        # left channel only
$ sox audio.wav right.wav remix 2       # right channel only
$ sox audio.wav mono.wav remix 1,2      # sum (a phase-cancelled payload vanishes)
```

- **反向 / 慢放** → 隐藏语音可能被反转或拉伸时长：`sox audio.wav rev.wav reverse`，或在 Audacity 中调整 *Tempo*（速度）。

## 样本 LSB（最低有效位，WAV 波形音频格式） {: #wav-lsb }

```console
$ stegolsb wavsteg -r -i audio.wav -o out.bin -n 1 -b 1000   # 1 LSB, 1000 bytes
$ file out.bin
```

WavSteg（WAV 隐写工具）来自 `stego-lsb` 软件包（`pip install stego-lsb`）。如果输出是乱码，可调整 `-n`（每个样本使用的位数）和 `-b`（字节数）。

## 信号解码：SSTV（慢扫描电视）/ DTMF（双音多频）/ FSK（频移键控）/ Morse（摩斯电码） {: #signalling }

```console
$ multimon-ng -a MORSE_CW -a DTMF -a FSK -t wav audio.wav   # decode many at once
$ minimodem --rx 1200 < audio.wav          # Bell/FSK modem tones (try 300/1200)
```

- **SSTV**（通过音频传图）→ 使用 [QSSTV（SSTV 图像解码器）](https://www.qsl.net/on4qz/) 解码（将音频输入虚拟麦克风），或执行 `pip install sstv` → `sstv -d audio.wav -o out.png`。
- **DTMF**（电话按键音）→ 执行 `multimon-ng -a DTMF`，或使用在线 DTMF 解码器。
- **Morse** → 波形中明显的开关脉冲可能对应摩斯电码；可执行 `multimon-ng -a MORSE_CW`。

## 受密码保护的容器 {: #containers }

steghide（音视频隐写提取工具）支持 WAV/AU 容器。

```console
$ steghide extract -sf audio.wav -p ''     # steghide supports WAV/AU
```

- **DeepSound（音频隐写工具）** → 一款 Windows 工具；可提取 / 挂载其容器，或使用社区提取工具。`strings`（字符串提取工具）输出中的魔数字符串 `DSCF` 可能表明这是 DeepSound 文件。

## WAV 文件头技巧 {: #header }

- 如果 WAV 文件头中的 **DataSize** 被缩小，声明终点之后的样本会被隐藏；编辑该尺寸字段（或设为 `0xFFFFFFFF`），然后重新打开文件查看隐藏内容。
- 原始数据导入：*Audacity → File → Import → Raw Data* 会把无文件头的数据块解释为 PCM（脉冲编码调制）；当 `file` 显示“data”时可以尝试。

## 相关内容 {: #related }

- 工具：[steghide](/wiki/tools/steghide) · [strings](/wiki/tools/strings)。
- 深入阅读：[音频技术页面](/wiki/techniques/audio) · [编码速查表](/wiki/cheatsheet/encodings)（用于解码载荷）。
