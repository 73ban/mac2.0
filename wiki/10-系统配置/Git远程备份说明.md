# Git远程备份说明

- 生成时间：2026-07-06 15:14:22
- 当前状态：已配置远程仓库；本地已提交；远程 push 被 GitHub 凭证阻塞
- 当前分支：`main`

## 当前远程

```text
origin	https://github.com/73ban/mac2.0.git (fetch)
origin	https://github.com/73ban/mac2.0.git (push)
```

## 最近提交

```text
cb40763 chore: connect github remote and sync trading wiki loop
35547ae feat: automate fifteen-point trading wiki loop
91fde97 feat: backfill trade mode attribution and D+ stats
```

## 当前阻塞

本机执行过：

```bash
git push -u origin main
```

GitHub 返回：

```text
fatal: could not read Username for 'https://github.com': Device not configured
```

原因：本机没有可用的 GitHub HTTPS 凭证，且当前没有 `gh` 登录态或标准 SSH key。

## 完成远程上传的办法

任选一种：

### 方式一：GitHub Desktop

1. 用 GitHub Desktop 登录 `73ban` 账号。
2. Add Existing Repository，选择：

```text
/Users/qixinchaye/wiki/73神话
```

3. 点击 Push origin。

### 方式二：Personal Access Token

在 GitHub 创建 token 后，本机执行：

```bash
git push -u origin main
```

按提示输入 GitHub 用户名和 token。

### 方式三：SSH

生成 SSH key，添加到 GitHub 后执行：

```bash
git remote set-url origin git@github.com:73ban/mac2.0.git
git push -u origin main
```

## 边界

- 现在所有提交都在 Mac 本地 `.git`，最新提交为 `cb40763`。
- 远程地址已配置，但由于缺少 GitHub 凭证，内容尚未上传到 GitHub。
- raw大体量数据已被 `.gitignore` 排除，只跟踪核心wiki、脚本和小型事实层。
