# 售后报修智能分诊平台

## 文件放置说明

- `app/`：平台程序代码，包括网页路由、数据模型、业务流程和分诊/检索算法。
- `run.py`：启动平台的程序入口。
- `requirements.txt`：Python依赖清单。
- `数据资料/样例工单/工单样例.csv`：虚构报修工单样例。
- `数据资料/维修知识/知识库.csv`：正式维修知识库及公开来源字段。
- `运行脚本/`：数据库初始化和种子数据导入脚本。
- `本地运行数据/`：本机SQLite数据库和运行文件，不提交实际运行数据。
- `测试用例/`：分诊规则、分类、检索和流程测试。
- `docs/er-diagram.drawio`：数据库 ER 图（draw.io 打开）。
- `docs/ticket-state.drawio`：工单状态图（draw.io 打开）。

## 本机启动

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

浏览器打开 http://127.0.0.1:5000 。

## 数据库初始化与种子数据

首次运行或换新电脑时，先初始化数据库，再按需导入演示数据。以下命令都在仓库根目录、虚拟环境已激活时执行。

**1. 初始化数据库（建表，不写数据）**

```powershell
python 运行脚本/init_db.py
```

看到"数据库初始化完成，表已就绪。"即可。脚本可重复执行，不会清空已有数据。

> **团队同步约定：** 每次拉取包含数据库表或字段变更的更新后，所有成员都应重新执行本步骤。初始化脚本会保留既有本地数据，并补建缺失表；不要仅因代码已更新就假定本机数据库结构已同步。

**2. 导入演示种子数据（可选）**

```powershell
python 运行脚本/import_sample_data.py
```

从 `数据资料/样例工单/工单样例.csv` 导入 5 条虚构工单。只导入数据库中还没有的编号，重复执行不会覆盖或清空。导入后可打开 `/tickets` 查看。

**3. 运行测试**

```powershell
python -m unittest discover -s 测试用例 -v
```

## 数据库备份与恢复

SQLite 数据库是单个文件，位于 `本地运行数据/triage.db`（该目录已被 `.gitignore` 忽略，不会提交到仓库）。

**备份**：先把平台停掉，再复制文件：

```powershell
Copy-Item 本地运行数据\triage.db 本地运行数据\triage.db.bak
```

**恢复**：用备份覆盖当前库：

```powershell
Copy-Item 本地运行数据\triage.db.bak 本地运行数据\triage.db -Force
```

恢复后重新启动平台即可。若要恢复到"空表"状态，删除 `triage.db` 后重新执行初始化脚本。

## 可选大模型客服参考（默认关闭）

`app/services/llm_advisor.py` 提供一个**可选的大模型参考层**，仅在 `tian` 分支用于试验。它不改变分诊结论，只生成客服可核对的文字参考。

- **默认关闭**：`.env` 中 `LLM_ENABLED` 与 `LLM_ALLOW_EXTERNAL_CALLS` 必须同时为 `true` 才会调用；缺密钥或配置不完整时保持禁用。
- **前置拦截**：工单存在安全风险、停机、关键信息缺失或规则已要求人工时，一律不调用。
- **脱敏**：发送前替换手机号、邮箱；含身份证等敏感身份信息时直接放弃调用。
- **输出约束**：只接受结构化 JSON，且类别必须与规则结论一致；非法输出全部丢弃。
- **只作参考**：结果写入操作留痕（`LLM_REFERENCE`），不写回 `predicted_category`、`priority`、`recommend_human` 等分诊字段；页面明确标注"不得作为维修结论或安全放行依据"。
- **调用留痕**：每次触发记录状态与原因，不保存外发描述、模型原文或密钥。

开启方法（仅在本地 `.env`，不要提交）：设置 `LLM_ENABLED=true`、`LLM_ALLOW_EXTERNAL_CALLS=true`、`LLM_PROVIDER=deepseek`、`DEEPSEEK_API_KEY=<你的密钥>`，然后到工单详情页点"生成客服参考"。

## 数据注意事项

样例数据为虚构内容。不要提交真实客户个人信息、未经授权的内部工单、密钥或本地数据库文件。维修知识需记录来源；模拟知识需明确标记为模拟。
