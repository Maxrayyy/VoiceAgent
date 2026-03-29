"""PDF 文本抽取脚本 - 使用 PaddleX Layout + PaddleOCR 提取 PDF 正文"""
import os
import sys
import argparse
import cv2
from pdf2image import convert_from_path
from paddlex import create_model
from paddleocr import PaddleOCR

os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# =========================
# 默认配置
# =========================
DEFAULT_PDF_PATH = "/home/zhidong_huang/knowledges/data.pdf"
DEFAULT_OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/txt/full_text.txt")
PAGE_IMAGE_DIR = os.path.join(PROJECT_ROOT, "data/figures/pages")

LAYOUT_MODEL_DIR = "/home/zhidong_huang/PDF_models/PP-DocLayout_plus-L_infer"
OCR_DET_MODEL_DIR = "/home/zhidong_huang/PDF_models/PP-OCRv5_server_det_infer"
OCR_REC_MODEL_DIR = "/home/zhidong_huang/PDF_models/PP-OCRv5_server_rec_infer"


def init_models():
    layout_model = create_model(
        model_name="PP-DocLayout_plus-L",
        model_dir=LAYOUT_MODEL_DIR,
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
        text_detection_model_dir=OCR_DET_MODEL_DIR,
        text_recognition_model_dir=OCR_REC_MODEL_DIR,
    )
    return layout_model, ocr_model


def pdf_to_images(pdf_path, output_dir, first_page, last_page, dpi=300):
    os.makedirs(output_dir, exist_ok=True)
    images = convert_from_path(
        pdf_path, dpi=dpi, first_page=first_page, last_page=last_page
    )
    image_infos = []
    for i, img in enumerate(images):
        page_num = first_page + i
        path = os.path.join(output_dir, f"page_{page_num}.png")
        img.save(path, "PNG")
        image_infos.append((path, page_num))
    return image_infos


def sort_text_blocks(blocks):
    return sorted(
        blocks,
        key=lambda b: (
            (b["bbox"][1] + b["bbox"][3]) / 2,
            b["bbox"][0]
        )
    )


def process_page(layout_model, ocr_model, image_path, page_num, output_text_path):
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
        if box["label"] in ("text", "paragraph_title"):
            text_blocks.append({"bbox": [x1, y1, x2, y2]})

    page_lines = []
    text_blocks = sort_text_blocks(text_blocks)

    for block in text_blocks:
        x1, y1, x2, y2 = block["bbox"]
        crop = img[y1:y2, x1:x2]
        h, w = crop.shape[:2]

        MAX_WIDTH = 2000
        if w > MAX_WIDTH:
            scale = MAX_WIDTH / w
            crop = cv2.resize(crop, (int(w * scale), int(h * scale)))

        ocr_res = ocr_model.predict(crop)
        if ocr_res and "rec_texts" in ocr_res[0]:
            line = "".join(t.strip() for t in ocr_res[0]["rec_texts"])
            if line:
                page_lines.append(line)
            page_lines.append("")

    with open(output_text_path, "a", encoding="utf-8") as f:
        f.write(f"\n===== 第 {page_num} 页 =====\n")
        f.write("\n".join(page_lines))
        f.write("\n")

    return page_lines


def main():
    parser = argparse.ArgumentParser(description="PDF 文本抽取（Layout + OCR）")
    parser.add_argument("--pdf", default=DEFAULT_PDF_PATH, help="PDF 文件路径")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH, help="输出 txt 路径")
    parser.add_argument("--first-page", type=int, default=9, help="起始页码")
    parser.add_argument("--last-page", type=int, default=69, help="结束页码")
    parser.add_argument("--dpi", type=int, default=300, help="渲染 DPI")
    parser.add_argument("--append", action="store_true", help="追加模式，不删除已有文件")
    args = parser.parse_args()

    os.makedirs(PAGE_IMAGE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    # 清空旧文件（除非追加模式）
    if not args.append and os.path.exists(args.output):
        os.remove(args.output)

    print("初始化模型...")
    layout_model, ocr_model = init_models()

    print(f"PDF: {args.pdf}")
    print(f"页码范围: {args.first_page} - {args.last_page}")

    image_infos = pdf_to_images(
        args.pdf, PAGE_IMAGE_DIR, args.first_page, args.last_page, args.dpi
    )

    for image_path, page_num in image_infos:
        print(f"处理第 {page_num} 页")
        try:
            process_page(layout_model, ocr_model, image_path, page_num, args.output)
        except Exception as e:
            print(f"第 {page_num} 页失败：{e}")

    print(f"\n文本抽取完成：{args.output}")


if __name__ == "__main__":
    main()
