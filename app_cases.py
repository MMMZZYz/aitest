import io
import os
import tempfile
import traceback

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from generate_cases_mvp import generate_cases_from_xmind_bytes
from generate_md_v2 import (
    IMAGE_EXTENSIONS,
    PDF_EXTENSION,
    llm_generate_struct,
    llm_generate_struct_from_image,
    read_pdf_text,
    save_to_markdown,
)

app = FastAPI(title="用例生成服务（需求/XMind -> 测试点/Excel）")

# 模板路径：可以通过环境变量覆盖
TEMPLATE_XLSX = os.getenv("CASES_TEMPLATE_PATH", "用例模板.xlsx")


def _is_image_filename(filename: str) -> bool:
    if not filename:
        return False
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS


def _is_pdf_filename(filename: str) -> bool:
    if not filename:
        return False
    return os.path.splitext(filename)[1].lower() == PDF_EXTENSION


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
    <html>
      <head>
        <meta charset="utf-8" />
        <title>用例生成服务</title>
      </head>
      <body>
        <h3>需求端：上传需求文档、PDF 或图片，生成测试点 MD</h3>
        <form action="/req_to_testpoints" method="post" enctype="multipart/form-data">
          <p>
            <input type="file" name="req_file" accept=".md,.txt,.pdf,.png,.jpg,.jpeg,.webp" required />
            <span style="color:#666">支持 .md/.txt、.pdf 或 .png/.jpg/.jpeg/.webp 需求截图</span>
          </p>
          <p>
            <button type="submit">生成测试点 MD</button>
          </p>
        </form>
        <hr />
        <h3>上传测试点 XMind，生成测试用例 Excel</h3>
        <form action="/generate_cases" method="post" enctype="multipart/form-data">
          <p>
            <input type="file" name="xmind_file" accept=".xmind" required />
          </p>
          <p>
            <button type="submit">生成用例 Excel</button>
          </p>
        </form>
      </body>
    </html>
    """


@app.post("/req_to_testpoints")
async def req_to_testpoints(req_file: UploadFile = File(...)):
    """
    上传需求文件（.md/.txt 文本、.pdf 或 .png/.jpg/.jpeg/.webp 图片），
    解析后使用 LLM 生成测试点 MD 并返回下载。
    """
    content = await req_file.read()
    filename = req_file.filename or "req"
    print(f"[WEB] 需求上传: filename={filename!r}, size={len(content) / 1024:.1f} KB")

    try:
        if _is_image_filename(filename):
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                result = llm_generate_struct_from_image(tmp_path)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        elif _is_pdf_filename(filename):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                req_text = read_pdf_text(tmp_path)
                result = llm_generate_struct(req_text)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        else:
            req_text = content.decode("utf-8").strip()
            if not req_text:
                raise HTTPException(status_code=400, detail="需求文件内容为空")
            result = llm_generate_struct(req_text)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as tmp:
            save_to_markdown(result, tmp.name, file_title=filename)
            tmp_path = tmp.name
        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                md_content = f.read()
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        return StreamingResponse(
            io.BytesIO(md_content.encode("utf-8")),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="test_points.md"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[WEB] 需求分析失败: {repr(e)}\n{tb}")
        raise HTTPException(
            status_code=500,
            detail=f"分析失败: {type(e).__name__}: {e}",
        )


@app.post("/generate_cases")
async def generate_cases(xmind_file: UploadFile = File(...)):
    """
    上传一个 XMind，返回生成好的 Excel 文件下载。
    """
    content = await xmind_file.read()
    size_kb = len(content) / 1024 if content else 0
    print(f"[WEB] 收到上传: filename={xmind_file.filename!r}, size={size_kb:.1f} KB")

    try:
        excel_bytes = generate_cases_from_xmind_bytes(content, TEMPLATE_XLSX)
    except SystemExit as e:
        msg = str(e) or "生成失败（配置或输入问题）"
        print(f"[WEB] 生成失败(SystemExit): {msg}")
        raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[WEB] 生成失败(Exception): {repr(e)}\n{tb}")
        raise HTTPException(
            status_code=500,
            detail=f"服务器错误: {type(e).__name__}: {e}",
        )

    print(f"[WEB] 已生成 Excel，大小约 {len(excel_bytes) / 1024:.1f} KB，准备返回给客户端")

    filename = "输出用例.xlsx"
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )

