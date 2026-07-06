# Mac迁移体检报告

更新时间：2026-07-02 09:06:59

## 结论

主程序、Wiki 数据、AI 上下文和核心脚本已可在 Mac 上运行。生态服务中，wx-cli 已安装但 daemon 未运行；Docker CLI/Compose 与 Docker daemon 可用；WeKnora Lite 已构建并通过 8080 HTTP 冒烟；QUEST 已安装 Mac runtime，可导入 API-agent 工具，torch/MPS 可用。vLLM 0.19.0 因 NVIDIA cuDNN frontend 依赖无 macOS arm64 wheel，无法在本机 Python 环境安装。

## 检查项

| 项目 | 状态 | 详情 |
|---|---|---|
| wiki_root | OK | /Users/qixinchaye/wiki/73神话 |
| raw | OK | /Users/qixinchaye/wiki/73神话/raw |
| wiki | OK | /Users/qixinchaye/wiki/73神话/wiki |
| data | OK | /Users/qixinchaye/wiki/73神话/data |
| current_ai_context | OK | /Users/qixinchaye/wiki/73神话/.system/current-ai-context.json |
| installed_app | OK | /Applications/Trading Review Wiki.app |
| integrated_repo | OK | /Users/qixinchaye/Workspace/trading-review-wiki-ymj-integrated |
| weknora_repo | OK | /Users/qixinchaye/Workspace/ymj8903668-droid-open-source/WeKnora |
| weknora_lite_binary | OK | /Users/qixinchaye/Workspace/ymj8903668-droid-open-source/WeKnora/WeKnora-lite |
| quest_repo | OK | /Users/qixinchaye/Workspace/ymj8903668-droid-open-source/QUEST |
| quest_venv | OK | /Users/qixinchaye/Workspace/ymj8903668-droid-open-source/QUEST/.venv |
| quest_lite_requirements | OK | /Users/qixinchaye/Workspace/ymj8903668-droid-open-source/QUEST/requirements-mac-lite.txt |
| python3 | OK | Python 3.9.6 |
| node | OK | v24.18.0 |
| npm | OK | 11.16.0 |
| codex | OK | codex-cli 0.142.3 |
| git | OK | git version 2.50.1 (Apple Git-155) |
| wx | OK | wx 0.3.0 |
| pnpm | OK | 11.9.0 |
| cargo | OK | cargo 1.96.0 (30a34c682 2026-05-25) |
| go | OK | go version go1.26.4 darwin/arm64 |
| docker | OK | Docker version 29.5.3, build d1c06ef |
| docker_compose | OK | Docker Compose version v5.1.4 |
| docker_daemon | OK | 29.5.3 |
| python_scripts_py_compile | OK |  |
| integrated_frontend_build | OK | ✓ built in 1.03s |
| weknora_lite_http | OK | http://127.0.0.1:8080/ responds |
| quest_lite_smoke | OK | torch ok 2.10.0 mps_available=True |
| ai_context | OK | activeDate=2026-07-02 pinned=31 |

## Windows路径残留

| 范围 | 文件数 | 命中数 | 示例 |
|---|---:|---:|---|
| active_system_scripts | 0 | 0 |  |
| active_raw_python_scripts | 0 | 0 |  |
| active_generated_latest_cache | 0 | 0 |  |
| active_runtime_state | 0 | 0 |  |
| legacy_runtime_state | 0 | 0 |  |
| integrated_source_scripts | 0 | 0 |  |
| standalone_connectors | 0 | 0 |  |
| migration_archives_and_logs | 5 | 78 | wiki/10-系统配置/迁移归档/Windows到Mac迁移清单.md, wiki/10-系统配置/大鸟交接/2026-06-13-交接记录.md, wiki/10-系统配置/配置归档/2026-06-20-旧v9配置副本-73wiki.config.json, .system/logs/longxia-review-handoff/2026-06-30-codex-stderr.log, raw/07-系统脚本/legacy-tools/codex_raw_watch_launcher.py |

说明：`active_*` 和 `integrated_source_scripts` 是当前执行链路；`legacy_runtime_state`、`migration_archives_and_logs` 是历史运行记录、旧日志或迁移归档，不作为 Mac 当前入口。

## 下一步

1. 微信/公众号抓取按本机直抓口径处理；若使用 wx-cli 缓存，先补齐 `config.json` 或完成 `wx init`。
2. WeKnora 当前使用 Lite 单二进制，入口为 `http://127.0.0.1:8080/`；Docker daemon 可用，若要切换标准版，运行 `start_weknora_mac.sh docker`。
3. QUEST 当前使用 Mac runtime + torch/MPS；vLLM full local serving 需 Linux/NVIDIA CUDA 环境或远端推理服务，本机 macOS arm64 不满足依赖。
4. 每次迁移、升级或重启后，运行本脚本重新体检。

机器报告：`data/trading/mac-migration-doctor.json`
