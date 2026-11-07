# 评测说明

本目录记录 `methodology-router` 的评测设计、判定标准、复现步骤和每次运行的结果。

- `scenarios.md`：六个场景和深度检查的提示词、期望与失败信号。
- `trigger_set.jsonl`：触发集，29 条（应触发 15、不应触发 14），中英文混合。
- `rubric.md`：判定标准。
- `tools/check_run.sh`：从 harness 会话记录判断 Skill 是否被加载（不采信模型自述）。
- `results/`：每次运行的记录。

## 运行方式

1. 每次运行是一个全新、互相隔离的会话，工作目录为空的临时目录（场景 S4 为放好 `utils.py` 的临时目录）。
2. 提示词逐字使用 `scenarios.md` / `trigger_set.jsonl` 中的原文，不附加任何说明，不提及 Skill 名称或预期答案。
3. 启用组：Skill 已安装到运行账号的 `~/.agents/skills/methodology-router/`。对照组：运行时该目录不存在。
4. 加载证据：对每次运行的会话记录执行

   ```bash
   sh evals/tools/check_run.sh <会话记录路径>/session.v4.jsonl.zstd
   ```

   它检查两件事：系统消息中的 Skill 目录是否列出了 `methodology-router`（可发现性）；会话记录中是否出现名为 `skill`、参数含 `methodology-router` 的工具调用（实际加载）。会话记录路径由运行方式决定，结果中写明路径的脱敏形式。
5. 判定依据是输出原文，按 `rubric.md` 逐条打分。
6. 每次运行记录：模型、提交 SHA、提示词编号、启用/对照、时间、加载证据、判定、脱敏后的输出链接。

## 脱敏

发布前去除：用户名、主机名、内网地址、绝对家目录路径、凭据及配置值。脱敏内容需在结果文件中说明。

## 迭代

先提交 `scenarios.md`、`trigger_set.jsonl`、`rubric.md`，再根据结果调整 Skill。每个版本的结果都保留，调整后重跑受影响项。作者不得修改判定口径以迎合结果。
