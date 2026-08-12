# Task 2 执行报告 — 文件管理：时间格式 + 前端校验

## Status: ✅ 已完成

所有 4 个步骤均已完成，无需回滚。

---

## Changes Made

### Step 1: 后端 `app/api/routes.py`
- **L3**: 新增 `from datetime import datetime` 导入
- **L237**: `modified_time=str(stat.st_mtime)` → `modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat()`
- 效果：`list_files()` API 返回的 `modified_time` 字段由浮点时间戳字符串改为 ISO 8601 格式（如 `2026-08-12T10:30:00`）

### Step 2: 前端 `frontend/js/app.js` — 新增 `formatRelativeTime()`
- **L868-L878**: 在 `formatFileSize()` 之后新增 `formatRelativeTime(isoStr)` 函数
- 逻辑：将 ISO 字符串转为人类可读的相对时间（刚刚 / N 分钟前 / N 小时前 / N 天前 / 日期）

### Step 3: 前端 `frontend/js/app.js` — 修改 `loadFileList()` 模板
- **L906**: file-meta 行增加 `formatRelativeTime(f.modified_time)` 显示
- 修改前：`${formatFileSize(f.size)} · ${f.file_type.toUpperCase()}`
- 修改后：`${formatFileSize(f.size)} · ${f.file_type.toUpperCase()} · ${formatRelativeTime(f.modified_time)}`

### Step 4: 前端 `frontend/js/app.js` — 修改 `handleFileUpload()`
- **L926-L930**: 在 `const file = files[0];` 之后、`const formData = new FormData()` 之前，新增 50MB 文件大小校验
- 超过限制时调用 `showToast()` 显示错误提示（含 `formatFileSize(MAX_SIZE)` 格式化大小），并 `return` 阻止上传

---

## Verification

验证点（按 task-2-brief.md 要求）：
1. 切换到「知识库」标签页，文件列表中的时间应显示为"2 小时前"等人类可读格式
2. 选择超过 50MB 的文件，应弹出错误提示"文件大小超过限制（50 MB），请压缩后重试"，不发起上传请求
3. 正常上传小文件，上传成功

注：以上验证需在启动后端服务后手动执行。

---

## Concerns

无。所有修改均为精确替换，未引入新功能或副作用。