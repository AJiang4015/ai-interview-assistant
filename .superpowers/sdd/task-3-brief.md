### Task 3: 文件管理 — 上传时异步索引重建

**Files:**
- Modify: `app/api/routes.py` —— `upload_file()` 改为后台索引重建
- Modify: `frontend/js/app.js` —— 延长上传完成等待时间

**Interfaces:**
- Modifies: `POST /api/files/upload` —— 返回 `index_rebuilt: false`，索引在后台重建

**Global Constraints:**
- 不新增功能，只修复上传阻塞问题
- 使用 `asyncio.create_task()` 后台重建，不阻塞上传响应

- [ ] **Step 1: 添加 asyncio 导入**

在 `app/api/routes.py` 文件顶部添加：

```python
import asyncio
```

- [ ] **Step 2: 修改 upload_file() 为后台索引重建**

在 `app/api/routes.py` 中，修改 `upload_file()` 函数（L273-L291），将同步索引重建替换为后台任务：

```python
# 修改前（L273-L291）
    # 自动重建索引
    indexer = _get_indexer()
    try:
        result = await indexer.build_index(rebuild=True)
        return FileUploadResponse(
            success=True,
            filename=filename,
            message=f"文件上传成功，索引已重建",
            index_rebuilt=True,
            total_chunks=result.total_chunks
        )
    except Exception as e:
        logger.exception(f"Index rebuild after upload failed: {e}")
        return FileUploadResponse(
            success=True,
            filename=filename,
            message=f"文件上传成功，但索引重建失败: {e}",
            index_rebuilt=False
        )

# 修改后
    # 后台异步重建索引，不阻塞上传响应
    async def rebuild_index_background():
        try:
            indexer = _get_indexer()
            result = await indexer.build_index(rebuild=True)
            logger.info(f"Background index rebuild done: {result.total_chunks} chunks")
        except Exception as e:
            logger.exception(f"Background index rebuild failed: {e}")

    asyncio.create_task(rebuild_index_background())

    return FileUploadResponse(
        success=True,
        filename=filename,
        message="文件上传成功，索引正在后台重建",
        index_rebuilt=False,
        total_chunks=0
    )
```

- [ ] **Step 3: 修改前端上传完成等待时间**

在 `frontend/js/app.js` 中，修改 `handleFileUpload()` 的 `xhr.addEventListener('load', ...)` 中 setTimeout 延迟，从 1500ms 改为 2000ms：

```javascript
// 修改前
setTimeout(() => {
    fileEls.uploadProgress.style.display = 'none';
    loadFileList();
}, 1500);

// 修改后
setTimeout(() => {
    fileEls.uploadProgress.style.display = 'none';
    loadFileList();
}, 2000);
```

- [ ] **Step 4: 验证**

验证点：
- 上传一个文件后，立即返回"文件上传成功，索引正在后台重建"，不阻塞
- 等待 2-3 秒后刷新文件列表，确认文件已出现
- 检查后端日志，确认 `Background index rebuild done` 消息出现