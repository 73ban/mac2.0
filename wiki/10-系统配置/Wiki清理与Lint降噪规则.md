# Wiki清理与Lint降噪规则

更新时间：2026-07-04

## 结论

全库深度 lint 不能直接扫整个项目根目录。73神话现在同时包含活动 Wiki、RAW 原始资料、运行缓存、旧 Windows 副本、Syncthing 版本历史和迁移冲突目录；如果全部送进 lint，会产生几十万级噪音，甚至拖死应用。

日常 lint 只扫 `wiki/` 活动知识库。RAW、data、.system、.llm-wiki、.conflicts、.stversions 只允许专项脚本按目的读取，不进入全库语义 lint。

## 必须排除

| 目录 | 原因 | 处理 |
|---|---|---|
| `.conflicts/` | 迁移冲突和旧嵌套 Wiki 副本 | 不进索引、不进 lint |
| `.73wiki/backups/` | 应用备份 | 不进索引、不进 lint |
| `.system/.system/` | Windows/服务器旧系统副本 | 不作为 Mac 当前入口 |
| `.llm-wiki/.llm-wiki/` | 旧运行产物嵌套副本 | 不作为当前 AI 上下文 |
| `data/data/` | 旧训练数据嵌套副本 | 暂不删除，先不进索引 |
| `**/.stversions/` | Syncthing 版本历史 | 不进索引、不进 lint |
| `raw/**` | 原始材料量大、格式混杂 | 只由专项脚本读取 |

## 可以清理但先不硬删

| 项目 | 当前判断 |
|---|---|
| `.system/.system/` | 42M，旧后台脚本和 WeRSS 状态副本，Mac 当前链路不用 |
| `.llm-wiki/.llm-wiki/` | 13M，旧 latest 产物，含 Windows 路径 |
| `data/data/` | 746M，疑似旧训练数据嵌套副本，需确认外层 `data/` 完整后再删 |
| `.conflicts/lint-quarantine-20260704/` | 旧 Wiki 噪音隔离区，不应回流主 Wiki |

## 清理原则

1. 不删除 `raw/01-交割单`、`raw/02-每日复盘`、`raw/04-市场数据`、`raw/05-研报新闻`、`raw/09-短线知识`、`raw/10-飞书交易沟通`、`raw/11-Codex分析产物`。
2. 旧判断页如果和新审计冲突，先标注“已被新审计覆盖”，不要直接删。
3. Windows/Mac本机RAW入口本地仍需要的 `.ps1/.cmd` 可以保留，但必须放在“Windows 侧/legacy”口径下，不能作为 Mac 主链路入口。
4. Mac 当前任务入口统一使用 `.sh`、LaunchAgent、Python/Node 脚本。
5. 新文件名、表头和报告尽量使用中文，不再输出 `weak-to-strong`、`limitUpCount` 这类英文业务字段。

## 日常命令

安全 lint：

```bash
python3 raw/07-系统脚本/codex_safe_wiki_lint.py --write
```

Mac 迁移残留审计：

```bash
python3 raw/07-系统脚本/codex_audit_mac_migration_residue.py --write
```

## 对应用内深度 lint 的要求

应用内“全库深度 lint”如果无法读取 `.wikiignore`，不要直接运行全库模式。先按目录运行：

1. `wiki/00-总纲`
2. `wiki/01-L1市场环境`
3. `wiki/02-L2方向题材`
4. `wiki/03-L3个股档案`
5. `wiki/04-L4交易模式与执行`
6. `wiki/05-错误库`
7. `wiki/06-持仓与资金管理`
8. `wiki/07-作战室`
9. `wiki/09-统计与进化`
10. `wiki/10-系统配置`

`wiki/08-信息来源` 只做入口索引审计，不做全文语义深度 lint。
