# AI DS6064 USB-TMC Bridge

这个工程把本地 RIGOL DS6064 示波器封装成一条可被 Codex/AI 安全调用的测量链路：

```text
用户自然语言
-> Codex / AI agent
-> rigol-ds6064-scope skill
-> Python JSON CLI
-> PyVISA + NI-VISA
-> USB-TMC
-> RIGOL DS6064
-> 测量值 / CSV / PNG / manifest
-> AI 工程分析结论
```

当前重点是把 AI 接入示波器的基础设施打通并稳定下来，而不是做复杂上层应用。工程默认只支持 USB-TMC，不实现 LAN/TCPIP 路径。

## 当前状态

已在真机上验证通过：

```text
Device: RIGOL TECHNOLOGIES,DS6064,DS6C134300118,00.01.03.SP01
CH1 frequency: 20000.0 Hz
CH2 frequency: 20000.0 Hz
CH3 frequency: 20000.0 Hz
```

最近一次三通道采集证据包：

```text
outputs/csv/20260711_160032_CH1_CH2_CH3_multi.csv
outputs/images/20260711_160032_CH1_CH2_CH3_multi.png
outputs/manifests/20260711_160032_CH1_CH2_CH3_multi.json
```

已完成的关键能力：

- 安全 JSON CLI：`list`、`idn`、`health`、`probe-open`、`summary`、`freq`、`period`、`duty`、`vpp`、`capture`、`capture-multi`、`latest`、`diagnose-channel`、`analyze-pwm`。
- 使用 DS6064 内置测量引擎读取频率、周期、占空比和 Vpp。
- 使用 BYTE 波形读取保存单通道/多通道 CSV、PNG 和 manifest。
- 使用文件锁和 watchdog 防止 AI 并发调用把 USB-TMC 会话卡住。
- 封装 skill：项目根目录 `SKILL.md` 和 `.agents/skills/rigol-ds6064-scope/SKILL.md`。

## 目录结构

```text
.
|-- SKILL.md
|-- README.md
|-- requirements.txt
|-- .env.example
|-- docs/
|   `-- CLI_CONTRACT.md
|-- src/
|   |-- rigol_ds6064.py
|   |-- scope_cli.py
|   |-- safety.py
|   `-- waveform_analysis.py
|-- tests/
|   `-- test_offline_parser.py
|-- outputs/
|   |-- csv/
|   |-- images/
|   |-- logs/
|   `-- manifests/
`-- .agents/skills/rigol-ds6064-scope/
    |-- SKILL.md
    |-- scripts/scope_cli.py
    `-- references/DS6000_SCPI_NOTES.md
```

`outputs/csv`、`outputs/images`、`outputs/manifests` 中的采集产物默认被 `.gitignore` 忽略。`outputs/chm_extract/` 是从编程手册 CHM 解包出的临时资料，也被忽略，不属于源码交付面。

## 环境要求

- Windows 主机。
- RIGOL DS6064 后面板 USB DEVICE 口连接电脑。
- Python 3.10+。
- 当前版本 NI-VISA。旧版 NI-VISA 可能出现 `list` 能看到资源但 `open_resource` 卡住的问题。
- Python 依赖见 `requirements.txt`。

推荐配置文件：

```env
RIGOL_CONNECTION=USB
RIGOL_SCOPE_RESOURCE=USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
RIGOL_SCOPE_TIMEOUT_MS=20000
RIGOL_DEFAULT_CHANNEL=CHANnel1
RIGOL_CLEAR_ON_CONNECT=0
RIGOL_VISA_ACCESS_MODE=no_lock
RIGOL_VISA_LIBRARY=auto
RIGOL_CLI_TIMEOUT_MS=30000
RIGOL_LOCK_TIMEOUT_MS=5000
```

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

如果已经存在 `.env`，不要覆盖它，确认其中的 `RIGOL_SCOPE_RESOURCE` 和真机 VISA 资源一致即可。

## 常用命令

所有命令都从项目根目录运行。优先使用虚拟环境里的 Python：

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py --help
```

链路检查：

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py list
.\.venv\Scripts\python.exe src\scope_cli.py probe-open --query-idn --open-timeout-ms 5000
.\.venv\Scripts\python.exe src\scope_cli.py health --channels CHANnel1 CHANnel2 CHANnel3 --points 64
.\.venv\Scripts\python.exe src\scope_cli.py idn
```

读内置测量值：

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py freq --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py period --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py duty --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py vpp --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py summary --channel CHANnel1
```

采集波形：

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py capture --channel CHANnel1 --points 1200
.\.venv\Scripts\python.exe src\scope_cli.py capture-multi --channels CHANnel1 CHANnel2 CHANnel3 --points 1200
.\.venv\Scripts\python.exe src\scope_cli.py latest
```

PWM 分析：

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py analyze-pwm --channel CHANnel1 --points 1200 --save
.\.venv\Scripts\python.exe src\scope_cli.py analyze-pwm-file --csv outputs\csv\<capture>.csv
```

异常通道诊断：

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py diagnose-channel --channel CHANnel3 --points 1200
```

## AI 调用约定

所有 CLI 输出都是 JSON：

```json
{"ok": true, "data": {}}
```

或：

```json
{"ok": false, "error": "message"}
```

AI agent 应先解析 `ok`，不要依赖 stderr 做机器判断。文件型命令会返回 `manifest_path`，并刷新 `outputs/manifests/latest.json`。给其他 AI 交接波形时，优先传 manifest，再附 PNG 和 CSV。

直接问“频率多少”“占空比多少”“Vpp 多少”时，优先调用 DS6064 内置测量命令。CSV 推导值只能作为辅助或失败回退，和内置测量不一致时应明确标注“波形估算”。

多通道时序关系分析优先使用：

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py capture-multi --channels CHANnel1 CHANnel2 CHANnel3 --points 1200
```

## 安全边界

默认 AI 流程只允许读取、采集、保存 CSV/PNG/manifest 和离线分析。不要自动改变电机、电源、电池、高压等外部实验硬件状态。

`autoscale` 会改变示波器显示/测量状态，只有用户明确允许或排障确实需要时才使用。

危险 SCPI 默认拦截：

```text
*RST
:STOR
:SAVE
:LOAD
:DISK
:SYSTem:SECure
```

## USB-TMC 排障经验

USB-TMC 是测试测量仪器协议，不是普通串口。常见卡住原因和处理方式：

| 原因 | 现象 | 处理方式 |
|---|---|---|
| Ultra Sigma / NI MAX / Python 同时占用 | 打不开设备或 query 卡住 | Python 测试时关闭其他 VISA 工具 |
| 查询命令没有读取返回值 | 后续命令超时 | 带 `?` 的 SCPI 必须用 query/read 路径消费回复 |
| 波形点数太大 | `:WAVeform:DATA?` 超时 | 先用 `--points 1200`，稳定后再增大 |
| timeout 太短 | 读取波形超时 | 保持 `RIGOL_SCOPE_TIMEOUT_MS=20000`、`RIGOL_CLI_TIMEOUT_MS=30000` |
| AI 并发调用 | 偶发卡死、设备占用 | CLI 已加锁；不要并行执行示波器命令 |
| 频繁 open/close 不稳定 | 偶发无法打开会话 | 后续可把同一 CLI 合同放到常驻 `scope_server.py` 队列后面 |
| USB 省电 | 长时间后设备消失 | 关闭 Windows USB 选择性暂停 |
| VISA 后端旧或异常 | `list` 能看到但 `open_resource` 卡住 | 更新 NI-VISA；必要时用 `probe-open` 对比 `visa32.dll` / `visa64.dll` |

本项目之前遇到过旧 NI-VISA Runtime 5.4.1 的问题：资源枚举能成功，但 `open_resource_start` 后卡住，NI MAX 的 Devices and Interfaces 也会一直转圈。更新到最新版 NI-VISA 后，`*IDN?` 和 Python/PyVISA 访问恢复正常。

## 验证

离线验证：

```powershell
.\.venv\Scripts\python.exe -m compileall src tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

真机验证：

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py probe-open --query-idn --open-timeout-ms 5000
.\.venv\Scripts\python.exe src\scope_cli.py health --channels CHANnel1 CHANnel2 CHANnel3 --points 64
.\.venv\Scripts\python.exe src\scope_cli.py capture-multi --channels CHANnel1 CHANnel2 CHANnel3 --points 1200
```

## 文档说明

- [SKILL.md](SKILL.md) 是给 Codex/AI agent 使用的根目录 skill。
- [.agents/skills/rigol-ds6064-scope/SKILL.md](.agents/skills/rigol-ds6064-scope/SKILL.md) 是 Codex skill 目录版本。
- [docs/CLI_CONTRACT.md](docs/CLI_CONTRACT.md) 是更详细的 JSON CLI 合同。
- `DS6000_Datasheet_EN.pdf` 和 `DS6000_ProgrammingGuide_EN.chm` 是原厂资料，默认忽略，不纳入 Git 源码交付。
