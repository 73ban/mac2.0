# D+验证总账规则

更新时间：2026-06-28

## 必查节点

所有作战室判断、核心个股、题材主线、模式结论都必须检查：

- D+1
- D+3
- D+5
- D+10
- D+20
- D+30

## 结论格式

```yaml
d1_result: 强于预期 | 符合预期 | 弱于预期 | 证伪
d3_result:
d5_result:
d10_result:
d20_result:
d30_result:
final_action: 升级 | 保留 | 降级 | 归档
```

## 作用

D+验证是 AI 自学习的核心。没有 D+验证，AI 只能总结资料；有 D+验证，AI 才能知道哪些判断真的赚钱、哪些只是看起来有道理。

## 自动生成入口

每日到期任务由脚本生成：

```bash
python3 raw/07-系统脚本/codex_generate_dplus_tasks.py --date 2026-06-29 --force
```

输出：

- `wiki/09-统计与进化/YYYY-MM-DD-D+验证任务.md`
- `data/facts/dplus_due_tasks.json`

原则：

1. 脚本只生成到期清单，不自动判断涨跌强弱。
2. 盘后必须用真实行情/交割/复盘回填结论。
3. 没有真实结果时保持 `pending`，不编造验证。
4. 验证失败的样本必须回写自动打分规则或错误库。
