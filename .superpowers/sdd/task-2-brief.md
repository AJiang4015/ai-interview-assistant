### Task 2: 文件管理 — 时间格式 + 前端校验

**Files:**
- Modify: `app/api/routes.py` —— `list_files()` 中 modified_time 改为 ISO 格式
- Modify: `frontend/js/app.js` —— 新增 `formatRelativeTime()`、修改 `loadFileList()` 和 `handleFileUpload()`

**Interfaces:**
- Produces: `formatRelativeTime(isoStr: string) → string` —— 人类可读的相对时间
- Modifies: `loadFileList()` —— 文件列表中的 file-meta 使用 formatRelativeTime
- Modifies: `handleFileUpload(files: FileList)` —— 开头添加文件大小校验

**Global Constraints:**
- 不新增功能，只修复正确性
- 50MB 文件大小限制与后端保持一致

- [ ] **Step 1: 后端 modified_time 改为 ISO 格式**

在 `app/api/routes.py` 中，修改 `list_files()` 函数（L215-L240），将 `str(stat.st_mtime)` 替换为 ISO 格式。需要先在文件顶部添加 `from datetime import datetime`：

```python
# 文件顶部添加（如果尚未导入）
from datetime import datetime

# 在 list_files() 中修改（L236）
# 修改前
modified_time=str(stat.st_mtime),

# 修改后
modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
```

- [ ] **Step 2: 前端新增 formatRelativeTime() 函数**

在 `frontend/js/app.js` 中，在 `formatFileSize()` 函数之后（L859 之后）添加：

```javascript
// 格式化相对时间：ISO 字符串 → "2 小时前"
function formatRelativeTime(isoStr) {
    const date = new Date(isoStr);
    const now = new Date();
    const diff = (now - date) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
    if (diff < 2592000) return `${Math.floor(diff / 86400)} 天前`;
    return date.toLocaleDateString('zh-CN');
}
```

- [ ] **Step 3: 修改 loadFileList() 使用 formatRelativeTime**

在 `frontend/js/app.js` 中，修改 `loadFileList()` 函数中文件列表的 file-meta 渲染（L887）：

```javascript
// 修改前
<div class="file-meta">${formatFileSize(f.size)} · ${f.file_type.toUpperCase()}</div>

// 修改后
<div class="file-meta">${formatFileSize(f.size)} · ${f.file_type.toUpperCase()} · ${formatRelativeTime(f.modified_time)}</div>
```

- [ ] **Step 4: 修改 handleFileUpload() 添加前端文件大小校验**

在 `frontend/js/app.js` 中，修改 `handleFileUpload()` 函数开头（L903-L906）：

```javascript
// 修改前
function handleFileUpload(files) {
    if (!files || files.length === 0) return;

    const file = files[0];
    const formData = new FormData();

// 修改后
function handleFileUpload(files) {
    if (!files || files.length === 0) return;

    const file = files[0];
    const MAX_SIZE = 50 * 1024 * 1024; // 50MB
    if (file.size > MAX_SIZE) {
        showToast(`文件大小超过限制（${formatFileSize(MAX_SIZE)}），请压缩后重试`, 'error');
        return;
    }

    const formData = new FormData();
```

- [ ] **Step 5: 验证**

```bash
cd e:\CodeField\RAGKonwLedge
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

验证点：
- 切换到「知识库」标签页，确认文件列表中的时间显示为"2 小时前"等人类可读格式
- 尝试选择一个超过 50MB 的文件，应弹出错误提示，不发起上传请求
- 正常上传一个小文件，确认上传成功