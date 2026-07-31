# GitHub User Management

用于通过 GitHub REST API 批量管理 GitHub 用户账户的 Python CLI 脚本。

常见使用流程分为三步：

1. 导出 Organization 中的用户，更新 users.csv
2. 移除 Organization 中除 Owner 之外的所有用户
3. 添加用户到 Enterprise Team

此外还支持两个独立操作：

- 按 CSV 清单从指定 Organization 中移除用户
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

仓库中提供了可提交的示例配置文件：[config.example.json](config.example.json)。

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

### 通用配置项

| 配置项 | 说明 |
| --- | --- |
| `token` | GitHub PAT (classic)。优先级：`--token` > `GITHUB_TOKEN` 环境变量 > 配置文件。不建议把真实 token 提交到版本库 |
| `csv` | 用户清单 CSV 路径，必须包含 `username` 列。用于 `remove-from-org`、`add-to-team`、`add-to-cost-center` |
| `enterprise` | Enterprise slug，即企业设置 URL `https://github.com/enterprises/<slug>` 中的 `<slug>`。Enterprise Team 和 Cost Center 操作必填 |
| `base_url` | GitHub API 地址，默认 `https://api.github.com`。GHE.com 使用 `https://api.SUBDOMAIN.ghe.com` |
| `failed_csv` | 失败用户报告输出路径，默认 `failed_users.csv` |
| `dry_run` | 设为 `true` 时只打印将执行的操作，不调用 GitHub API。命令行 `--dry-run` 也可开启 |

### 子命令配置项

| 配置项 | 说明 |
| --- | --- |
| `remove_from_org.org` | 要移除用户的 Organization 名称 |
| `remove_non_owners_from_org.org` | 要移除非 Owner 成员的 Organization 名称 |
| `export_org_members.output` | 导出成员的 CSV 输出路径，默认 `org_members.csv` |
| `export_org_members.orgs` | 要导出的 Organization 数组。为空数组或省略时，自动导出当前 token 可访问的所有组织 |
| `add_to_team.team` | 目标 Enterprise Team 的 slug 或 ID |
| `add_to_cost_center.cost_center` | 目标 Cost Center 的名称或 ID，脚本会自动解析为真实 ID |
| `add_to_cost_center.cost_center_id` | 直接指定 Cost Center ID，跳过名称解析。与 `cost_center` 二选一 |

## 1. 导出 Organization 中的用户，更新 users.csv

这个命令会列出当前 token 可访问的组织，并分别查询每个组织的 Owner 和 Member，导出到 CSV。

默认输出文件为 `org_members.csv`，该文件已在 [.gitignore](.gitignore) 中忽略。

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

### 用导出结果更新 users.csv

导出的 CSV 已包含 `username` 列，脚本读取 CSV 时会忽略其他列，因此可以直接覆盖 `users.csv`：

```bash
python manage_users.py export-org-members --org YOUR_ORG --output org_members.csv
cp org_members.csv users.csv
```

如果只需要处理部分用户，请在覆盖后删除不需要的行（保留表头）。

## 2. 从 Organization 移除除 Owner 之外的所有用户

这个命令会先调用 GitHub API 查询组织中 `role=member` 的成员，只移除非 Owner 用户，无需读取用户清单 CSV。Owner 不会出现在该查询结果中，因此不会被删除。

先用 dry-run 检查将要移除的非 Owner 用户：

```bash
python manage_users.py remove-non-owners-from-org \
  --config config.json \
  --dry-run
```

执行真实移除：

```bash
python manage_users.py remove-non-owners-from-org \
  --config config.json
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

## 3. 添加用户到 Enterprise Team

执行真实添加：

```bash
python manage_users.py add-to-team \
  --csv users.csv \
  --config config.json
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

## 4. 按 CSV 清单从 Organization 移除用户

这个命令只移除 `users.csv` 中列出的用户，适合需要精确控制移除范围的场景。

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
