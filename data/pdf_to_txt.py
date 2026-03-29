import os
import sys
import cv2
from pdf2image import convert_from_path
from paddlex import create_model
from paddleocr import PaddleOCR

os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"

# =========================
# 路径基准（项目根目录）
# =========================
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# =========================
# PDF 配置
# =========================
PDF_PATH = "/home/zhidong_huang/knowledges/data.pdf"
PAGE_IMAGE_DIR = os.path.join(PROJECT_ROOT, "data/figures/pages")
OUTPUT_TEXT_PATH = os.path.join(PROJECT_ROOT, "data/txt/full_text.txt")
FIRST_PAGE = 9
LAST_PAGE = 69
DPI = 300

os.makedirs(PAGE_IMAGE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(OUTPUT_TEXT_PATH), exist_ok=True)

# =========================
# 模型初始化（只加载一次）
# =========================
layout_model = create_model(
    model_name="PP-DocLayout_plus-L",
    model_dir="/home/zhidong_huang/PDF_models/PP-DocLayout_plus-L_infer",
    device="cpu"
)

ocr_model = PaddleOCR(
    enable_mkldnn=False,
    cpu_threads=2,
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",
    text_detection_model_dir="/home/zhidong_huang/PDF_models/PP-OCRv5_server_det_infer",
    text_recognition_model_dir="/home/zhidong_huang/PDF_models/PP-OCRv5_server_rec_infer",
)

# =========================
# PDF → 图片（多页）
# =========================
def pdf_to_images(pdf_path, output_dir, first_page, last_page, dpi=300):
    os.makedirs(output_dir, exist_ok=True)

    images = convert_from_path(
        pdf_path,
        dpi=dpi,
        first_page=first_page,
        last_page=last_page
    )

    image_infos = []
    for i, img in enumerate(images):
        page_num = first_page + i
        path = os.path.join(output_dir, f"page_{page_num}.png")
        img.save(path, "PNG")
        image_infos.append((path, page_num))

    return image_infos

# =========================
# 工具：text block 排序
# =========================
def sort_text_blocks(blocks):
    return sorted(
        blocks,
        key=lambda b: (
            (b["bbox"][1] + b["bbox"][3]) / 2,  # y_center
            b["bbox"][0]
        )
    )

# =========================
# 单页处理（结构化抽取）
# =========================
def process_page(image_path, page_num, output_text_path):
    img = cv2.imread(image_path)
    if img is None:
        return []

    layout_result = list(layout_model.predict(image_path))
    if not layout_result:
        return []

    result0 = layout_result[0]
    if "pred" in result0 and "boxes" in result0["pred"]:
        boxes = result0["pred"]["boxes"]
    else:
        boxes = result0["boxes"]

    text_blocks = []

    for box in boxes:
        x1, y1, x2, y2 = map(int, box["coordinate"])
        label = box["label"]

        if label in ("text", "paragraph_title"):
            text_blocks.append({"bbox": [x1, y1, x2, y2]})

    # ---------- 正文 OCR ----------
    page_lines = []
    text_blocks = sort_text_blocks(text_blocks)

    for idx, block in enumerate(text_blocks):
        x1, y1, x2, y2 = block["bbox"]
        crop = img[y1:y2, x1:x2]
        h, w = crop.shape[:2]

        MAX_WIDTH = 2000

        if w > MAX_WIDTH:
            scale = MAX_WIDTH / w
            crop = cv2.resize(
                crop,
                (int(w * scale), int(h * scale))
            )
        ocr_res = ocr_model.predict(crop)
        if ocr_res and "rec_texts" in ocr_res[0]:
            line = "".join(t.strip() for t in ocr_res[0]["rec_texts"])
            if line:
                page_lines.append(line)

            page_lines.append("")

    # ---------- 单页立即写入 txt ----------
    with open(output_text_path, "a", encoding="utf-8") as f:
        f.write(f"\n===== 第 {page_num} 页 =====\n")
        f.write("\n".join(page_lines))
        f.write("\n")

    return page_lines


# =========================
# 多页处理
# =========================
def process_pages(image_infos, output_text_path):
    for image_path, page_num in image_infos:
        print(f"处理第 {page_num} 页")

        try:
            process_page(image_path, page_num, output_text_path)
        except Exception as e:
            print(f"第 {page_num} 页失败：{e}")

# =========================
# RAG 索引构建
# =========================
def build_rag_index(text_path):
    sys.path.insert(0, PROJECT_ROOT)
    from src.rag.retriever import DocumentStore

    store = DocumentStore()
    store.load()

    count = store.add_documents(text_path)
    store.save()
    print(f"RAG 索引构建完成：导入 {count} 个文本块，共 {store.count} 个文档")

# =========================
# 主流程
# =========================
def main():
    # 清空旧的输出文件，避免重复追加
    if os.path.exists(OUTPUT_TEXT_PATH):
        os.remove(OUTPUT_TEXT_PATH)

    image_infos = pdf_to_images(
        PDF_PATH,
        PAGE_IMAGE_DIR,
        FIRST_PAGE,
        LAST_PAGE,
        DPI
    )

    process_pages(image_infos, OUTPUT_TEXT_PATH)

    print(f"\n文本抽取完成：{OUTPUT_TEXT_PATH}")

    # 构建 RAG 索引
    build_rag_index(OUTPUT_TEXT_PATH)


if __name__ == "__main__":
    main()
