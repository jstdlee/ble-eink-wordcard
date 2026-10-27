# 网易有道电子单词卡 YDW012 完整逆向工程技术手册
# NetEase Youdao E-Ink Word Card (YDW012) Complete Reverse-Engineering Reference

本文档完整记录了对 **网易有道电子单词卡 YDW012** 硬件通信链路、杰理 (Jieli) `JL_AUTH` 6 步加密握手协议、RCSP (Remote Control Serial Protocol) 文件系统浏览与大文件传输任务 (`TransferTask`)、有道私有 `0xFF` 业务指令集以及 `.CAD` / `.REV` 二进制词书文件格式的逆向工程过程与字节级规范。

---

## 1. 硬件架构与 BLE GATT 通信层

### 1.1 物理接口排障（USB 纯供电陷阱）
- **实测现象**：通过全功能 Type-C 数据线将 YDW012 连接至 Linux 主机，监控 `dmesg -w` 与 `lsusb` 均无任何 USB 设备枚举事件。
- **硬件结论**：YDW012 的 Type-C 接口仅焊接了电源线（VBUS/GND）至线性充电管理芯片，未连接主控 SoC 的 USB D+/D- 引脚。所有固件交互、词书下发与学习记录同步均通过 **杰理 (Jieli) 双模蓝牙 SoC 的 BLE GATT 通道**完成。

### 1.2 BLE 广播与 GATT 特征值 (Characteristics)
- **广播名称格式**：`YDW:GD4170XXXXXXXXXX`（前缀固定为 `YDW:`，后跟 16 位设备序列号）。
- **主服务与特征 UUID**：

| 名称 | UUID | 属性 (Properties) | 作用说明 |
| :--- | :--- | :--- | :--- |
| **RCSP Service** | `0000ae00-0000-1000-8000-00805f9b34fb` | Primary Service | 杰理 RCSP 主服务 |
| **TX (Host -> Card)** | `0000ae01-0000-1000-8000-00805f9b34fb` | `Write Without Response` (`0x04`) | 主机向单词卡写入裸认证帧或 RCSP 帧 |
| **RX (Card -> Host)** | `0000ae02-0000-1000-8000-00805f9b34fb` | `Notify` (`0x10`) | 单词卡向主机推送认证应答、RCSP 响应与主动命令 |

---

## 2. 阶段一：6 步 `JL_AUTH` 挑战-应答加密握手 (`libjl_auth.so` & `libjl_bt_auth.so`)

### 2.1 Silent Drop 陷阱 #1：为什么连上 BLE 后发任何 RCSP 帧都超时？
连接 `0xAE01` 并订阅 `0xAE02` Notify 后，固件处于 **Unauthenticated（未认证隔离态）**。此时任何以 `FE DC BA` 开头的标准 RCSP 帧都会被固件底层静默丢弃，且超时后固件会主动断开 BLE 连接。

主机必须先在 `0xAE01` / `0xAE02` 上直接收发**不含 RCSP 封包的裸字节流**完成 6 步双向挑战-应答握手：

| 步骤 | 方向 | 长度 | 字节内容 | 含义 |
| :---: | :---: | :---: | :--- | :--- |
| **Step 1** | Host -> Card (`0xAE01`) | 17 B | `0x00` + `R_h[0..15]` | 主机发送 16 字节随机挑战 `R_h` |
| **Step 2** | Card -> Host (`0xAE02`) | 17 B | `0x01` + `E(R_h)[0..15]` | 固件返回加密后的 `E(R_h)` |
| **Step 3** | Host -> Card (`0xAE01`) | 5 B | `02 70 61 73 73` (`\x02pass`) | 主机确认固件响应并发送 `pass` |
| **Step 4** | Card -> Host (`0xAE02`) | 17 B | `0x00` + `R_d[0..15]` | 固件向主机发起 16 字节随机挑战 `R_d` |
| **Step 5** | Host -> Card (`0xAE01`) | 17 B | `0x01` + `E(R_d)[0..15]` | 主机计算并返回 `E(R_d)` |
| **Step 6** | Card -> Host (`0xAE02`) | 5 B | `02 70 61 73 73` (`\x02pass`) | 固件校验通过，返回 `\x02pass`，解锁 RCSP 通道 |

### 2.2 密码学实现分析（APK 内两套 Native 库对比）
在旧版 APK 的 `lib/arm64-v8a/` 目录下同时存在两个杰理认证库：
1. **`libjl_bt_auth.so`（通用蓝牙音频 SDK 变体）**：
   - 使用魔数数组 `[254, 237, 250, 206, 202, 254, 186, 190]`（即 `FE ED FA CE CA FE BA BE`）、线性同余变换（`v = (v * 16807) % 0x7FFFFFFF`）派生密钥，并调用 **8 轮 Salsa20 流密码**对挑战块加密。
2. **`libjl_auth.so`（`com.jieli.jl_rcsp.impl.RcspAuth` 实际加载的 RCSP 认证库）**：
   - YDW012 单词卡使用的是 `RcspAuth` 调用的 `libjl_auth.so -> getEncryptedAuthData(byte[])`。
   - 我们在 `ydw012_cli.py` 中 100% 纯 Python 还原了其内部 `function_e1test` 算法：
     - **静态种子密钥 (`STATIC_KEY`)**：`06 77 5F 87 91 8D D4 23 00 5D F1 D8 CF 0C 14 2B`
     - **6 字节魔数盐 (`MAGIC`)**：`4D 69 76 47 39 58` (ASCII `"MivG9X"`)
     - **第一阶段（轮密钥生成）**：以 `STATIC_KEY` 为初始密钥，对 `R[0..7]` 重复 `R[0..7]` 构成的 16 字节块运行 8 轮正向 S-Box 查表、Fibonacci 模乘置换 (`idx = (i + i*34) & 15`) 与列混淆，生成动态轮密钥 `round_key`。
     - **第二阶段（混合挑战块）**：以 `round_key` 为密钥，将 `R[8..15] + MAGIC[0..5] + R[8..9]` 作为输入块，运行 8 轮逆向 `ISBOX` 查表与逆列混淆，输出最终 16 字节密文 `E(R)`。

---

## 3. 阶段二：RCSP 帧结构与会话状态机激活 (`GetTargetInfoCmd 0x03`)

### 3.1 杰理 RCSP 标准帧格式
认证完成后，`0xAE01` 与 `0xAE02` 上的所有数据均采用大端序 (Big-Endian) RCSP 帧封装：

```text
+------------+--------+--------+---------------+------------+------------------+------+
| Start Flag | Flags  | OpCode | Param Length  | SeqNum(SN) | Payload / Params | End  |
| FE DC BA   | 1 Byte | 1 Byte | 2 Bytes (BE)  | 1 Byte     | N Bytes          | EF   |
+------------+--------+--------+---------------+------------+------------------+------+
```

- **Flags 字节位定义**：
  - `0xC0` (`bit7=1, bit6=1`)：需要对方回复 Response 的 Command 帧（`Param Length = 1 + len(param)`，第 1 字节为 `SN`）。
  - `0x80` (`bit7=1, bit6=0`)：无需回复 Response 的单向流式 Command 帧（如 `OpCode=0x01` 大文件数据分片推送，`Param Length = 1 + len(param)`）。
  - `0x00` (`bit7=0, bit6=0`)：Response 响应帧（`Param Length = 2 + len(param)`，前 2 字节分别为 `Status (0=成功)` 和对应的请求 `SN`）。

### 3.2 Silent Drop 陷阱 #2：为什么认证成功后发 `0xFF` 或 `0x0C` 依然超时？
- **现象**：收到 Step 6 的 `02 70 61 73 73` 后，直接发送有道业务指令 `0xFF` 或文件浏览指令 `0x0C`，固件仍然不返回任何数据。
- **根因与解决方案**：逆向 `RcspOpImpl` 初始化流程发现，固件在 `JL_AUTH` 完成后，必须先收到一条 **`GetTargetInfoCmd (OpCode=0x03)`** 指令才会激活 RCSP 会话上下文并上报设备存储句柄：
  - **请求帧**：`FE DC BA C0 03 00 06 01 FF FF FF FF 00 EF`
    - `mask = 0xFFFFFFFF`（请求全部设备特性 TLV）
    - `platform = 0x00`（Android 主机标识）
  - **响应帧**：`FE DC BA 00 03 00 41 00 01 ... EF`（`status=0`，携带 63 字节 TLV 设备信息，其中包含存储卡句柄 `devHandler = 1`）。

---

## 4. 阶段三：FAT 文件系统目录浏览 (`0x0C`/`0x0D`) 与原卡文件无损提取 (`0x24`)

### 4.1 目录浏览 (`StartFileBrowseCmd 0x0C`)
用于读取单词卡内置 Flash FAT 文件系统中的目录结构、文件名与 **起始簇号 (`cluster`)**：
- **请求参数 (`PathData.toParamData`, 14+ 字节)**：
  ```python
  param = struct.pack(">BBHBIIH",
      path_type,    # 0 = 目录浏览
      read_num,     # 每次读取条目数 (如 10)
      start_index,  # 起始索引 (1-based: 1, 2, 3...)
      dev_handler,  # 存储设备句柄: 固定为 1
      parent_clust, # 父目录簇号 (根目录 "/" 为 0)
      dir_clust,    # 当前目录簇号 (如 "/O/" 为 5, "/O/513/" 为 656)
      4             # 簇号列表字节长度 (1 个 uint32 = 4)
  )
  ```
- **响应与数据推送**：
  1. 固件先回 `Resp 0x0C (status=0)`；
  2. 随后通过 `Cmd 0x01 (xm_opcode=0x0C)` 推送目录项二进制流：
     - `byte[0]`：`flags`（`bit0`: `0`=目录, `1`=文件；`bit1`: `0`=ANSI/GBK, `1`=Unicode UTF-16LE）
     - `byte[1..4]`：`<I` Little-Endian **文件/目录起始簇号 (`cluster`)**
     - `byte[5..6]`：`<H` Little-Endian 文件名长度 `name_len`
     - `byte[7]`：`dev_handler` (`1`)
     - `byte[8..8+name_len]`：文件名或目录名
  3. 最後固件发送 `Cmd 0x0D (StopFileBrowseCmd, reason)` 结束本次读取，主机需回复 `Resp 0x0D (status=0)`。

### 4.2 按簇号无损读取文件 (`ReadFileFromDeviceCmd 0x24`)
拿到任意文件（如 `/O/513/513.CAD`）的簇号 `cluster` 后，可通过 `OpCode=0x24` 将其完整导出到电脑：
1. **启动读取请求 (`StartWithClusterParam`)**：
   - `param = struct.pack(">BIIIB", 0x81, dev_handler=1, offset=0, cluster, 0)`
2. **固件响应 (`StartRsp`)**：
   - `Resp 0x24` 返回 `status=0, op=0x81` 及 4 字节大端文件总大小 `total_size = struct.unpack(">I", param[1:5])[0]`。
3. **流式分包接收 (`OpCode=0x01, xm_opcode=0x24`)**：
   - 每包格式：`seq (1B)` + `chunk_crc16 (2B BE)` + `file_data_chunk`。
   - 校验规则：采用累加式 **CRC16-XMODEM**（初值 `0`，每收到一包以 `running_crc = crc16_xmodem(chunk, running_crc)` 连续计算并与包头 `chunk_crc16` 校验）。
4. **结束通知**：
   - 当接收字节数达到 `total_size` 时，固件发送 `Cmd 0x24 (op=0x80)`，主机回复 `Resp 0x24 (status=0, param=0x80)` 完成下载。

---

## 5. 阶段四：RCSP 大文件高速上传状态机 (`TransferTask` `0x21`/`0x27`/`0x1B`/`0x20`/`0x1D`/`0x1C`)

### 5.1 Pitfall #3：为什么 `StartLargeFileTransfer (0x1B)` 返回 `status=1`？
如果只发 `NotifyPrepareEnv (0x21, param=0x00)` 就直接发 `0x1B`，固件不知道目标存储设备句柄，必定返回 `status=1` 拒绝传输。
逆向 `com.jieli.jl_rcsp.task.TransferTask` 发现，必须在 `0x21` 之后、`0x1B` 之前发送 **`DeviceExtendParamCmd (OpCode=0x27)`**：
```python
# op=0x00 (文件传输扩展参数), dev_handler=1 (Flash/SD), has_crc16=0
param_27 = struct.pack(">BIB", 0x00, 1, 0)
```
发送 `0x27` 并收到 `status=0` 后，再发送 `0x1B`：
```python
# size: 4B BE 文件总字节数
# crc16: 2B BE 全文件 CRC16-XMODEM
# md5_prefix: 文件路径 MD5 十六进制前 4 字符 + ".tmp" (如 b"6b34.tmp")
param_1b = struct.pack(">IH", len(file_bytes), crc16_xmodem(file_bytes)) + md5_prefix
```
固件立即返回 `status=0` 及 `transfer_mtu = 512`（大端 `>H`）！

### 5.2 Pitfall #4：`LargeFileTransferGetNameCmd (0x20)` 的 8.3 短文件名编码陷阱
固件收到 `0x1B` 后，会主动向主机发送 `Cmd 0x20` 询问真实文件名。
逆向 `LargeFileTransferGetNameCmd$Param.getNameData()` 发现其分支逻辑：
- 若主文件名长度 `< 9` 字节且扩展名 `< 5` 字节（即符合 DOS **8.3 短文件名**，如 `901.cad`、`901.rev`），**绝对不能加 `\U` 前缀或 UTF-16LE 编码**，必须直接返回：
  ```python
  name_bytes = filename.encode("gbk") + b"\x00\x00"
  # 例如 "901.cad" -> 39 30 31 2e 63 61 64 00 00
  ```
- 固件收到 `"901.cad\x00\x00"` 后，会自动提取前缀数字 `901` 并在 FAT 文件系统中创建目录 `/O/901/901.CAD`。

### 5.3 Pitfall #5：固件 `0x1D` 偏移量乱序拉取机制（断电安全文件头最后写入）
文件命名完成后，固件通过 `LargeFileTransferOpCmd (0x1D)` 主动向主机拉取数据块：
- 请求参数：`op (1B, 0=拉取数据)` + `buf_size (2B BE, 通常为 4096)` + `offset (4B BE)`。
- **关键逆向发现**：固件**不会从 `offset=0` 开始顺序拉取**！以 `901.cad` (50,164 B) 为例，固件的真实拉取序列为：
  1. `offset = 512, buf_size = 4096`
  2. `offset = 4608, buf_size = 4096`
  3. ... 依次拉取到文件末尾 `offset = 49664, buf_size = 4096`
  4. **最后一次拉取**：`offset = 0, buf_size = 512`！
- **设计原因**：固件故意将文件前 512 字节（包含 `.CAD` / `.REV` Header）留到最后写入。若传输中途蓝牙断开，Flash 上的文件头全为 `0xFF`/`0x00` 无效值，不会导致固件重启解析半截文件而死机。
- **主机端实现**：收到 `0x1D` 后，严格切片 `window = file_bytes[offset : offset + buf_size]`，再按 `transfer_mtu = 512` 切分为最多 8 个分片，通过无响应帧 `pack_rcsp_cmd(0x01, bytes([0x1D, seq]) + chunk, has_resp=False)` 连续发出，分片间仅需 `6ms` 间隔（实测稳定速率 ~8 KB/s）。
- **传输完成确认**：所有块写完后，固件发送 `StopLargeFileTransfer (0x1C)`，当 `param[0] == 0` 表示校验并落盘成功，主机回复 `Resp 0x1C (status=0)` 即可。

---

## 6. 阶段五：有道私有业务层协议 (`OpCode = 0xFF`)

有道应用层消息封装在 RCSP `OpCode = 0xFF` 的参数区中，内部采用 **Little-Endian (小端序)** 编码。

### 6.1 消息 ID 映射表 (`com.youdao.hardware.wordcard.ble.msg.*`)

| 方向 | Msg ID (LE uint16) | 类名 | 结构体格式与说明 |
| :---: | :---: | :--- | :--- |
| Host -> Card | `0x0003` | `GetTaskWordBookMsg` | `03 00` (2B)：查询卡内已激活的词书列表与背词进度 |
| Card -> Host | `0x0004` | `TaskWordBookMsg` | `04 00` + `count (2B)` + `N * 24B` 词书条目 + `9B` 尾部状态 (`currBookId`, `studyCount`, `reviewCount`) |
| Host -> Card | `0x0019` | `GetDeviceInfoMsg` | `19 00` + `0x00 * 6` (8B)：查询固件版本与电量 |
| Card -> Host | `0x001A` | `DeviceInfoMsg` | 返回固件版本号、序列号、音量与电量百分比 |
| Host -> Card | `0x0055` | `BeginSyncMsg` | `55 00 00 00` (4B)：开启词书同步事务，墨水屏显示同步界面 |
| Card -> Host | `0x0056` | `BeginSyncResultMsg` | `56 00 <result:1B> 00` (`result=0` 表示就绪) |
| Host -> Card | `0x0075` | `SetWordBookMsg` | `75 00` + `count (2B)` + `N * 31B` 词书声明 + `9B` 尾部 (`<IHHB`: `currBookId, 0, 0, 1`) |
| Card -> Host | `0x0076` | `SetWordBookResultMsg` | `76 00 <result:1B>` (`result=0` 成功) |
| Host -> Card | `0x0077` | `DeleteWordBookMsg` | `77 00 <count:2B>` + `N * <bookId:4B>`：从卡内删除指定词书 |
| Card -> Host | `0x0078` | `DeleteWordBookResultMsg` | `78 00 <result:1B>` |
| Host -> Card | `0x007A` | `TransportBookMsg` | `<HHII` (`0x007A, bookType=1, bookId, fileMask=3`)：通知固件即将上传某本词书的 `.cad`(`bit0`) 与 `.rev`(`bit1`) |
| Card -> Host | `0x007B` | `TransportBookResultMsg` | `7B 00 <result:1B>` (`result=0` 后立即启动 `.cad` 和 `.rev` 的 RCSP `TransferTask`) |
| Host -> Card | `0x00AA` | `EndSyncMsg` | `AA 00 <type:1B> 00` (`type=0` 完成同步并刷新词书列表) |
| Card -> Host | `0x00AB` | `EndSyncResultMsg` | `AB 00 <result:1B>` |

### 6.2 `SetWordBookMsg (0x0075)` 单条词书结构体 (31 Bytes, Little-Endian)
```python
struct.pack("<IBIIIIIIH",
    book_id,        # uint32: 词书 ID (如 901, 902, 513, 514)
    1,              # uint8 : bookType (1 = 单词书)
    words_count,    # uint32: 总词数
    0,              # uint32: memorizedWords (已背词数)
    0,              # uint32: taskNum
    0,              # uint32: finishTaskNum
    version_s,      # uint32: Unix 时间戳 (秒)
    15,             # uint32: groupWords (每组/每日新词数，默认 15)
    1               # uint16: flag (固定为 1)
)
```

---

## 7. `.CAD` 与 `.REV` 二进制词书格式字节级规范

通过 `ReadFileFromDeviceCmd (0x24)` 从真机 `/O/513/` 目录提取原厂词书样本后，我们完整逆向并验证了 YDW012 固件解析的 `.CAD` 与 `.REV` 格式。

### 7.1 `.CAD` 词卡文件格式 (Little-Endian)
`.CAD` 文件由 **4 个连续区段**组成，所有文件内偏移量均为相对于文件起始位置 (`0x00`) 的 **32 位/64 位绝对字节偏移**：

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

#### (2) Section 1：墨水屏正面词头与音标/发音索引表 (`0x84 .. meta_off - 1`)
- **区段头 (8 字节)**：`struct.pack("<II", N, 0)`，其中 `N` 为总词数。
- **记录指针数组 (`4 * N` 字节)**：`N` 个 `<I`，第 `i` 项指向第 `i` 条 59 字节定长记录在文件中的绝对偏移 `rec1_base + i * 59`。
- **定长记录数组 (`59 * N` 字节)**：每条记录 59 字节，包含词头及 6 个附加媒体槽（英音音标、美音音标、英音音频、美音音频等）。对于纯文本自定义词卡，将附加槽的 `len` 设为 `0`、`offset` 指向词头末尾 `w_off + w_len` 即可：
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

#### (4) Section 2：墨水屏背面词义与例句详情表 (`sec2_off .. EOF`)
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

### 7.2 `.REV` 艾宾浩斯复习计划文件格式 (Little-Endian)
`.REV` 文件定义了词书中每个单词的复习序号以及未来 `K` 天的艾宾浩斯复习矩阵：

#### (1) 文件头 (Header, `0x00 .. 0x37`, 共 56 字节)
```python
header = struct.pack("<QQQQQIIII",
    1,              # version = 1
    book_id,        # uint64: 词书 ID
    ts_ms,          # uint64: 创建时间戳 (ms)
    ts_ms - 59,     # uint64: 基准时间戳 (ms)
    daily_words,    # uint64: 每日新学词数 (默认 15)
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

## 8. 附：旧版/跨型号 `.CAD` / `.REV` 变体格式参考 (GB2312 / 36B 记录变体)

在逆向早期对其他型号有道词卡固件的分析中，还存在一种基于 **GB2312 空字符结尾 + 36 字节定长复习记录** 的紧凑变体格式（供跨型号固件研究参考）：
- **变体 `.CAD` Header (128B)**：`0x2C..0x33` 固定为 `FF FF FF FF 00 00 00 00`，词书名最长 62B UTF-8；每个词条的 GB2312 字符串必须以 `\x00` 结尾，且 `total_len (uint8)` 必须包含末尾的 `\x00`。
- **变体 `.REV` Header (12B)**：`struct.pack("<III", 1, N, 0xFFFFFF00)`，后跟 `N` 条 **36 字节**定长复习记录。
- **注意**：**YDW012 固件实际使用的是第 7 节详述的 UTF-8 偏移表格式**（已由 `ydw012_cli.py` 完整实现并在真机验证通过）。
