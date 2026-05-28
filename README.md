# GitHub User Management

用于通过 GitHub REST API 批量管理 GitHub 用户账户的 Python CLI 脚本。

当前支持三类独立操作：

- 从指定 Organization 中移除用户
- 从指定 Organization 中移除除 Owner 之外的所有用户
- 列出可访问组织中的 Owner 和 Member 并导出 CSV
- 将用户添加到指定 Enterprise Team
- 将用户添加到指定 Cost Center

## 环境要求

- Python 3.10+
- GitHub Enterprise Cloud
- Personal Access Token (classic)

脚本仅使用 Python 标准库，不需要安装第三方依赖。

## Token 权限

建议使用 Personal Access Token (classic)，并按实际操作授予权限：

| 操作 | 推荐 scope |
| --- | --- |
| 从 Organization 移除用户 | `admin:org` |
| 添加到 Enterprise Team | `admin:enterprise` |
| 添加到 Cost Center | `admin:enterprise` |

Enterprise Team 和 Cost Center 相关 API 不适用于 fine-grained PAT。

可以通过环境变量提供 token：

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

也可以在命令中显式传入：

```bash
python manage_users.py --token ghp_xxxxxxxxxxxxxxxxxxxx ...
```

## 用户清单 CSV

CSV 文件必须包含 `username` 列。其他列会被忽略。

示例：

```csv
username
monalisa
octocat
```

仓库中提供了示例文件：[users.csv](users.csv)。

## 配置文件

仓库中提供了可提交的示例配置文件：[config.example.json](config.example.json)。本地真实配置文件使用 `config.json`，并已在 [.gitignore](.gitignore) 中忽略，避免把真实 token 提交到 GitHub。

首次使用时可以复制模板：

```bash
cp config.example.json config.json
```

配置文件可以提供通用参数和各子命令所需参数，命令行参数会覆盖配置文件中的同名配置。

示例结构：

```json
{
  "token": "YOUR_GITHUB_PAT_CLASSIC",
  "csv": "users.csv",
  "enterprise": "YOUR_ENTERPRISE_SLUG",
  "base_url": "https://api.github.com",
  "failed_csv": "failed_users.csv",
  "dry_run": true,
  "remove_from_org": {
    "org": "YOUR_ORG"
  },
  "remove_non_owners_from_org": {
    "org": "YOUR_ORG"
  },
  "export_org_members": {
    "output": "org_members.csv",
    "orgs": []
  },
  "add_to_team": {
    "team": "YOUR_ENTERPRISE_TEAM_SLUG_OR_ID"
  },
  "add_to_cost_center": {
    "cost_center": "YOUR_COST_CENTER_NAME_OR_ID"
  }
}
```

使用配置文件运行：

```bash
python manage_users.py --config config.json add-to-team
```

当前本地 `config.json` 已配置以下目标：

| 配置项 | 当前值 |
| --- | --- |
| Enterprise | `qifengemu` |
| Organization | `qifengemu-org1` |
| Enterprise Team | `qifengemu-team1` |
| Cost Center | `qifengemu-costcenter1` |
| Cost Center ID | 自动解析为 `84299cbd-6777-49f3-8fcf-6a2a20217459` |
| CSV | `users.csv` |
| 导出成员 CSV | `org_members.csv` |
| 导出组织范围 | `qifengemu-org1` |
| dry-run | `false` |

当前配置中的 token 不应写入 README。文档中一律使用脱敏占位值展示。

基于当前配置，可以直接运行：

```bash
python manage_users.py --config config.json remove-from-org
python manage_users.py --config config.json remove-non-owners-from-org
python manage_users.py --config config.json export-org-members
python manage_users.py --config config.json add-to-team
python manage_users.py --config config.json add-to-cost-center
```

当前配置中的 `export_org_members.orgs` 指定为 `qifengemu-org1`，因此 `export-org-members` 只会导出该组织。如果希望自动导出当前 token 可访问的所有组织，请将本地 `config.json` 中的 `orgs` 改为空数组：

```json
"export_org_members": {
  "output": "org_members.csv",
  "orgs": []
}
```

由于当前 `dry_run` 为 `false`，上述命令会真实调用 GitHub API。如需先预览操作，请在命令末尾加上 `--dry-run`。

覆盖配置文件中的某个值：

```bash
python manage_users.py --config config.json add-to-team --team ANOTHER_TEAM
```

配置文件支持 `token` 字段，但不建议把真实 token 提交到版本库；优先使用 `GITHUB_TOKEN` 环境变量或 `--token`。如果确实要在本地配置中使用 token，请只保存在本机私有文件中，并避免把该文件上传到 GitHub。

## 通用参数

通用参数可以放在子命令前，也可以放在子命令后。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--config` | 否 | JSON 配置文件路径 |
| `--csv` | 是 | 用户清单 CSV 路径 |
| `--token` | 否 | GitHub PAT classic；未提供时读取 `GITHUB_TOKEN` |
| `--enterprise` | Enterprise 操作必填 | Enterprise slug，例如企业设置 URL 中的 `https://github.com/enterprises/<slug>` |
| `--dry-run` | 否 | 只打印将执行的操作，不调用 GitHub API |
| `--base-url` | 否 | GitHub API 地址，默认 `https://api.github.com` |
| `--failed-csv` | 否 | 失败用户报告路径，默认 `failed_users.csv` |

如果使用 GHE.com dedicated subdomain，请指定：

```bash
--base-url https://api.SUBDOMAIN.ghe.com
```

## 1. 从 Organization 移除用户

先用 dry-run 检查将要移除的用户：

```bash
python manage_users.py remove-from-org \
  --csv users.csv \
  --org YOUR_ORG \
  --dry-run
```

执行真实移除：

```bash
python manage_users.py remove-from-org \
  --csv users.csv \
  --org YOUR_ORG
```

真实执行时，脚本会显示将移除的用户数量和组织名，并要求输入：

```text
yes
```

只有输入完全匹配 `yes` 时才会调用 API；其他输入会中止操作。

对应 API：

```text
DELETE /orgs/{org}/members/{username}
```

## 2. 从 Organization 移除除 Owner 之外的所有用户

这个命令会先调用 GitHub API 查询组织中 `role=member` 的成员，只移除非 Owner 用户。Owner 不会出现在该查询结果中，因此不会被删除。

先用 dry-run 检查将要移除的非 Owner 用户：

```bash
python manage_users.py remove-non-owners-from-org \
  --org YOUR_ORG \
  --dry-run
```

执行真实移除：

```bash
python manage_users.py remove-non-owners-from-org \
  --org YOUR_ORG
```

使用配置文件：

```bash
python manage_users.py --config config.json remove-non-owners-from-org --dry-run
```

真实执行时，脚本会显示将移除的用户数量和组织名，并要求输入：

```text
yes
```

只有输入完全匹配 `yes` 时才会调用删除 API；其他输入会中止操作。

对应 API：

```text
GET /orgs/{org}/members?role=member&per_page=100&page={page}
DELETE /orgs/{org}/members/{username}
```

## 3. 导出每个组织中的成员到 CSV

这个命令会列出当前 token 可访问的组织，并分别查询每个组织的 Owner 和 Member，导出到 CSV。

默认输出文件为 `org_members.csv`，该文件已在 [.gitignore](.gitignore) 中忽略。

导出所有可访问组织：

```bash
python manage_users.py export-org-members \
  --output org_members.csv
```

使用配置文件导出：

```bash
python manage_users.py --config config.json export-org-members
```

只导出指定组织，可以重复传入 `--org`：

```bash
python manage_users.py export-org-members \
  --org YOUR_ORG_1 \
  --org YOUR_ORG_2 \
  --output org_members.csv
```

配置文件中对应字段为：

```json
"export_org_members": {
  "output": "org_members.csv",
  "orgs": ["YOUR_ORG_1", "YOUR_ORG_2"]
}
```

如果 `orgs` 为空数组或省略，脚本会通过 `GET /user/orgs` 自动获取当前 token 可访问的组织。

CSV 字段：

```csv
organization,username,role
octo-org,monalisa,owner
octo-org,octocat,member
```

对应 API：

```text
GET /user/orgs?per_page=100&page={page}
GET /orgs/{org}/members?role=admin&per_page=100&page={page}
GET /orgs/{org}/members?role=member&per_page=100&page={page}
```

## 4. 添加用户到 Enterprise Team

先 dry-run：

```bash
python manage_users.py add-to-team \
  --csv users.csv \
  --enterprise YOUR_ENTERPRISE \
  --team YOUR_ENTERPRISE_TEAM \
  --dry-run
```

执行真实添加：

```bash
python manage_users.py add-to-team \
  --csv users.csv \
  --enterprise YOUR_ENTERPRISE \
  --team YOUR_ENTERPRISE_TEAM
```

`--team` 可以传入 GitHub API 可识别的 Enterprise Team slug 或 ID。如果你的 Enterprise Team slug 包含 `ent:` 前缀，请按实际 slug 一并传入。

对应 API：

```text
POST /enterprises/{enterprise}/teams/{enterprise-team}/memberships/add
```

请求 payload：

```json
{
  "usernames": ["monalisa", "octocat"]
}
```

## 5. 添加用户到 Cost Center

脚本支持两种方式：

- `--cost-center`：传入 Cost Center 名称或 ID，脚本会自动查询并解析真实 ID
- `--cost-center-id`：直接传入 GitHub API 要求的 Cost Center ID

配置文件中对应字段为：

```json
"add_to_cost_center": {
  "cost_center": "qifengemu-costcenter1"
}
```

也可以使用：

```json
"add_to_cost_center": {
  "cost_center_id": "84299cbd-6777-49f3-8fcf-6a2a20217459"
}
```

先 dry-run：

```bash
python manage_users.py add-to-cost-center \
  --csv users.csv \
  --enterprise YOUR_ENTERPRISE \
  --cost-center YOUR_COST_CENTER_NAME \
  --dry-run
```

执行真实添加：

```bash
python manage_users.py add-to-cost-center \
  --csv users.csv \
  --enterprise YOUR_ENTERPRISE \
  --cost-center YOUR_COST_CENTER_NAME
```

如果你已经知道真实 ID，也可以使用：

```bash
python manage_users.py add-to-cost-center \
  --csv users.csv \
  --enterprise YOUR_ENTERPRISE \
  --cost-center-id YOUR_COST_CENTER_ID
```

对应 API：

```text
POST /enterprises/{enterprise}/settings/billing/cost-centers/{cost_center_id}/resource
```

请求 payload：

```json
{
  "users": ["monalisa", "octocat"]
}
```

## 失败报告

脚本执行后会打印摘要：

```text
Summary
  Success: 2
  Failed:  0
  Skipped: 0
```

如果存在失败用户，会写入 `failed_users.csv`，字段如下：

```csv
username,status_code,message
monalisa,403,Forbidden
```

如果本次没有失败，脚本会删除旧的失败报告，避免误读上一次运行结果。

## 常见用法

公共参数放在子命令前：

```bash
python manage_users.py --csv users.csv --enterprise YOUR_ENTERPRISE --dry-run add-to-team --team YOUR_TEAM
```

公共参数放在子命令后：

```bash
python manage_users.py add-to-team --csv users.csv --enterprise YOUR_ENTERPRISE --dry-run --team YOUR_TEAM
```

两种写法都支持。

## 本地验证

运行单元测试：

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest test_manage_users.py
```

运行语法检查：

```bash
python -m py_compile manage_users.py test_manage_users.py
```

## 注意事项

- `remove-from-org` 和 `remove-non-owners-from-org` 是破坏性操作，建议始终先运行 `--dry-run`。
- 如果用户通过 Enterprise Team 获得 Organization 的间接成员身份，从 Organization 移除直接成员关系后，间接访问可能仍然存在。
- 如果 Enterprise Team 与 IdP 同步，GitHub API 可能拒绝直接修改 team membership。
- Cost Center API 需要 Enterprise 侧已启用相关 billing 功能，并要求调用者具备相应 Enterprise 权限。
