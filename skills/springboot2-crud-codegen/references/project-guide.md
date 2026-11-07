# 项目总览

## 目录

- [工具定位](#工具定位)
- [黑盒边界](#黑盒边界)
- [示例配置起点](#示例配置起点)
- [关键命令](#关键命令)
- [重要输入与输出](#重要输入与输出)
- [验收要点](#验收要点)
- [项目边界](#项目边界)

## 工具定位

`springboot2-crud-codegen` 是一个黑盒 Python CLI。它把 JSON 配置转换成企业级 Spring Boot 2 + MyBatis-Plus CRUD 工程，并可选生成独立 Vue 2 + Element UI 管理前端。

默认可生成或注入的能力包括：

- Spring Security + JWT + RBAC
- 多租户拦截器
- Swagger/Knife4j 文档
- Excel 导入/导出
- 文件上传
- 操作日志 AOP
- 批量删除
- 仪表盘统计
- MockMvc 单元测试
- 带表单校验的 Vue 2 管理前端

## 黑盒边界

- 允许读取和修改：用户配置、`examples/*.json`、本 skill 的参考文档、CLI 输出、生成后的项目文件。
- 禁止读取、搜索、总结、修改：生成器源码、模板、测试和内部实现文件。
- 生成失败时，只基于命令、配置、CLI 输出和生成目录写复现报告。
- 不提出源码级修复方案，不让用户去改内部实现。

## 示例配置起点

- `examples/student_single_table.json`：单表 CRUD 最小起点
- `examples/sample.json`：双表与基础联表查询
- `examples/student_class_management.json`：更完整的教学管理示例
- `examples/sample_security.json`：权限、多租户、前端、企业级能力最全的起点
- `examples/preset_api_only.json`：纯后台 API 起步
- `examples/preset_backend_frontend.json`：后台 + 前端 + 字典起步
- `examples/preset_saas_multi_tenant.json`：SaaS 多租户起步
- `examples/preset_audit_admin.json`：审计型后台起步
- `examples/preset_light_auth.json`：轻权限起步

优先复制最近的示例再增量修改，不要从空白 JSON 开始拼大配置。

## 关键命令

- 安装：`python -m pip install -e .`
- 运行模块：`python -m codegen -c examples/sample_security.json -o /tmp/codegen-out`
- 运行控制台命令：`codegen -c examples/sample_security.json -o /tmp/codegen-out`

## 重要输入与输出

- 典型输入：`examples/sample_security.json`
- 后端输出：`<output>/<artifactId>/backend/...`
- 前端输出：`<output>/<artifactId>/frontend/...`，仅在 `frontend.enabled = true` 时生成

常看生成文件：

- `backend/pom.xml`
- `backend/src/main/resources/application.yml`
- `backend/src/main/resources/init.sql`
- `backend/src/main/java/<basePackage>/security/*`
- `backend/src/main/java/<basePackage>/controller/*`
- `backend/src/main/java/<basePackage>/common/FileController.java`
- `backend/src/main/java/<basePackage>/common/annotation/SystemLog.java`
- `backend/src/main/java/<basePackage>/common/aspect/SystemLogAspect.java`
- `backend/src/main/java/<basePackage>/controller/DashboardController.java`
- `backend/src/test/java/<basePackage>/controller/*Test.java`
- `frontend/src/views/login/index.vue`
- `frontend/src/views/<xxx>/index.vue`
- `frontend/src/utils/request.js`
- `frontend/src/api/auth.js`
- `frontend/src/utils/auth.js`
- `frontend/src/router/index.js`
- `frontend/src/layout/Layout.vue`

## 验收要点

- RBAC 角色名最终表现为 `ROLE_*`，并同步体现在 `init.sql`、注册默认角色、权限表达式与 `/auth/me` 返回。
- 当前端启用且安全开启时，前端要消费 `/auth/me`，并把角色/权限用于路由守卫、菜单、仪表盘入口和 CRUD 按钮显隐。
- `POST /import` 应与 create 权限一致，登录页成功后应尽量回跳到原始受保护地址。
- `global.enableSwagger = true` 时，生成的 `application.yml` 应包含兼容配置，安全配置应放行文档路径。
- `global.tenant.enabled = true` 时，认证、字典、日志等系统能力不应被租户条件误拦。

## 项目边界

- 仅支持 Java 8
- 仅支持 Spring Boot 2.x
- SQL 与 datasource 以 MySQL 为主
- 前端仅支持 Vue 2 + Element UI
