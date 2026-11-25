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

**1. 初始化数据库（建表并首次导入公开知识资料）**

```powershell
python 运行脚本/init_db.py
```

看到"数据库初始化完成，表已就绪。"即可。脚本可重复执行，不会清空已有数据；首次运行会导入仓库随附的公开知识资料，后续不会重复导入。

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

## 数据注意事项

样例数据为虚构内容。不要提交真实客户个人信息、未经授权的内部工单、密钥或本地数据库文件。维修知识需记录来源；模拟知识需明确标记为模拟。

## 对话式报修信息采集助手（可选）

平台在“提交报修”和“待补充信息”阶段提供可选的对话式信息采集助手。它只通过多轮对话帮助用户补充设备状态、报警代码和可观察现象；不会输出故障类别、优先级、维修结论或直接执行工单操作。用户采用字段建议后，工单仍由既有字段校验、规则分诊和知识匹配流程处理。

默认不调用外部模型。若仅使用虚构/已授权且已脱敏的文本，可在本机 `.env` 中设置：

```powershell
LLM_ENABLED=true
LLM_ALLOW_EXTERNAL_CALLS=true
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的密钥
```

默认单次输出额度为 1200，避免推理型模型因先生成内部推理而截断可见回复；如在本机 `.env` 中另行设置 `LLM_MAX_OUTPUT_TOKENS`，以本机设置为准。

也可将 `LLM_PROVIDER` 设为 `dashscope`，并配置 `DASHSCOPE_API_KEY`、`LLM_DASHSCOPE_BASE_URL` 和 `LLM_DASHSCOPE_MODEL`。阿里云百炼的兼容地址与工作空间和地域相关，需使用控制台提供的完整地址。密钥只能保存在 `.env`，不得提交到 Git。
