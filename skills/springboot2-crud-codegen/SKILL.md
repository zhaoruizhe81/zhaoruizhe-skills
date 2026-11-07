---
name: springboot2-crud-codegen
description: Use `springboot2-crud-codegen` as a black-box CLI to create or revise JSON configs, run project generation, and inspect generated Spring Boot 2 + MyBatis-Plus backend output with optional Vue 2 admin frontend output. Use when users ask to scaffold projects from JSON, edit `examples/*.json`, validate generated Java/SQL/Vue files, or report reproducible generation failures. Do not inspect, search, modify, debug, or extend generator source code, templates, or tests.
---

# springboot2-crud-codegen

- Treat the generator as an absolute black box.
- Allowed inputs: user-provided JSON configs, `examples/*.json`, this skill's references, CLI stdout/stderr, and generated output directories.
- Forbidden implementation files: `codegen/`, `codegen/templates/`, `tests/`, build metadata produced for package internals, and any generator source file.
- Do not search, read, summarize, patch, or test generator implementation internals, even when generation fails.
- Do not promise source fixes. For generator failures, provide a reproducible black-box report: config path, command, output directory, error text, and observed generated-file mismatch.

## 默认执行流程

1. 先判定任务类型：编写配置、修改配置、运行生成、验收生成结果、报告生成失败。
2. 只读当前任务需要的参考资料：
   - `references/project-guide.md`：黑盒工具能力、命令、输入输出、验收边界。
   - `references/config-guide.md`：JSON 结构、功能开关、字段级规则。
   - `references/task-playbook.md`：配置、生成、验收、失败报告步骤。
3. 优先从最近的示例配置增量修改：
   - 完整后台 + 权限 + 多租户 + 前端：`examples/sample_security.json` 或 `examples/preset_saas_multi_tenant.json`
   - 单表最小 CRUD：`examples/student_single_table.json`
   - 双表或联表：`examples/sample.json` 或 `examples/student_class_management.json`
   - 纯后台 API：`examples/preset_api_only.json`
   - 后台 + 前端 + 字典：`examples/preset_backend_frontend.json`
4. 运行真实黑盒命令验证：
   - `python -m codegen -c <config> -o <tmp>`
5. 检查生成目录和生成文件，而不是检查生成器源码：
   - `<output>/<artifactId>/backend`
   - `<output>/<artifactId>/frontend`（仅当前端启用）
   - `backend/pom.xml`
   - `backend/src/main/resources/application.yml`
   - `backend/src/main/resources/init.sql`
   - `backend/src/main/java/.../security/*`
   - `backend/src/main/java/.../controller/*`
   - `frontend/src/views/*`

## 工作规则

- 配置问题只能通过配置文档、示例配置、CLI 错误信息和生成结果判断。
- 生成结果不符合预期时，重新生成到临时目录并检查实际输出；不要回溯实现。
- 如果 CLI 报错明显指向 JSON 字段、枚举、缺失项或非法组合，可以修改配置后重跑。
- 如果 CLI 报错或输出缺陷无法通过配置解释，停止在黑盒边界，整理复现报告。
- 权限相关验收默认检查生成的 `init.sql`、安全类、认证接口、前端 `/auth/me` 消费、菜单过滤和 CRUD 按钮显隐。
- Swagger/Knife4j 相关验收默认检查生成的 `pom.xml`、`application.yml`、`SwaggerConfig.java` 和安全放行路径。
