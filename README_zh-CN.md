# Epub & PDF 转 Markdown 转换器

本项目提供了一个强大的解决方案，用于将 EPUB 和 PDF 文件转换为结构化的 Markdown 文档。它的设计初衷是尽可能保留原始文档的结构，根据目录（TOC）或标题将内容拆分到独立的文件中。

[English README](README.md)

## 主要功能

*   **EPUB 转换**：
    *   **基于目录拆分**：智能解析 EPUB 的目录（NCX 或 Nav），创建对应的文件夹结构。
    *   **保留层级**：完美保留书籍的层级关系（例如：`第一部/第一章.md`）。
    *   **智能图片管理**：将所有图片提取到统一的 `media/` 文件夹，并自动修复 Markdown 文件中的相对链接，确保图片正常显示。
    *   **锚点精准切割**：使用 Pandoc 转换全文，然后根据内部锚点进行精准切割，避免章节间内容重复。
    *   **降级机制**：如果未找到目录，会自动降级使用 EPUB 的线性“Spine”结构进行拆分。

*   **PDF 转换**：
    *   使用 `marker`（一个强大的 PDF 转 Markdown 引擎）进行高质量转换。
    *   **标题拆分**：自动根据一级标题（`#`）和二级标题（`##`）将生成的长 Markdown 文件拆分为多个小文件。

*   **macOS 集成**：
    *   包含一个脚本，可直接用于 macOS Automator，实现“右键 -> 转换为 Markdown”的快捷功能。

## 依赖要求

*   **Python 3.x**
*   **Pandoc**：EPUB 转换必须。
    *   通过 Homebrew 安装：`brew install pandoc`
*   **Marker**（可选，仅 PDF 转换需要）：
    *   请参阅 [Marker 安装说明](https://github.com/VikParuchuri/marker)。

## 安装

1.  克隆本仓库：
    ```bash
    git clone https://github.com/wanghanlele12345/epub-to-markdown.git
    cd epub-to-markdown
    ```

2.  确保您已安装所需的依赖（Pandoc, Python）。

## 使用方法

### 命令行

您可以直接对一个或多个文件运行转换脚本：

```bash
./convert.sh book.epub document.pdf
```

*   **EPUB 文件**：会创建一个名为 `book_toc_split/` 的文件夹，其中包含结构化的 Markdown 内容。
*   **PDF 文件**：会创建一个名为 `document_md/` 的文件夹，包含原始输出以及一个 `_split/` 子文件夹，里面是拆分后的内容。

### macOS 右键菜单（快速操作）

要在 macOS 上添加右键快捷操作：

1.  打开 **Automator**（自动操作）。
2.  新建一个 **Quick Action**（快速操作）。
3.  将“工作流程接收当前”设置为 **访达（Finder）** 中的 **文件或文件夹**。
4.  添加 **Run Shell Script**（运行 Shell 脚本）操作。
5.  将“传递输入”设置为 **作为自变量**（as arguments）。
6.  粘贴 `convert.sh` 中的逻辑，或者直接调用该脚本：
    ```bash
    /path/to/epub-to-markdown/convert.sh "$@"
    ```
    *(请将 `/path/to/` 替换为您实际存放该项目的路径)*
7.  保存为 "Convert to Markdown"。

现在，您可以右键点击任何 EPUB 或 PDF 文件，选择 **快速操作 > Convert to Markdown** 即可开始转换。

## 项目结构

*   `epub_to_md.py`: 核心 Python 脚本，负责 EPUB 解析、Pandoc 转换、内容切割和媒体资源管理。
*   `split_markdown.py`: 辅助 Python 脚本，用于根据标题拆分扁平的 Markdown 文件（主要用于 PDF 输出）。
*   `convert.sh`: 主 Shell 脚本，作为入口点，负责检测文件类型并调用相应的 Python 转换器。

## 许可证

MIT License. 欢迎使用和修改。
