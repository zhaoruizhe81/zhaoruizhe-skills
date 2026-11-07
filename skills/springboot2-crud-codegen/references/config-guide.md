# 配置文档

## 目录

- [先记住这 8 条](#先记住这-8-条)
- [顶层结构](#顶层结构)
- [安全与权限配置 (Security/RBAC)](#安全与权限配置-securityrbac)
- [字典配置 (Dictionaries)](#字典配置-dictionaries)
- [多租户配置 (Multi-tenancy)](#多租户配置-multi-tenancy)
- [后端与其他配置](#后端与其他配置)
- [`tables[]` 完整说明](#tables-完整说明)
- [文件上传组件](#文件上传组件)
- [`relations[]` 完整说明](#relations-完整说明)
- [数据导出与测试生成](#数据导出与测试生成)

## 先记住这 8 条

1. 几乎所有对象都不允许出现未声明字段；多写一个键也会报错。
2. 顶层必须有 `project`、`datasource`、`tables`、`relations`、`global`；`security`、`backend`、`frontend` 可选。
3. 如果开启 `security.enabled`，不要手动在 JSON 里建 `sys_user` 这种表，生成器会自动补齐系统表。
4. `queryableFields` 在每张表里也是必填；如果不需要查询条件，写空数组 `[]`。
5. `relations` 顶层也是必填；如果没有联表关系，写空数组 `[]`。
6. `bootVersion` 必须以 `2.` 开头，`javaVersion` 当前只能是 `8`。
7. 单表和联表排序都必须显式走白名单，不能自由传任意字段名。
8. 联表查询遇到含有 `logicDelete: true` 的表时，渲染层会自动给你补上 `AND is_deleted = 0` 的判断。

## 顶层结构

合法骨架建议写成这样：

```json
{
  "project": {},
  "datasource": {},
  "security": {},
  "backend": {},
  "frontend": {},
  "tables": [],
  "relations": [],
  "global": {}
}
```

## 安全与权限配置 (Security/RBAC)

这部分配置负责生成 Spring Security + JWT，以及五张核心系统表。

### 顶层 `security`
```json
"security": {
  "enabled": true,
  "type": "jwt",
  "jwt": {
    "secret": "your-256-bit-secret-string",
    "expiration": 86400,
    "header": "Authorization",
    "prefix": "Bearer "
  },
  "rbac": {
    "strategy": "role_permission",
    "superAdminRole": "ROLE_ADMIN",
    "defaultRoles": ["ROLE_USER"]
  }
}
```
**行为说明**：
- 一旦 `enabled: true`，生成的项目 `pom.xml` 自动引入 Security 和 JJWT。
- 自动生成 `WebSecurityConfig`、`JwtTokenUtil`、`AuthController` 等核心类。
- 配置里的角色名会被统一规范成 `ROLE_*`；因此 `ADMIN`、`admin`、`ROLE_ADMIN` 最终都会按 `ROLE_ADMIN` 处理。
- 生成四个开箱即用的认证接口：
  - `POST /api/auth/login` — 验证账密，返回 JWT Token
  - `POST /api/auth/register` — 注册新账号（BCrypt 加密密码，自动绑定 `rbac.defaultRoles` 中的角色；未配置时默认 `ROLE_USER`）
  - `GET /api/auth/me` — 凭 Token 返回当前用户名 + 角色 + 权限列表（便于前端渲染菜单权限）
  - `POST /api/auth/change-password` — 先 BCrypt 校验旧密码，再加密存储新密码
- 如果同时开启了 `frontend.enabled`，生成的 Vue 2 前端会在登录后和受保护路由跳转时调用 `/api/auth/me`，并把返回的 `roles` / `permissions` 用于路由守卫、侧边菜单过滤、仪表盘快捷入口过滤，以及 CRUD 页面新增/编辑/删除按钮显隐。
- 生成器会隐式生成 `sys_user`, `sys_role`, `sys_user_role`, `sys_menu_permission`, `sys_role_permission` 这 5 张表的 Entity, Mapper, Service, Controller。
- 默认在 `init.sql` 里塞入账号 `admin` / 密码 `123456`（经过 BCrypt 加密，可直接登录）的数据。
- `init.sql` 还会自动补齐：
  - 超级管理员角色
  - 默认注册角色
  - 业务表和联表自动生成的权限点
  - 超级管理员角色到这些权限点的映射

### 表级/关联级的 `auth`
```json
"tables": [
  {
    "name": "products",
    "auth": {
      "enabled": true,
      "roles": ["ADMIN", "MANAGER"],
      "permissions": {
        "query": "product:view",
        "create": "product:add",
        "update": "product:edit",
        "delete": "product:delete"
      }
    }
  }
]
```
**行为说明**：
- 如果没有写 `auth.permissions`，生成器会自动按 `<table_name>:view` 这类规则兜底补全。
- `roles` 中可以写 `ADMIN` 或 `ROLE_ADMIN`，最终都会按同一套角色语义处理。
- 生成 Controller 时，会拼接为：`@PreAuthorize("hasAnyRole('ADMIN', 'MANAGER') or hasAuthority('product:add')")`。
- 如果前端也启用，同一份 `auth` 会被传到前端模板，生成与后端一致的页面访问和按钮显隐规则；前端做的是体验层过滤，最终安全边界仍以后端接口权限为准。
- 同时，表级 `POST /import` 会复用 create 对应的角色/权限规则，不再只是“登录即可导入”。

## 全局功能特性 (Global Features)

除了常规的实体生成，可以在 `global` 下开启额外的拦截器或 API 增强。

### 多租户配置 (Multi-tenancy)

通过 MyBatis-Plus `TenantLineInnerInterceptor` 实现请求级别隔离。

```json
"global": {
  "apiPrefix": "/api",
  "author": "codegen",
  "dateTimeFormat": "yyyy-MM-dd HH:mm:ss",
  "enableSwagger": false,
  "tenant": {
    "enabled": true,
    "column": "tenant_id"
  }
}
```
**行为说明**：
- 开启后，生成的 `MybatisPlusConfig.java` 注入多租户拦截器。
- `JwtAuthenticationFilter` 会自动尝试从 HTTP Header 的 `X-Tenant-Id` 或 JWT claims 里读取 tenant ID 存入 `TenantContextHolder` (ThreadLocal)。
- 之后所有增删改查 SQL MyBatis-Plus 都会自动拼上 `WHERE tenant_id = ?`。
- 生成器会自动忽略 `sys_user`、`sys_role`、`sys_user_role`、`sys_menu_permission`、`sys_role_permission`、`sys_dict_type`、`sys_dict_item`、`sys_log` 等系统表，避免认证、字典读取和日志写入被租户条件误拦。

### Swagger/Knife4j 接口文档生成

这部分配置负责自动引入依赖和生成详尽的接口文档注释配置。

```json
"global": {
  "enableSwagger": true
}
```
**行为说明**：
- 当 `enableSwagger: true` 时，生成的后端 `pom.xml` 中将自动注入 `@github.xiaoymin:knife4j-spring-boot-starter` 依赖。
- 生成一个支持分组的全局 `SwaggerConfig.java` 配置文件。
- 自动分析所有表(`table.comment`)及字段(`field.comment`)信息，利用 `@Api`、`@ApiOperation`、`@ApiModel`、`@ApiModelProperty` 等注解在生成的 Controller、Entities 以及 DTO 类上提供清晰友好的文档注释。
- 生成的 `application.yml` 会自动写入 `spring.mvc.pathmatch.matching-strategy: ant_path_matcher`，用于 Spring Boot 2.6+ 与 Springfox/Knife4j 的兼容。
- 生成的 `WebSecurityConfig` 会自动放行 `/doc.html`、`/swagger-ui/**`、`/swagger-resources/**`、`/v2/api-docs`、`/webjars/**` 等文档路径。启动后可访问 `/doc.html` 查看。

## 字典配置 (Dictionaries)

顶层可以声明可复用字典：

```json
"dictionaries": [
  {
    "key": "user_status",
    "name": "用户状态",
    "valueType": "integer",
    "items": [
      {"label": "禁用", "value": 0, "sort": 10, "enabled": true},
      {"label": "启用", "value": 1, "sort": 20, "enabled": true}
    ]
  }
]
```

字段通过 `dictKey` 绑定：

```json
{
  "name": "status",
  "type": "int",
  "nullable": false,
  "dictKey": "user_status"
}
```

**行为说明**：
- `dictKey` 必须引用已存在的顶层字典。
- `dictKey` 和 `frontend.options` 不能同时使用。
- 生成器会自动注入 `sys_dict_type`、`sys_dict_item` 及其种子数据。
- 后端额外生成字典管理 CRUD 与 `GET /api/system/dictionaries/{dictKey}/items`。
- 前端表单和查询会远程拉取字典选项。
- 导出 Excel 写标签，导入 Excel 同时接受标签和值。

## 后端与其他配置

### `backend`
```json
"backend": {
  "outputDir": "backend",
  "uploadDir": "uploads"
}
```
- `uploadDir` 会在生成的项目中产生一个 `FileController.java`，暴露 `/api/common/upload` 端点供前端调用。该端点将文件存入本地该目录，并提供静态资源映射。

## `tables[]` 完整说明

必填字段：`name`, `comment`, `entityName`, `fields`, `primaryKey`, `queryableFields`。

### 逻辑删除与联表
如果你的表中配置了：
```json
{"name": "is_deleted", "type": "tinyint(1)", "logicDelete": true, "comment": "是否删除"}
```
工具不仅为它加上 `@TableLogic`，而且当这表参与 `relations` 联查时，Mapper XML 会智能探测到，并在 `WHERE 1=1` 后强行加上 `AND l.is_deleted = 0` 防止脏数据泄露！

## 文件上传组件

在 `fields[].frontend.component` 中支持新组件：
- `image-upload`
- `file-upload`

配置示例：
```json
"frontend": {
  "label": "产品封面",
  "component": "image-upload"
}
```
生成器在遇到这两个组件时，不仅会输出 `<el-upload>`，还会自动获取 JWT Token (`localStorage.getItem('token')`) 注入请求头，防止上传接口报 401 错误。
在开启安全时，Token 会按 `<artifactId>_token` 的 key 存储，并由生成的前端鉴权工具统一管理。

## 智能前端表单校验 (Vue Form Validation)

生成器能够通过提取数据库字段的约束要求，自动在 `<el-form>` 以及 `$data.formRules` 中埋入对应的校验逻辑。这是**开箱即用**的功能。

- **必填校验 (`required`)**：如果某个字段设为 `nullable: false`，则会在 `rules` 里自动生成 `{ required: true, message: "xxx is required", trigger: "..." }`，在前端弹窗点击”保存“时自动拦截空输入。
- **长度校验 (`max`)**：如果字段类型为 `varchar(50)` (即携带最大长度约束的 `db_type`)，表单验证规则会自动附加上 `{ max: 50, message: "长度不能超过 50 个字符" }`。

## `relations[]` 完整说明

每一个 relation 都会生成一个只读联表分页接口。

必填：`name`, `leftTable`, `rightTable`, `joinType`, `dtoName`, `methodName`, `on`, `select`, `filters`。

注意：现在联表接口同样受 `relation.auth` 的权限保护。

## 数据导出与测试生成

这两个特性**开箱即用，无需额外 JSON 配置**：

1. **Excel 导出**：每个普通的 Table 都会生成一个 `XxxExportDto.java` 类（字段自动打上中文的 `@ExcelProperty`），Controller 里自动暴露 `@GetMapping("/export")` 端点，流式输出 Excel 文件。
2. **单元测试**：生成器会在 `src/test/java/.../controller/` 目录下为所有表生成基于 `@WebMvcTest` + `@MockBean` 的 Spring Boot 集成测试代码，确保项目交付即拥有基础覆盖率。

## 自动生成的通用功能（无需 JSON 配置）

以下功能在每次生成时自动包含，不需要在 JSON 配置中开启：

### Excel 批量导入
- 每张业务表自动生成 `POST /<resource>/import` 接口。
- 接受 `MultipartFile`，用 EasyExcel `PageReadListener` 逐页读取，调用 `saveBatch()` 批量插入。
- 与 `/export` 完全对称，生成的 `ExportDto` 类同时作为导入模板。

### 批量删除
- 每张业务表自动生成 `DELETE /<resource>/batch` 接口。
- 接受 `List<ID>` 请求体，调用 MyBatis-Plus `deleteBatchIds()` 一次性删除。

### 操作日志 AOP
- 自动生成 `@SystemLog("描述")` 注解 + `SystemLogAspect` 切面。
- 切面通过 `@AfterReturning` 在 Controller 方法成功返回后自动记录：操作人（来自 JWT）、请求 URI、客户端 IP、时间戳。
- 记录存入 `sys_log` 表（每次生成 `init.sql` 均包含该建表语句）。
- `create`、`update`、`delete`、`batch delete`、`import` 方法均自动加上 `@SystemLog` 注解。

### 仪表盘统计
- 自动生成 `DashboardController`，暴露 `GET /api/dashboard/stats` 端点。
- 返回所有业务表的 `totalCount`（总记录数）和 `todayCount`（今日 `created_at >= 00:00` 的记录数）。
- 适合后台管理首页的数据概览卡片直接调用。
