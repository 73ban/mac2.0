# Git远程备份说明

- 生成时间：2026-07-06 08:29:25
- 当前状态：未配置远程仓库
- 当前分支：`main`

## 当前远程

```text
(none)
```

## 最近提交

```text
91fde97 feat: backfill trade mode attribution and D+ stats
a2c4064 chore: ignore runtime state files
d94649d chore: initialize 73wiki version tracking
```

## 如果要备份到私有仓库

1. 在 GitHub / Gitee / GitLab 建一个私有仓库。
2. 在本机执行：

```bash
git remote add origin <你的私有仓库地址>
git push -u origin main
```

## 边界

- 现在所有提交都在 Mac 本地 `.git`。
- 没有远程地址和凭据前，我不会把内容上传到任何网站。
- raw大体量数据已被 `.gitignore` 排除，只跟踪核心wiki、脚本和小型事实层。
