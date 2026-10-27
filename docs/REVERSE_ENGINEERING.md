# 通用双模蓝牙 RCSP 架构墨水屏词卡协议与二进制容器技术手册
# Generic Dual-Mode BLE RCSP E-Ink Word Card Protocol & Binary Container Reference

> ### ⚠️ 技术学习与互操作性研究声明 (Educational & Interoperability Disclaimer)
> 1. 本文档仅用于**嵌入式低功耗蓝牙 (BLE GATT) 协议学习、串行控制状态机 (RCSP) 机制研究、二进制数据容器分析，以及个人合法持有硬件的互操作性（Interoperability）研究**。
> 2. 文中描述的所有状态机步骤、数据结构与密码学流程均通过标准黑盒协议交互分析与个人设备合法导出样本比对得出，所有配套源码均为从零编写的独立实现（Clean-Room Implementation），**不包含任何第三方受版权保护的闭源 SDK、固件镜像或商业词库**。
> 3. 本文档及配套代码按“原样 (AS IS)”提供，严禁用于任何商业用途或侵犯第三方合法权益的行为。任何基于本文档进行的操作风险由操作者自行承担。

---

## 1. Stage 1：物理层架构与 BLE GATT 通道发现

### 1.1 物理接口排障（纯供电 USB 端口识别）
- **实测现象**：通过全功能 Type-C 数据线将设备连接至计算机，监控 `dmesg -w` 与 `lsusb` 均无任何 USB 设备枚举事件。
- **硬件架构结论**：该类便携墨水屏词卡的 Type-C 母座仅焊接电源线（VBUS/GND）至锂电池充电管理芯片，未连接主控 SoC 的 USB D+/D- 差分引脚。所有固件交互、词卡容器下发与学习记录同步均通过 **双模蓝牙 SoC 的 BLE GATT 通道**完成。

### 1.2 BLE 广播与 GATT 特征值 (Characteristics)
- **广播名称特征**：默认以固定前缀（如 `YDW:`）加设备序列号对外广播，同时广播主服务 UUID `0xAE00`。
- **主服务与特征 UUID 定义**：

| 通道名称 | UUID | 属性 (Properties) | 作用说明 |
| :--- | :--- | :--- | :--- |
| **RCSP Primary Service** | `0000ae00-0000-1000-8000-00805f9b34fb` | Primary Service | 串行控制协议主服务 |
| **TX (Host -> Card)** | `0000ae01-0000-1000-8000-00805f9b34fb` | `Write Without Response` (`0x04`) | 主机向设备写入裸握手包或 RCSP 命令帧 |
| **RX (Card -> Host)** | `0000ae02-0000-1000-8000-00805f9b34fb` | `Notify` (`0x10`) | 设备向主机推送握手应答、RCSP 响应与主动拉取命令 |

---

## 2. Stage 2：链路层 6 步挑战-应答握手与会话状态机激活

### 2.1 Silent Drop 陷阱 #1：为什么连接 BLE 后直接发送 RCSP 帧全部超时？
连接 `0xAE01` 并订阅 `0xAE02` Notify 后，固件处于 **Unauthenticated（未认证隔离态）**。此时任何以 `FE DC BA` 开头的标准 RCSP 帧都会被固件底层静默丢弃，且超时后固件会主动断开 BLE 连接。

主机必须先在 `0xAE01` / `0xAE02` 上直接收发**不含 RCSP 封包头的裸字节流**完成 6 步双向挑战-应答握手：

| 步骤 | 方向 | 长度 | 字节内容 | 含义 |
| :---: | :---: | :---: | :--- | :--- |
| **Step 1** | Host -> Card (`0xAE01`) | 17 B | `0x00` + `R_h[0..15]` | 主机发送 16 字节随机挑战 `R_h` |
| **Step 2** | Card -> Host (`0xAE02`) | 17 B | `0x01` + `E(R_h)[0..15]` | 固件返回加密后的应答 `E(R_h)` |
| **Step 3** | Host -> Card (`0xAE01`) | 5 B | `02 70 61 73 73` (`\x02pass`) | 主机验证固件应答通过并发送确认码 `pass` |
| **Step 4** | Card -> Host (`0xAE02`) | 17 B | `0x00` + `R_d[0..15]` | 固件向主机发起 16 字节随机挑战 `R_d` |
| **Step 5** | Host -> Card (`0xAE01`) | 17 B | `0x01` + `E(R_d)[0..15]` | 主机计算并返回 `E(R_d)` |
| **Step 6** | Card -> Host (`0xAE02`) | 5 B | `02 70 61 73 73` (`\x02pass`) | 固件验证通过，返回 `\x02pass`，解锁 RCSP 通道 |

### 2.2 链路层双相置换分组密码算法规范
通用双模蓝牙 SoC 家族常见的链路层认证存在两种算法变体：
1. **流密码变体（通用音频外设常见）**：
   - 采用 8 字节常量种子 `[254, 237, 250, 206, 202, 254, 186, 190]`（`FE ED FA CE CA FE BA BE`）结合线性同余发生器（`v = (v * 16807) % 0x7FFFFFFF`）派生密钥，并调用 **8 轮 Salsa20 流密码**加密挑战块。
2. **8 轮双相 S-Box / Fibonacci 置换分组密码（本墨水屏词卡 SoC 实际采用）**：
   - `ydw012_cli.py` 中通过纯 Python 完整实现了该双相分组密码（`function_e1test`）：
     - **16 字节静态根密钥 (`STATIC_KEY`)**：`06 77 5F 87 91 8D D4 23 00 5D F1 D8 CF 0C 14 2B`
     - **6 字节常量盐 (`MAGIC`)**：`4D 69 76 47 39 58` (ASCII `"MivG9X"`)
     - **密钥扩展 (`_key_schedule`)**：基于 256 字节非线性表 `KS_TABLE` 将 16 字节密钥扩展为 9 组共 144 字节轮密钥（`w[0..143]`）。
     - **Phase 1（派生动态会话密钥）**：以 `STATIC_KEY` 为初始密钥，将随机挑战前 8 字节重复拼接（`R[0..7] + R[0..7]`）作为 16 字节输入块，执行 8 轮正向 `SBOX` 查表、Fibonacci 模乘置换 (`idx = (i + i*34) & 15`) 与列混淆循环左移，输出 16 字节动态密钥 `round_key`。
     - **Phase 2（计算挑战密文）**：以 `round_key` 扩展出的轮密钥，对 `R[8..15] + MAGIC[0..5] + R[8..9]` 构成的 16 字节块执行 8 轮逆向 `ISBOX` 查表与逆列混淆循环右移，最终输出 16 字节密文 `E(R)`。

---

## 3. RCSP 协议帧格式与会话状态机解锁 (`GetTargetInfoCmd 0x03`)

### 3.1 标准 RCSP 帧结构
链路层 6 步握手通过后，`0xAE01` 与 `0xAE02` 上的所有数据包均采用大端序 (Big-Endian) RCSP 帧格式封装：

```text
+------------+--------+--------+---------------+------------+------------------+------+
| Start Flag | Flags  | OpCode | Param Length  | SeqNum(SN) | Payload / Params | End  |
| FE DC BA   | 1 Byte | 1 Byte | 2 Bytes (BE)  | 1 Byte     | N Bytes          | EF   |
+------------+--------+--------+---------------+------------+------------------+------+
```

- **Flags 字节标志位**：
  - `0xC0` (`bit7=1, bit6=1`)：需要接收方回复 Response 的 Command 帧（`Param Length = 1 + len(param)`，首字节为 `SN`）。
  - `0x80` (`bit7=1, bit6=0`)：无需回复 Response 的流式 Command 帧（如 `OpCode=0x01` 大文件数据分片推送，`Param Length = 1 + len(param)`）。
  - `0x00` (`bit7=0, bit6=0`)：Response 响应帧（`Param Length = 2 + len(param)`，前 2 字节分别为 `Status (0=成功)` 和对应的请求 `SN`）。

### 3.2 Silent Drop 陷阱 #2：为什么握手成功后发送 `0xFF` 或 `0x0C` 依然超时？
- **问题现象**：收到 Step 6 的 `02 70 61 73 73` 后，若直接发送扩展业务指令 `0xFF` 或文件浏览指令 `0x0C`，固件仍然静默丢弃。
- **根因与解决方案**：固件在链路层握手完成后，要求主机发送的第一条 RCSP 指令必须是 **`GetTargetInfoCmd (OpCode=0x03)`**，以完成协议栈初始化并上报存储介质句柄：
  - **请求帧**：`FE DC BA C0 03 00 06 01 FF FF FF FF 00 EF`
    - `mask = 0xFFFFFFFF`（请求全部设备特性 TLV）
    - `platform = 0x00`（主机平台标志）
  - **响应帧**：`FE DC BA 00 03 00 41 00 01 ... EF`（`status=0`，返回 63 字节 TLV 设备能力描述，其中指明外置/内置 Flash 存储句柄 `devHandler = 1`）。

---

## 4. Stage 3：FAT 文件系统目录浏览 (`0x0C`/`0x0D`) 与按簇无损读取 (`0x24`)

### 4.1 目录浏览 (`StartFileBrowseCmd 0x0C`)
用于遍历设备内置 Flash FAT 文件系统中的目录结构、文件名与 **起始簇号 (`cluster`)**：
- **请求参数格式**：
  ```python
  path_bytes = b"".join(struct.pack(">I", c) for c in path_clusters) # 根目录为 [0]
  param = struct.pack(">BBHIH",
      0,                # path_type: 0 = 目录浏览
      read_num,         # 单次读取条目上限 (如 10)
      start_idx,        # 起始索引 (1-based: 1, 2, 3...)
      dev_handler,      # 存储介质句柄: 1
      len(path_bytes)   # 路径簇号数组字节长度
  ) + path_bytes
  ```
- **响应与数据流解析**：
  1. 固件首先回复 `Resp 0x0C (status=0)`；
  2. 随后通过 `Cmd 0x01 (xm_opcode=0x0C)` 推送目录项字节流：
     - `byte[0]`：`flags`（`bit0`: `0`=目录, `1`=文件；`bit1`: `0`=UTF-16LE, `1`=ANSI/GBK）
     - `byte[1..4]`：`>I` Big-Endian **文件/目录起始簇号 (`cluster`)**
     - `byte[5..6]`：`>H` Big-Endian 文件编号 `file_num`
     - `byte[7]`：文件名长度 `name_len`
     - `byte[8..8+name_len]`：文件名或目录名字节
  3. 推送完毕后固件发送 `Cmd 0x0D (StopFileBrowseCmd, reason)`，主机回复 `Resp 0x0D (status=0)` 即可。

### 4.2 按簇号无损导出文件 (`ReadFileFromDeviceCmd 0x24`)
获取任意目标文件（如 `/O/513/513.CAD`）的簇号 `cluster` 后，可通过 `OpCode=0x24` 将其完整导出：
1. **启动读取请求**：
   - `param = struct.pack(">BIII", 0x01, dev_handler=1, offset=0, cluster)`
2. **固件响应文件总长度**：
   - `Resp 0x24` 返回 `status=0` 及 4 字节大端文件总字节数 `file_size = struct.unpack(">I", payload[:4])[0]`。
3. **流式分包接收 (`OpCode=0x01, xm_opcode=0x24`)**：
   - 每包负载格式：`offset (4B BE)` + `pkt_crc16 (2B BE)` + `chunk`。
   - 校验方式：采用累加式 **CRC16-XMODEM**（初值 `0`，每收到一包执行 `running_crc = crc16_xmodem(chunk, running_crc)` 并与 `pkt_crc16` 比对）。
4. **结束确认**：
   - 全部字节传输完成后，固件发送 `Cmd 0x24 (sub_op=0x80)`，主机回复 `Resp 0x24 (status=0, param=0x80)` 完成导出。

---

## 5. Stage 4：存储句柄绑定与设备驱动型大文件上传状态机 (`0x21`/`0x27`/`0x1B`/`0x20`/`0x1D`/`0x1C`)

### 5.1 Pitfall #3：为什么 `StartLargeFileTransfer (0x1B)` 会返回 `status=1` 失败？
若仅发送 `NotifyPrepareEnv (0x21, param=0x00)` 就直接发送 `0x1B`，固件因未绑定目标存储介质句柄，必定返回 `status=1` 拒绝写入。
正确的处理步骤是在 `0x21` 之后、`0x1B` 之前发送 **`DeviceExtendParamCmd (OpCode=0x27)`**：
```python
# op=0x00 (大文件传输扩展参数), dev_handler=1 (内置 Flash FAT 分区), has_crc16=0
ext_param = struct.pack(">BIB", 0x00, 1, 0)
```
收到 `Resp 0x27 (status=0)` 后，再发送 `StartLargeFileTransfer (0x1B)`：
```python
file_crc = crc16_xmodem(file_bytes)
hash_bytes = f"{file_crc:04x}{len(file_bytes)&0xFFFF:04x}.tmp\x00".encode("ascii") # 13 字节临时名
start_param = struct.pack(">IH", len(file_bytes), file_crc) + hash_bytes
```
此时固件立即返回 `status=0` 及协商后的分片大小 `transfer_mtu = 512`（`>H`）！

### 5.2 Pitfall #4：`LargeFileTransferGetNameCmd (0x20)` 的 8.3 短文件名编码规则
固件接受 `0x1B` 后，会主动向主机下发 `Cmd 0x20` 请求目标文件名。
对于主文件名长度 `< 9` 字节且扩展名 `< 5` 字节的标准 **8.3 短文件名**（如 `901.cad`、`901.rev`），**不得添加 `\U` 前缀或使用 UTF-16LE 编码**，必须直接返回 GBK 编码加双零字节结尾：
```python
name_bytes = filename.encode("gbk") + b"\x00\x00"
# 例如 "901.cad" -> 39 30 31 2e 63 61 64 00 00
```
固件收到 `"901.cad\x00\x00"` 后，会自动解析词书编号 `901` 并在 FAT 文件系统中创建 `/O/901/901.CAD`。

### 5.3 Pitfall #5：固件 `0x1D` 偏移量乱序拉取机制（断电安全文件头最后写入）
文件名确认后，固件通过 `LargeFileTransferOpCmd (0x1D)` 主动向主机拉取数据窗口：
- 请求格式：`op (1B, 0=请求数据)` + `buf_size (2B BE, 通常为 4096)` + `offset (4B BE)`。
- **关键机制发现**：固件**并非从 `offset=0` 顺序拉取**！以 `901.cad` (50,164 B) 为例，固件的实际拉取顺序为：
  1. `offset = 512, buf_size = 4096`
  2. `offset = 4608, buf_size = 4096`
  3. ... 依次拉取至文件末尾 `offset = 49664, buf_size = 4096`
  4. **最后一次请求**：`offset = 0, buf_size = 512`！
- **工程设计原理**：固件特意将文件前 512 字节（包含 `.CAD` / `.REV` Header）留到最后一步写入（Atomic Header Commit）。若蓝牙传输中途断电或断连，Flash 上的文件头部仍为未初始化状态，避免重启时加载半截损坏词书导致系统异常。
- **主机响应实现**：主机收到 `0x1D` 后，严格按请求的 `offset` 与 `buf_size` 切片 `window = file_bytes[offset : min(offset + buf_size, len(file_bytes))]`，再按 `transfer_mtu = 512` 拆分为最多 8 个子包，封装进无响应帧 `pack_rcsp_cmd(0x01, bytes([seq]) + chunk, has_resp=False, xm_opcode=0x1D)` 发送。
- **落盘结束确认**：全部窗口写完后，固件发送 `StopLargeFileTransfer (0x1C)`，当 `reason == 0` 表示全文件 CRC16 校验通过并成功落盘，主机回复 `Resp 0x1C (status=0)` 即可。

---

## 6. Stage 5：扩展业务层同步事务 (`OpCode = 0xFF`) 与二进制容器格式

业务层控制指令封装在 RCSP `OpCode = 0xFF` 的负载区中，内部字段采用 **Little-Endian (小端序)** 编码。

### 6.1 扩展业务层消息 ID 映射表

| 方向 | Msg ID (LE uint16) | 阶段 / 消息名称 | 载荷格式与功能说明 |
| :---: | :---: | :--- | :--- |
| Host -> Card | `0x0003` | `GetTaskWordBookMsg` | `03 00` (2B)：查询当前已注册激活的词书 ID 列表 |
| Card -> Host | `0x0004` | `GetTaskWordBookResultMsg` | `<HH` (`0x0004, count`) + `count * <Q` (`book_id` 数组) |
| Host -> Card | `0x0077` | `GetWordBookInfoMsg` | `<HQB` (`0x0077, book_id, book_type=1`)：查询单本词书的词数与学习进度 |
| Card -> Host | `0x0078` | `GetWordBookInfoResultMsg` | `<HQQIBHHBHBBBB` (34B)：返回词书版本、总词数、当前背词索引与配置 |
| Host -> Card | `0x0019` | `GetCurrBookMsg` | `19 00` (2B)：查询当前正在学习的词书状态 |
| Card -> Host | `0x001A` | `GetCurrBookResultMsg` | 返回当前激活词书 `currBookId`、`wordsCount` 与 `currIndex` |
| Host -> Card | `0x0055` | `BeginSyncMsg` | `55 00` (2B)：开启词书同步事务锁，墨水屏切换至同步状态界面 |
| Card -> Host | `0x0056` | `BeginSyncResultMsg` | `56 00 <result:1B>` (`result=0` 表示准备就绪) |
| Host -> Card | `0x0075` | `SetWordBookMsg` | `<HH` (`0x0075, count`) + `count * 31B` 词书描述符 + `<QB` (`currBookId, currBookType=1`) |
| Card -> Host | `0x0076` | `SetWordBookResultMsg` | `76 00 <result:1B>` (`result=0` 注册成功) |
| Host -> Card | `0x007A` | `TransportBookMsg` | `<HQBB` (`0x007A, book_id, book_type=1, file_mask=3`)：声明即将上传该词书的 `.cad`(`bit0`) 与 `.rev`(`bit1`) |
| Card -> Host | `0x007B` | `TransportBookResultMsg` | `7B 00 <result:1B>` (`result=0` 后立即启动 `.cad` 和 `.rev` 的 Stage 3/4 传输) |
| Host -> Card | `0x00AA` | `EndSyncMsg` | `AA 00 00 00` (4B)：提交同步事务并刷新墨水屏词书菜单 |
| Card -> Host | `0x00AB` | `EndSyncResultMsg` | `AB 00 <result:1B>` (`result=0` 同步完成) |

### 6.2 `SetWordBookMsg (0x0075)` 单条词书描述符结构 (31 Bytes, Little-Endian)
```python
struct.pack("<QQIBHHBHBBB",
    book_id,            # uint64: 词书 ID (如 901, 902)
    book_version_ms,    # uint64: 版本毫秒时间戳 (如 1681960781000)
    task_id,            # uint32: 任务 ID (通常与 book_id 相同)
    1,                  # uint8 : book_type (1 = 标准词书)
    words_count,        # uint16: 总词数
    curr_index,         # uint16: 当前已学到的词序 (新书为 0)
    1,                  # uint8 : learn_mode (1 = 默认模式)
    15,                 # uint16: per_time_size (每组学习词数，默认 15)
    1,                  # uint8 : sound_count (发音次数)
    2,                  # uint8 : voice_type (2 = 美音/默认发音类型)
    0                   # uint8 : display_content (0 = 默认显示模式)
)
```

---

## 7. `.CAD` 与 `.REV` 二进制容器字节级规范

### 7.1 `.CAD` 词卡数据库容器格式 (Little-Endian)
`.CAD` 文件由 **4 个连续区段**构成，所有偏移量均为相对于文件起始位置 (`0x00`) 的绝对字节偏移：

#### (1) 文件头 (Header, `0x00 .. 0x83`, 共 132 字节)
```python
header = struct.pack("<6I",
    0,          # 0x00: 保留字 0
    0,          # 0x04: 保留字 1
    0x84,       # 0x08: Section 1 (正面词头表) 起始偏移 (固定 132)
    meta_off,   # 0x0C: Metadata Block (词书元数据) 起始偏移
    sec2_off,   # 0x10: Section 2 (背面释义表) 起始偏移
    0           # 0x14: 保留字 2
) + b"\x00" * 108  # 0x18..0x83: 108 字节全零填充
```

#### (2) Section 1：墨水屏正面词头与媒体槽索引表 (`0x84 .. meta_off - 1`)
- **区段头 (8 字节)**：`struct.pack("<II", N, 0)`，其中 `N` 为总词数。
- **记录指针数组 (`4 * N` 字节)**：`N` 个 `<I`，第 `i` 项指向第 `i` 条 59 字节定长记录在文件中的绝对偏移 `rec1_base + i * 59`。
- **定长记录数组 (`59 * N` 字节)**：每条记录 59 字节，第 1 个槽 `(w_len, w_off)` 指向正面词头 UTF-8 字符串，其余 6 个附加槽（音标、例句发音等）对于纯文本词卡可将长度设为 `0`、偏移指向词头末尾 `w_off + w_len`：
  ```python
  end_off = w_off + w_len
  rec1 = (
      struct.pack("<II", w_len, w_off)
      + struct.pack("<II", 0, end_off)
      + struct.pack("<II", 0, end_off)
      + b"\x00" * 5
      + struct.pack("<II", 0, end_off)
      + struct.pack("<II", 0, end_off)
      + b"\x00" * 5
      + struct.pack("<II", 0, end_off)
      + struct.pack("<HB", 0, 0)
  )  # 严格等于 59 字节
  ```
- **正面 UTF-8 字符串池**：紧跟在 `59 * N` 记录之后，紧凑存放所有词头的 UTF-8 字节流。

#### (3) Metadata Block：词书元数据区 (`meta_off .. sec2_off - 1`)
```python
title_bytes = title.encode("utf-8")
meta_block = struct.pack("<IQQIIIIQ",
    1,                  # version = 1
    book_id,            # uint64: 词书 ID (如 901)
    timestamp_ms,       # uint64: 毫秒级时间戳
    0,                  # reserved = 0
    13,                 # lang_type = 13
    3,                  # category = 3
    len(title_bytes),   # uint32: 标题 UTF-8 字节长度
    meta_off + 44       # uint64: 标题字符串在文件中的绝对偏移
) + title_bytes
```

#### (4) Section 2：墨水屏背面释义与例句详情表 (`sec2_off .. EOF`)
- **区段头 (8 字节)**：`struct.pack("<II", N, 0)`。
- **记录指针数组 (`4 * N` 字节)**：`N` 个 `<I`，第 `i` 项指向 `rec2_base + i * 37`。
- **定长记录数组 (`37 * N` 字节)**：每条记录 37 字节，第 1 个槽 `(d_len, d_off)` 指向背面完整多行释义文本，其余 3 个扩展槽设为空：
  ```python
  end_off = d_off + d_len
  rec2 = (
      struct.pack("<II", d_len, d_off)
      + struct.pack("<II", 0, end_off)
      + struct.pack("<II", 0, end_off)
      + struct.pack("<II", 0, end_off)
      + b"\x00" * 5
  )  # 严格等于 37 字节
  ```
- **背面 UTF-8 字符串池**：紧凑存放所有词卡背面释义的 UTF-8 字节流（支持 `\n` 换行排版）。

---

### 7.2 `.REV` 艾宾浩斯复习计划容器格式 (Little-Endian)
`.REV` 文件定义了词书中每个词条的索引以及未来 `K` 天的艾宾浩斯周期复习矩阵：

#### (1) 文件头 (Header, `0x00 .. 0x37`, 共 56 字节)
```python
header = struct.pack("<QQQQQIIII",
    1,              # version = 1
    book_id,        # uint64: 词书 ID
    ts_ms,          # uint64: 创建时间戳 (ms)
    ts_ms - 59,     # uint64: 基准时间戳 (ms)
    daily_words,    # uint64: 每组/每日新学词数 (默认 15)
    N,              # uint32: 总词数
    0x38,           # uint32: Section 1 起始偏移 (固定 56)
    sec2_off,       # uint32: Section 2 起始偏移
    0               # uint32: reserved = 0
)
```

#### (2) Section 1：词头快速索引表 (`0x38 .. sec2_off - 1`)
- 包含 `N` 个 `<HI`（`uint16 w_len`, `uint32 w_off`）描述符，后跟所有词头的紧凑 UTF-8 字节流。

#### (3) Section 2：艾宾浩斯每日复习词号矩阵 (`sec2_off .. EOF`)
- 设总词数为 `N`，每日新词数为 `G`（默认 `15`），则总新学组数为 `M = ceil(N / G)`，复习计划总天数为 `K = M + 40`。
- 在第 `d` 天（`0 <= d < K`），需要学习的词组集合为满足 `m = d - offset`（其中艾宾浩斯间隔 `offset` 取自 `[0, 2, 6, 14, 29, 39]` 且 `0 <= m < M`）的所有组 `m`。
- 将当天命中的所有组内的 **1-based 词号**（`1 .. N`）用英文逗号 `,` 拼接为 ASCII 字符串（若当天无复习任务则为 `""` 空串）。
- 写入 `<I` (`K`) + `K` 个 `<HI` (`s_len, s_off`) + 紧凑拼接的日期词号字符串池。

---

## 8. 附：早期紧凑型固件 `.CAD` / `.REV` 变体格式参考 (GB2312 / 36B 记录变体)

在其他早期墨水屏词卡固件中，还存在一种基于 **GB2312 空字符结尾 + 36 字节定长复习记录** 的紧凑变体格式（供跨版本协议研究对比）：
- **变体 `.CAD` Header (128B)**：`0x2C..0x33` 固定为 `FF FF FF FF 00 00 00 00`，词书名最长 62B UTF-8；每个词条的 GB2312 字符串必须以 `\x00` 结尾，且 `total_len (uint8)` 必须包含末尾的 `\x00`。
- **变体 `.REV` Header (12B)**：`struct.pack("<III", 1, N, 0xFFFFFF00)`，后跟 `N` 条 **36 字节**定长复习记录。
- **注意**：**YDW012 系列固件实际采用的是第 7 节详述的 UTF-8 偏移指针表格式**（已由 `ydw012_cli.py` 完整实现并在硬件上验证通过）。

---

> **学习研究与免责声明**：本文档仅供嵌入式通信协议学习与个人合法持有硬件的互操作性研究使用，严禁用于任何商业或侵权用途。
