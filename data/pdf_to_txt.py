import os
import cv2
import pprint
from pdf2image import convert_from_path
from paddlex import create_model
from paddleocr import PaddleOCR

os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"

# =========================
# PDF 配置
# =========================
PDF_PATH = "/home/zhidong_huang/knowledges/data.pdf"
PAGE_IMAGE_DIR = "data/figures/pages"
# FIGURE_DIR = "data/figures/extracted_figures"
# FORMULA_FIGURE_DIR = "data/figures/formula_figures"
OUTPUT_TEXT_PATH = "data/txt/full_text.txt"
FIRST_PAGE = 34
LAST_PAGE = 34
DPI = 300

os.makedirs(PAGE_IMAGE_DIR, exist_ok=True)
# os.makedirs(FORMULA_FIGURE_DIR, exist_ok=True)
# os.makedirs(FIGURE_DIR, exist_ok=True)
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
    #use_gpu=False,
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
def sort_text_blocks(blocks, y_threshold=25):
    return sorted(
        blocks,
        key=lambda b: (
            # round(b["bbox"][1] / y_threshold),
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

    print(f"\n检测到 boxes 数量: {len(boxes)}\n")

    print("==== 原始 box 内容 ====")
    for i, box in enumerate(boxes):
        print(f"\n--- box {i} ---")
        pprint.pprint(box)

    text_blocks = []

    for box in boxes:
        x1, y1, x2, y2 = map(int, box["coordinate"])
        label = box["label"]

        if label in ("text", "paragraph_title"):
            text_blocks.append({"bbox": [x1, y1, x2, y2]})

    # ---------- 正文 OCR ----------
    page_lines = []
    text_blocks = sort_text_blocks(text_blocks)

    # print(">>> 开始正文 OCR")

    for idx, block in enumerate(text_blocks):
        x1, y1, x2, y2 = block["bbox"]
        crop = img[y1:y2, x1:x2]
        # [表情] ===== 尺寸保护（关键）=====
        h, w = crop.shape[:2]

        MAX_WIDTH = 2000

        if w > MAX_WIDTH:
            scale = MAX_WIDTH / w
            crop = cv2.resize(
                crop,
                (int(w * scale), int(h * scale))
            )
            print(f"[表情] resize block {idx}: {w} -> {MAX_WIDTH}")
        ocr_res = ocr_model.predict(crop)
        if ocr_res and "rec_texts" in ocr_res[0]:
            # page_lines.extend(
            #     [t.strip() for t in ocr_res[0]["rec_texts"] if t.strip()]
            # )
            line = "".join(t.strip() for t in ocr_res[0]["rec_texts"])
            if line:
                page_lines.append(line)

            page_lines.append("")

    # print(">>> 即将写入 txt")
    # ---------- [表情] 单页立即写入 txt ----------
    with open(output_text_path, "a", encoding="utf-8") as f:
        f.write(f"\n===== 第 {page_num} 页 =====\n")
        f.write("\n".join(page_lines))
        f.write("\n")

    return page_lines


# =========================
# 多页处理（抽出来）
# =========================
def process_pages(image_infos, output_text_path):
    for image_path, page_num in image_infos:
        print(f"[表情] 处理第 {page_num} 页")

        try:
            process_page(image_path, page_num, output_text_path)
        except Exception as e:
            print(f"[表情] 第 {page_num} 页失败：{e}")

# =========================
# 主流程（只调度）
# =========================
def main():
    image_infos = pdf_to_images(
        PDF_PATH,
        PAGE_IMAGE_DIR,
        FIRST_PAGE,
        LAST_PAGE,
        DPI
    )

    process_pages(image_infos, OUTPUT_TEXT_PATH)

    print("\n[表情] 抽取完成")
    print("[表情] 文本目录：", OUTPUT_TEXT_PATH)


if __name__ == "__main__":
    main()

# import os
# import cv2
# import pprint
# from paddlex import create_model
# from paddleocr import PaddleOCR
#
# # =========================
# # 初始化 Layout 模型
# # =========================
# layout_model = create_model(
#     model_name="PP-DocLayout_plus-L",
#     model_dir=r"D:\paddle_models\official_models\PP-DocLayout_plus-L_infer",
#     device="cpu"
# )
#
# image_path = "page_10.png"
#
# # =========================
# # Layout 推理
# # =========================
# layout_result = list(layout_model.predict(image_path))
# if not layout_result:
#     raise RuntimeError("layout_model.predict() 返回为空")
#
# result0 = layout_result[0]
#
# # 兼容 PaddleX 不同输出结构
# if "pred" in result0 and "boxes" in result0["pred"]:
#     boxes = result0["pred"]["boxes"]
# elif "boxes" in result0:
#     boxes = result0["boxes"]
# else:
#     raise RuntimeError(f"无法解析 layout 输出结构: {result0.keys()}")
#
# print(f"\n检测到 boxes 数量: {len(boxes)}\n")
#
# print("==== 原始 box 内容 ====")
# for i, box in enumerate(boxes):
#     print(f"\n--- box {i} ---")
#     pprint.pprint(box)
#
# # =========================
# # 初始化 OCR 模型（离线）
# # =========================
# ocr_model = PaddleOCR(
#     enable_mkldnn=False,
#     cpu_threads=2,
#     use_doc_orientation_classify=False,
#     use_doc_unwarping=False,
#     use_textline_orientation=False,
#     text_recognition_model_name="PP-OCRv5_server_rec",
#     text_detection_model_name="PP-OCRv5_server_det",
#     text_detection_model_dir=r"D:\paddle_models\official_models\PP-OCRv5_server_det_infer",
#     text_recognition_model_dir=r"D:\paddle_models\official_models\PP-OCRv5_server_rec_infer",
# )
#
# # =========================
# # 读取原图
# # =========================
# img = cv2.imread(image_path)
# if img is None:
#     raise RuntimeError(f"无法读取图片: {image_path}")
#
# h, w = img.shape[:2]
#
# # =========================
# # 输出目录
# # =========================
# image_dir = "output_images"
# os.makedirs(image_dir, exist_ok=True)
#
# # =========================
# # 按类型分离 blocks
# # =========================
# figure_title_blocks = []
# image_blocks = []
# text_blocks = []
#
# for idx, box in enumerate(boxes):
#     x1, y1, x2, y2 = map(int, box["coordinate"])
#     label = box["label"]
#
#     if label == "figure_title":
#         figure_title_blocks.append({
#             "id": idx,
#             "bbox": [x1, y1, x2, y2]
#         })
#     elif label == "image":
#         image_blocks.append({
#             "id": idx,
#             "bbox": [x1, y1, x2, y2]
#         })
#     elif label == "text":
#         text_blocks.append({
#             "id": idx,
#             "bbox": [x1, y1, x2, y2]
#         })
#
# # =========================
# # text block 排序（阅读顺序）
# # =========================
# def sort_text_blocks(blocks, y_threshold=25):
#     return sorted(
#         blocks,
#         key=lambda b: (
#             round(b["bbox"][1] / y_threshold),  # y1 分桶
#             b["bbox"][0]                         # x1
#         )
#     )
#
# text_blocks = sort_text_blocks(text_blocks)
#
# # =========================
# # 提取正文文本
# # =========================
# full_text_lines = []
#
# for t_block in text_blocks:
#     x1, y1, x2, y2 = t_block["bbox"]
#
#     if x2 <= x1 or y2 <= y1:
#         continue
#
#     crop_text = img[y1:y2, x1:x2]
#     ocr_result = ocr_model.predict(crop_text)
#
#     if ocr_result and "rec_texts" in ocr_result[0]:
#         for line in ocr_result[0]["rec_texts"]:
#             line = line.strip()
#             if line:
#                 full_text_lines.append(line)
#
# # =========================
# # 保存正文文本
# # =========================
# text_save_path = "full_text.txt"
# with open(text_save_path, "w", encoding="utf-8") as f:
#     f.write("\n".join(full_text_lines))
#
# print(f"\n[表情] 正文文本已保存到: {text_save_path}")
#
# # =========================
# # figure_title → image 匹配并保存图片
# # =========================
# for f_block in figure_title_blocks:
#     fx1, fy1, fx2, fy2 = f_block["bbox"]
#
#     crop_title = img[fy1:fy2, fx1:fx2]
#     ocr_result = ocr_model.predict(crop_title)
#
#     figure_text = f"figure_{f_block['id']}"
#     if ocr_result and "rec_texts" in ocr_result[0]:
#         candidate = "".join(ocr_result[0]["rec_texts"]).strip()
#         if candidate:
#             figure_text = candidate[:50]
#
#     print(f"\n=== 图注 OCR 结果 ===")
#     print("识别文字:", figure_text)
#
#     min_dist = float("inf")
#     matched_image = None
#
#     for i_block in image_blocks:
#         ix1, iy1, ix2, iy2 = i_block["bbox"]
#         dist = fy1 - iy2
#         if dist >= 0 and dist < min_dist:
#             min_dist = dist
#             matched_image = i_block
#
#     if matched_image:
#         ix1, iy1, ix2, iy2 = matched_image["bbox"]
#         crop_img = img[iy1:iy2, ix1:ix2]
#         save_path = os.path.join(image_dir, f"{figure_text}.png")
#
#         success, encoded_img = cv2.imencode(".png", crop_img)
#         if success:
#             with open(save_path, "wb") as f:
#                 f.write(encoded_img.tobytes())
#             print(f"[表情] 保存成功: {save_path}")
#         else:
#             print(f"[表情] 图像编码失败: {save_path}")
#     else:
#         print(f"[表情] 标题 '{figure_text}' 未匹配到图片")
