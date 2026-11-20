# 售后报修智能分诊平台

## 文件放置说明

- `app/`：平台程序代码，包括网页路由、数据模型、业务流程和分诊/检索算法。
- `run.py`：启动平台的程序入口。
- `requirements.txt`：Python依赖清单。
- `数据资料/样例工单/工单样例.csv`：虚构报修工单样例。
- `数据资料/维修知识/知识库.csv`：正式维修知识库及公开来源字段。
- `运行脚本/`：数据库初始化、种子数据导入、模型训练和评估脚本。
- `本地运行数据/`：本机SQLite数据库和模型文件，不提交实际运行数据。
- `测试用例/`：分诊规则、分类、检索和流程测试。
- `data/fault_taxonomy.json`：模块1故障词表（v0.1，只读展示，不参与分诊判断；说明见 `data/词表说明.md`）。
- `docs/fault-taxonomy-fields.md`：词表字段说明。
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

> 若本机已经有旧版数据库，而新拉取的代码新增了数据表（例如客服操作留痕表 `ticket_actions`），也应再次执行本步骤，以补建缺失表。

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
