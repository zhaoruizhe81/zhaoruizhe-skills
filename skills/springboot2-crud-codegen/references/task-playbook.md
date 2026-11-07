# 任务执行手册

## 目录

- [编写或修改配置](#编写或修改配置)
- [运行黑盒生成](#运行黑盒生成)
- [验收生成输出](#验收生成输出)
- [报告生成失败](#报告生成失败)
- [检查前端生成结果](#检查前端生成结果)

## 编写或修改配置

1. 先选最近的示例：
   - `examples/student_single_table.json`：单表 CRUD
   - `examples/sample.json`：基础双表与联表
   - `examples/student_class_management.json`：更完整的学生/班级管理
   - `examples/sample_security.json`：权限、多租户、前端、企业级能力
   - `examples/preset_api_only.json`：纯后台 API
   - `examples/preset_backend_frontend.json`：后台 + 前端 + 字典
   - `examples/preset_saas_multi_tenant.json`：多租户 SaaS
   - `examples/preset_audit_admin.json`：审计后台
   - `examples/preset_light_auth.json`：轻权限项目
2. 再读 `references/config-guide.md`，确认顶层键、`tables[]`、`relations[]`、`global`、`security`、`frontend` 的要求。
3. 增量修改配置，优先保持已有结构；不要一次性引入大量新字段。
4. 修改后立即运行黑盒生成命令；不要检查生成器源码。

## 运行黑盒生成

1. 使用真实配置运行：
   - `python -m codegen -c <config> -o /tmp/codegen-out`
2. 确认输出目录为：
   - `/tmp/codegen-out/<artifactId>/backend`
   - `/tmp/codegen-out/<artifactId>/frontend`（仅当前端启用）
3. 如需避免覆盖已有输出，换一个新的临时目录。
4. 只根据 CLI 输出、退出状态和生成文件判断结果。

## 验收生成输出

1. 后端基础文件：
   - `backend/pom.xml`
   - `backend/src/main/resources/application.yml`
   - `backend/src/main/resources/init.sql`
   - `backend/src/main/java/.../controller/*`
   - `backend/src/main/java/.../service/*`
   - `backend/src/main/resources/mapper/*`
2. 高级功能文件：
   - 权限：`backend/src/main/java/.../security/*` 与 `AuthController`
   - 上传：`backend/src/main/java/.../common/FileController.java`
   - 日志：`SystemLog.java` 与 `SystemLogAspect.java`
   - 仪表盘：`DashboardController.java`
   - Swagger：`application.yml`、`SwaggerConfig.java`、`WebSecurityConfig.java`
3. 验收只看生成项目文件；不要打开生成器实现文件。

## 报告生成失败

当问题无法通过 JSON 配置直接解释时，停止在黑盒边界并报告：

1. 使用的配置文件路径。
2. 完整生成命令。
3. 输出目录路径。
4. CLI 退出码和关键 stdout/stderr。
5. 期望生成结果与实际生成结果的差异。
6. 已检查过的生成文件路径。

不要尝试定位或修复生成器源码。

## 检查前端生成结果

1. 先确认顶层 `frontend.enabled=true`，并检查 `framework`、`locale`、`outputDir`、`backendUrl`、`devPort`。
2. 再检查表和字段上的 `frontend` 配置，尤其是：
   - `menuTitle`
   - `menuIcon`
   - `menuVisible`
   - `component`
   - `queryComponent`
   - `tableVisible`
   - `formVisible`
3. 上传组件问题优先检查字段 `frontend.component` 是否为 `image-upload` 或 `file-upload`，以及后端 `backend.uploadDir` 是否存在。
4. 表单校验问题优先检查字段的 `nullable`、`varchar(n)` 长度与生成的 `rules`。
5. 权限相关前端验收检查生成后的：
   - `frontend/src/api/auth.js`
   - `frontend/src/utils/auth.js`
   - `frontend/src/router/index.js`
   - `frontend/src/layout/Layout.vue`
   - `frontend/src/views/*/index.vue`
6. 不要只验证“有没有 token”；要验证 `/auth/me` 的 `roles` / `permissions` 是否真的参与了路由守卫、菜单过滤、仪表盘入口过滤和 CRUD 按钮显隐。
