# Task 3 Code Review 修复报告

## 修复内容

### 1. Critical: sendQuestion 点击事件传递 MouseEvent 作为参数
- **文件**: `frontend/js/app.js` (第535行)
- **问题**: `els.btnSend.addEventListener('click', sendQuestion)` 将 MouseEvent 对象作为 `question` 参数传入
- **修复**: 改为 `els.btnSend.addEventListener('click', () => sendQuestion())`，确保点击时调用无参数版本，从输入框读取问题文本

### 2. Important: 来源默认可见
- **文件**: `frontend/js/app.js`
- **问题**: 历史消息渲染时 (`renderMessageElement`) 仅在操作按钮中创建来源折叠按钮，来源面板默认不显示
- **修复**: 
  - 在 `renderMessageElement` 中调用 `addActionButtons` 后，若 sources 有数据则调用 `appendSourcesToMessage` 渲染来源面板（默认可见）
  - 简化来源折叠按钮点击逻辑，仅切换现有 `.msg-sources` 的 display 状态，不再创建新面板

### 3. Important: 删除旧 CSS 类名
- **文件**: `frontend/css/style.css` (第416-451行)
- **问题**: 旧的 `.sources-list`、`.sources-title`、`.source-item`、`.source-file`、`.source-score` 类名已不再使用
- **修复**: 删除所有未使用的旧 CSS 规则

### 4. Minor: addActionButtons 缺少重复保护
- **文件**: `frontend/js/app.js` (第372行)
- **问题**: `addActionButtons` 在流式渲染完成后的 `done` 事件中可能被重复调用，导致重复添加操作按钮
- **修复**: 在函数开头添加 `if (msgDiv.querySelector('.msg-actions')) return;` 保护

## 测试结果

- **服务启动**: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` 启动成功
- **前端加载**: `curl http://localhost:8000/` 返回 `HTTP 200, Content-Type: text/html; charset=utf-8, Size: 15957 bytes`
- **后端日志**: 所有服务初始化成功（Redis、Faiss 索引 545 向量、SearchStore）

## 提交信息

- **Commit SHA**: `15d6612`
- **提交信息**: `fix: 修复 Task 3 code review 发现的四个问题`
- **变更文件**: 2 个文件，+6 行 / -63 行