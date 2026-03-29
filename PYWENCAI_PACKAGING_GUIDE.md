# pywencai 打包问题解决方案

## 问题原因

打包后 `pywencai` 无法正常工作的原因：

1. **JS 文件未打包**：`pywencai` 依赖 `hexin-v.bundle.js` 文件生成 token
2. **Node.js 路径问题**：打包后无法找到 `node` 命令
3. **文件路径问题**：打包后文件在 `_MEIPASS` 临时目录

## 解决方案

### 1. 打包配置（已完成）

在 `pyapp/spec/getSpec.py` 中添加 pywencai 目录到打包：

```python
import pywencai
pywencai_path = os.path.dirname(pywencai.__file__)
addModules = "..., ('{pywencai_path}', 'pywencai')"
```

### 2. 补丁模块（已完成）

创建了 `pyapp/quant/pywencai_patch.py`，修复：
- Node.js 路径查找
- JS 文件路径查找（支持 _MEIPASS）
- 错误处理和超时控制

### 3. 应用补丁（已完成）

在 `main.py` 启动时自动应用补丁。

## 打包步骤

1. 生成 spec 文件：
```bash
cd pyapp/spec
python getSpec.py --mac  # macOS
python getSpec.py        # Windows
```

2. 检查生成的 spec 文件，确认 pywencai 已包含在 datas 中

3. 执行打包：
```bash
pyinstaller macos.spec  # macOS
```

## 测试步骤

### 开发环境测试

```bash
python test_pywencai_debug.py
```

### 打包后测试

1. 运行打包后的应用
2. 尝试执行问财查询
3. 查看错误信息

## 常见问题

### 问题1：找不到 Node.js

**错误信息**：`未找到 Node.js`

**解决方案**：
- 确保系统已安装 Node.js
- 检查 Node.js 是否在 PATH 中
- 或者在常见路径：
  - macOS: `/opt/homebrew/bin/node`, `/usr/local/bin/node`
  - Windows: `C:\Program Files\nodejs\node.exe`

### 问题2：找不到 JS 文件

**错误信息**：`未找到 hexin-v.bundle.js 文件`

**解决方案**：
- 检查 spec 文件中是否包含 pywencai 目录
- 重新生成 spec 文件并打包
- 检查打包后的应用目录，确认 pywencai 文件夹存在

### 问题3：Node.js 执行失败

**错误信息**：`Node.js 执行失败` 或 `Node.js 执行超时`

**解决方案**：
- 检查 Node.js 版本（建议 v16+）
- 检查 JS 文件是否完整（约 5MB）
- 检查应用是否有执行外部命令的权限

## 调试信息

运行 `test_pywencai_debug.py` 会输出：
- Python 环境信息
- pywencai 模块路径和文件
- Node.js 路径和版本
- 实际查询测试结果

## 验证清单

打包前：
- [ ] pywencai 已安装
- [ ] Node.js 已安装并可用
- [ ] 开发环境测试通过

打包配置：
- [ ] getSpec.py 包含 pywencai 路径
- [ ] spec 文件生成成功
- [ ] spec 文件中 datas 包含 pywencai

打包后：
- [ ] 应用可以启动
- [ ] 可以找到 Node.js
- [ ] 可以找到 JS 文件
- [ ] 查询功能正常
