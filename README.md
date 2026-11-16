# ag-ui-chunk-expand

**把录制里的 AG-UI 紧凑 chunk 事件离线展开成规范的 START/CONTENT/END 三元组，并把「同一 message 的 role / toolCallName 冲突」逐条报出来，而不是悄悄选一个赢家。**

Upstream: https://github.com/ag-ui-protocol/ag-ui

## 上游是什么，缺什么

AG-UI 允许生产者用紧凑写法发事件：[`TEXT_MESSAGE_CHUNK`](https://github.com/ag-ui-protocol/ag-ui/blob/main/docs/spec/1.0/events/text-messages.mdx) 的规范原文是 “A consumer MUST expand chunks into the three events above ... including the first-chunk requirements and the conflicting-repeat rule.”；`TOOL_CALL_CHUNK` 同理。也就是说，**展开是消费者的义务**，而 SDK 各语言实现里这是内部行为，没有一个独立工具能对一份录制做展开、并把冲突列出来。

这件事有真实成本：开放 issue [#3264](https://github.com/ag-ui-protocol/ag-ui/issues/3264)（`[P2] client: subscriber message replacement can discard tool-call argument chunks`）就是同一类失败——chunk 在替换/合并时被丢掉，而流本身仍然“合法”。上游 conformance 目录有 `chunk-conflicting-role-fatal` 这类断言，但它是 TS 测试链路的一部分，不能拿来检查你手上的一份录制。

## 它做什么 / 不做什么

做：

- 读 SSE 录制（`data:` 行），识别 `TEXT_MESSAGE_CHUNK` / `TOOL_CALL_CHUNK`，按首 chunk 要求生成 START，按 delta/args 生成 CONTENT/ARGS，在 message 切换、run 结束或流结束时补 END。
- 冲突检测：C010/C020 首 chunk 缺 id；C011 role 前后不一致；C021 toolCallName 前后不一致。每条带输入事件下标。
- `--json` 输出展开后事件序列与冲突；`--keep-provenance` 保留 `_from` 下标。
- 退出码 0（无冲突）/ 1（有冲突）/ 2（用法或输入错误）。

不做：

- 不判断事件顺序是否合法（交给 `ag-ui-stream-verify`），不做 transcript 归约（交给 `ag-ui-transcript-diff`）。
- 冲突时仍然输出展开结果（便于看清丢的是什么），**不**替调用方丢弃数据；不联网、不执行 agent。
- 只处理 SSE；JSONL 录制请先转成 SSE 行。

## 安装 / 用法

零依赖，Python ≥ 3.9：

```bash
git clone https://github.com/linmoxi33/ag-ui-chunk-expand.git
cd ag-ui-chunk-expand
python3 tests/run.py                      # 10 passed
python3 agui_chunk_expand.py examples/in/compact.sse
python3 agui_chunk_expand.py examples/in/conflict.sse --json   # exit 1
```

`--json` 输出示例：`examples/out/compact.json`（6 in → 10 out）、`examples/out/conflict.json`（C011）。

## 本轮创新

B 档：把 AG-UI 规范里「消费者 MUST 展开 chunk」从 SDK 内部行为变成**可对任意录制复算的独立展开器**，并首次把 conflicting-repeat 规则输出成带输入下标的机器可读冲突（C010/C011/C020/C021）。与同轮两个工具互补：一个判合法性、一个判消费结果，这个负责“紧凑写法到规范事件”的那一步。

## 局限

- 只在流结束/切换时补 END，无法还原生产者原本想在哪一刻结束。
- role/toolCallName 冲突采用“保留首个非空值 + 报错”，这与上游 fatal 语义不同（上游直接判错）；冲突流的下游结果不可信，只用于定位。
- 不支持 `TEXT_MESSAGE_CHUNK` 中嵌套的 metadata 合并规则。
