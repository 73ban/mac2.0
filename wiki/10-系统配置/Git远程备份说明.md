# Git远程备份说明

- 生成时间：2026-07-06 15:20:13
- 当前状态：已配置远程仓库；SSH认证成功；`main` 已上传并跟踪 `origin/main`
- 当前分支：`main`

## 当前远程

```text
origin	git@github.com:73ban/mac2.0.git (fetch)
origin	git@github.com:73ban/mac2.0.git (push)
```

## 最近提交

```text
fb55cc4 docs: record github push credential blocker
cb40763 chore: connect github remote and sync trading wiki loop
35547ae feat: automate fifteen-point trading wiki loop
```

## 当前远程备份状态

已完成：

```text
To github.com:73ban/mac2.0.git
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

SSH key：

```text
~/.ssh/id_ed25519_73wiki_github
```

远程仓库：

```text
git@github.com:73ban/mac2.0.git
```

## 边界

- 现在提交同时保存在 Mac 本地 `.git` 和 GitHub 远程 `origin/main`。
- raw大体量数据已被 `.gitignore` 排除，只跟踪核心wiki、脚本和小型事实层。
- 后续 push 需要使用同一把 SSH key；若 Git 默认找不到 key，可使用：

```bash
GIT_SSH_COMMAND='ssh -i ~/.ssh/id_ed25519_73wiki_github -o IdentitiesOnly=yes' git push
```
