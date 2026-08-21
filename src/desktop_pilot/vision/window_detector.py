"""视觉理解层：用 OpenCV + OCR 检测截图中的窗口和 UI 元素。

两层检测：
1. 窗口级：从全屏截图找出所有窗口矩形
2. 元素级：对每个窗口截图，找出所有可交互/可读元素并分类

不依赖 UIA，纯靠图像分析。
"""
from __future__ import annotations

import cv2
import numpy as np
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------- #
# 元素类型枚举
# --------------------------------------------------------------------------- #
class UIElementType(str, Enum):
    """可识别的 UI 元素类型。"""
    BUTTON = "button"
    TEXT_LABEL = "text_label"
    INPUT_FIELD = "input_field"
    LINK = "link"
    CHECKBOX = "checkbox"
    RADIO_BUTTON = "radio_button"
    DROPDOWN = "dropdown"
    SLIDER = "slider"
    TAB = "tab"
    MENU_ITEM = "menu_item"
    ICON = "icon"
    IMAGE = "image"
    PROGRESSBAR = "progressbar"
    CONTAINER = "container"
    SCROLLBAR = "scrollbar"
    TOGGLE = "toggle"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# 第一层：窗口级检测
# --------------------------------------------------------------------------- #
def detect_windows_from_screenshot(
    screenshot_rgb: np.ndarray,
    min_area: int = 10000,
    edge_threshold: int = 50,
) -> list[dict[str, Any]]:
    """从 RGB 截图中检测所有窗口矩形。

    Returns:
        [{"rect": (x,y,w,h), "area": int, "center": (cx,cy), "color": (r,g,b)}, ...]
    """
    gray = cv2.cvtColor(screenshot_rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, edge_threshold, edge_threshold * 3)
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=1)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    windows = []
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)]
    color_idx = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        windows.append({
            "rect": (x, y, w, h),
            "area": int(area),
            "center": (x + w // 2, y + h // 2),
            "color": colors[color_idx % len(colors)],
        })
        color_idx += 1

    windows.sort(key=lambda w: w["area"], reverse=True)
    return windows


# --------------------------------------------------------------------------- #
# 第二层：窗口内元素检测
# --------------------------------------------------------------------------- #
def _ocr_full_region(gray: np.ndarray, lang: str = "chi_sim+eng") -> list[dict[str, Any]]:
    """对一整块灰度图做 OCR，返回所有识别到的文字及其位置。

    特殊处理：中文相邻单字会被合并成短语（如 "选"+"择" → "选择"）。
    """
    try:
        import pytesseract
        from .ocr import _tesseract_cmd
        cmd = _tesseract_cmd()
        if cmd and getattr(pytesseract, "tesseract_cmd", "tesseract") == "tesseract":
            try:
                pytesseract.pytesseract.tesseract_cmd = cmd
            except AttributeError:
                pass
    except ImportError:
        return []

    try:
        data = pytesseract.image_to_data(
            gray, lang=lang, output_type=pytesseract.Output.DICT
        )
    except Exception:
        return []

    # 收集原始 OCR 词
    raw_words = []
    n = len(data.get("text", []))
    for i in range(n):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        try:
            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            conf = int(data["conf"][i])
            block_num = int(data["block_num"][i])
            line_num = int(data["line_num"][i])
        except (KeyError, ValueError, TypeError):
            continue
        if conf < 20:
            continue
        raw_words.append({
            "text": word,
            "rect": (x, y, w, h),
            "center": (x + w // 2, y + h // 2),
            "confidence": conf,
            "block_num": block_num,
            "line_num": line_num,
            "x": x,
            "y": y,
        })

    if not raw_words:
        return []

    # 合并相邻的中文单字：只合并都是中文单字的情况
    merged = []
    i = 0
    while i < len(raw_words):
        current = raw_words[i].copy()
        cx, cy, cw, ch = current["rect"]
        j = i + 1
        while j < len(raw_words):
            nxt = raw_words[j]
            # 只合并两个都是中文单字的情况
            if len(current["text"]) > 1 or len(nxt["text"]) > 1:
                break
            if not (all('一' <= c <= '鿿' or c in '，。、！？：；""''（）' for c in current["text"]) and
                    all('一' <= c <= '鿿' or c in '，。、！？：；""''（）' for c in nxt["text"])):
                break
            nx, ny, nw, nh = nxt["rect"]
            # 水平相邻
            if abs(ny - cy) < 15 and 0 <= nx - (cx + cw) < 20 and abs(nh - ch) < 15:
                current["text"] += nxt["text"]
                new_w = nx + nw - cx
                current["rect"] = (cx, cy, new_w, max(ch, nh))
                current["center"] = (cx + new_w // 2, cy + max(ch, nh) // 2)
                current["confidence"] = min(current["confidence"], nxt["confidence"])
                cw = new_w
                j += 1
            else:
                break
        current["width"] = current["rect"][2]
        merged.append(current)
        i = j

    return merged


def _match_text_to_elements(
    ocr_words: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    overlap_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """把 OCR 识别到的文字匹配到最近的元素框上。"""
    for word in ocr_words:
        wx, wy = word["center"]
        best_match = None
        best_dist = float("inf")
        for el in elements:
            ex, ey = el["center"]
            # 文字中心落在元素框内，或距离很近
            ex_, ey_, ew, eh = el["rect"]
            if ex_ <= wx <= ex_ + ew and ey_ <= wy <= ey_ + eh:
                best_match = el
                best_dist = 0
                break
            dist = ((wx - ex) ** 2 + (wy - ey) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_match = el

        # 文字中心在元素框内，或距离 < 100px，就匹配上
        if best_match and best_dist < 100:
            existing = best_match.get("text", "")
            if existing:
                best_match["text"] = existing + " " + word["text"]
            else:
                best_match["text"] = word["text"]

    return elements


def _classify_element(
    x: int, y: int, w: int, h: int,
    text: str,
    avg_color: tuple[int, int, int],
    aspect_ratio: float,
    rel_y: float,
) -> UIElementType:
    """根据形状、文字、颜色、位置推断元素类型。"""
    area = w * h
    r, g, b = avg_color

    # ---- 有文字的元素：优先按文字上下文分类 ----
    if text:
        text_lower = text.strip().lower()

        # 纯数字/符号 → text_label
        if all(c in "0123456789.:;|/\\()-+*%!?#@&" for c in text):
            return UIElementType.TEXT_LABEL

        # 链接特征：蓝色文字
        if b > 120 and r < 100 and g < 150:
            return UIElementType.LINK

        # 宽高比接近按钮（1.5~5）且面积中等
        if 1.2 < aspect_ratio < 6 and 500 < area < 80000:
            # 如果是纯中文短语（2-4字），很可能是按钮
            if all('一' <= c <= '鿿' for c in text) and 1 <= len(text) <= 6:
                return UIElementType.BUTTON
            # 英文按钮词
            if text_lower in ("ok", "cancel", "yes", "no", "submit", "send", "done", "save", "close"):
                return UIElementType.BUTTON

        # 有冒号的 → 通常是标签
        if ":" in text or "：" in text:
            return UIElementType.TEXT_LABEL

        # 窄高（下拉）→ dropdown
        if aspect_ratio < 0.7 and h > 15:
            return UIElementType.DROPDOWN

        # 默认：有文字的区域是 text_label
        return UIElementType.TEXT_LABEL

    # ---- 无文字的元素：按形状分类 ----

    # 正方形或接近正方形的小元素 → icon / checkbox / radio
    if 0.7 < aspect_ratio < 1.4:
        if area < 800:
            return UIElementType.ICON
        if area < 2500 and min(w, h) < 50:
            return UIElementType.CHECKBOX
        if area < 5000:
            return UIElementType.ICON
        # 更大的正方形 → 可能是按钮（无文字的按钮图标）
        if area < 15000:
            return UIElementType.BUTTON

    # 椭圆/极扁 → toggle / radio
    if aspect_ratio > 2 and area < 2000:
        return UIElementType.TOGGLE

    # 窄高（下拉箭头）
    if aspect_ratio < 0.5 and 20 < h < 80:
        return UIElementType.DROPDOWN

    # 窄长水平条 → slider / scrollbar
    if aspect_ratio > 5 and h < 20:
        return UIElementType.SLIDER
    if h < 10 and w > 80:
        return UIElementType.SCROLLBAR

    # 进度条
    if 3 < aspect_ratio < 12 and 15 < h < 40 and w > 100:
        return UIElementType.PROGRESSBAR

    # 图片：面积较大、宽高比接近1、无文字
    if area > 10000:
        return UIElementType.IMAGE

    # 大面积无文字 → 容器
    if area > 80000:
        return UIElementType.CONTAINER

    # 非常小的元素（无文字）→ icon
    if area < 800 and not text:
        return UIElementType.ICON

    # 窄高（< 0.5）且小 → icon
    if aspect_ratio < 0.5 and area < 3000 and not text:
        return UIElementType.ICON

    # 中等面积无文字 → image（很可能是图标或图片区域）
    if area > 8000 and 0.5 < aspect_ratio < 3:
        return UIElementType.IMAGE

    # 窄条无文字 → menu_item 或 tab
    if h < 60 and w > 80:
        return UIElementType.MENU_ITEM

    # 默认
    return UIElementType.UNKNOWN


def detect_elements_in_region(
    screenshot_rgb: np.ndarray,
    region: tuple[int, int, int, int] | None = None,
    min_element_area: int = 600,
    max_element_area: int = 500000,
    text_ocr: Any = None,
    lang: str = "chi_sim+eng",
) -> list[dict[str, Any]]:
    """在截图（或指定区域）中检测所有 UI 元素。

    Args:
        screenshot_rgb: HxWx3 RGB numpy 数组。
        region: (x, y, w, h) 只检测这个区域，None 表示全图。
        min_element_area: 过滤太小的元素。
        max_element_area: 过滤太大的（可能是背景）。
        text_ocr: 可选的 OCR 函数，签名为 (np.ndarray) -> str。
                  传入裁切后的灰度图，返回识别到的文字。

    Returns:
        元素列表，每个元素包含：
        {
            "type": "button"/"input_field"/...,
            "rect": (x, y, w, h),     # 在原始截图中的绝对坐标
            "center": (cx, cy),
            "text": "识别到的文字",
            "aspect_ratio": float,
            "area": int,
        }
    """
    # 裁切区域
    if region is not None:
        rx, ry, rw, rh = region
        # 边界保护
        rx = max(0, min(rx, screenshot_rgb.shape[1] - 1))
        ry = max(0, min(ry, screenshot_rgb.shape[0] - 1))
        rw = max(1, min(rw, screenshot_rgb.shape[1] - rx))
        rh = max(1, min(rh, screenshot_rgb.shape[0] - ry))
        crop = screenshot_rgb[ry:ry+rh, rx:rx+rw].copy()
        offset_x, offset_y = rx, ry
    else:
        crop = screenshot_rgb.copy()
        offset_x, offset_y = 0, 0

    # 转灰度做边缘和轮廓检测
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)

    # 自适应阈值（对亮度不均匀的界面更鲁棒）
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 11, 2)

    # 二值图的轮廓检测
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    elements = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_element_area or area > max_element_area:
            continue

        # 用矩形近似，过滤非矩形区域
        epsilon = 0.02 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)

        # 至少 4 个顶点（矩形）才考虑
        if len(approx) < 4:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        if w < 15 or h < 10:
            continue  # 太小，噪声

        # 裁切元素内部
        el_crop = crop[y:y+h, x:x+w]
        el_gray = gray[y:y+h, x:x+w]

        # OCR 识别文字：优先从全局 OCR 结果匹配，回退到逐元素 OCR
        text = ""
        if w > 20 and h > 10:
            if text_ocr is not None:
                try:
                    text = text_ocr(el_gray).strip()
                except Exception:
                    pass

        # 平均颜色（用于链接/按钮颜色判断）
        avg_color = tuple(int(c) for c in cv2.mean(el_crop)[:3])

        # 宽高比
        ar = w / h if h > 0 else 0

        # 相对位置（归一化到 0-1）
        rel_y = y / crop.shape[0] if crop.shape[0] > 0 else 0

        # 分类
        el_type = _classify_element(x, y, w, h, text, avg_color, ar, rel_y)

        elements.append({
            "type": el_type.value,
            "rect": (x + offset_x, y + offset_y, w, h),
            "center": (x + offset_x + w // 2, y + offset_y + h // 2),
            "text": text,
            "aspect_ratio": round(ar, 2),
            "area": int(area),
        })

    # 策略：OCR 结果 + 轮廓检测结果合并
    # 1. OCR 的每个词/句子本身就是一个元素（按钮上的文字、标签等）
    # 2. 轮廓检测补充无文字的元素（图标、图像、复选框等）
    ocr_words = _ocr_full_region(gray, lang=lang)

    # OCR 结果转成元素
    elements = []
    for word in ocr_words:
        if word["confidence"] < 30:
            continue
        wx, wy, ww, wh = word["rect"]
        # 平均颜色
        crop_el = crop[wy:wy+wh, wx:wx+ww] if wy+wh <= crop.shape[0] and wx+ww <= crop.shape[1] else None
        avg_color = tuple(int(c) for c in cv2.mean(crop_el)[:3]) if crop_el is not None and crop_el.size > 0 else (200, 200, 200)
        ar = ww / wh if wh > 0 else 0
        el_type = _classify_element(wx, wy, ww, wh, word["text"], avg_color, ar, wy / max(crop.shape[0], 1))
        elements.append({
            "type": el_type.value,
            "rect": (wx + offset_x, wy + offset_y, ww, wh),
            "center": (wx + offset_x + ww // 2, wy + offset_y + wh // 2),
            "text": word["text"],
            "aspect_ratio": round(ar, 2),
            "area": int(ww * wh),
            "confidence": word["confidence"],
        })

    # 2. 轮廓检测补充无文字元素（去掉和 OCR 文字重叠的区域）
    ocr_boxes = [(w["rect"][0], w["rect"][1], w["rect"][2], w["rect"][3]) for w in ocr_words]

    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 11, 2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_element_area or area > max_element_area:
            continue
        epsilon = 0.02 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        if len(approx) < 4:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        if w < 15 or h < 10:
            continue

        # 跳过和已有 OCR 文字重叠的区域
        overlap = False
        for ox, oy, ow, oh in ocr_boxes:
            if abs(x - ox) < 30 and abs(y - oy) < 30:
                overlap = True
                break
        if overlap:
            continue

        el_crop = crop[y:y+h, x:x+w]
        el_gray = gray[y:y+h, x:x+w]
        avg_color = tuple(int(c) for c in cv2.mean(el_crop)[:3]) if el_crop.size > 0 else (200, 200, 200)
        ar = w / h if h > 0 else 0
        el_type = _classify_element(x, y, w, h, "", avg_color, ar, y / max(crop.shape[0], 1))

        elements.append({
            "type": el_type.value,
            "rect": (x + offset_x, y + offset_y, w, h),
            "center": (x + offset_x + w // 2, y + offset_y + h // 2),
            "text": "",
            "aspect_ratio": round(ar, 2),
            "area": int(area),
            "confidence": 0,
        })

    return elements


# --------------------------------------------------------------------------- #
# 标注：在截图上画元素检测结果
# --------------------------------------------------------------------------- #
def annotate_windows_on_screenshot(
    screenshot_rgb: np.ndarray,
    windows: list[dict[str, Any]],
    thickness: int = 3,
) -> np.ndarray:
    """在截图上画出窗口矩形和标注。

    Args:
        screenshot_rgb: 原始 RGB 截图。
        windows: detect_windows_from_screenshot 的返回值。
        thickness: 边框粗细。

    Returns:
        标注后的 RGB 图像（numpy 数组）。
    """
    annotated = screenshot_rgb.copy()
    for i, w in enumerate(windows):
        x, y, w_, h = w["rect"]
        color = w["color"]
        cv2.rectangle(annotated, (x, y), (x + w_, y + h), color, thickness)
        # 左上角标序号
        cv2.putText(
            annotated,
            str(i),
            (x + 5, y + 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
        )
    return annotated


def annotate_elements_on_screenshot(
    screenshot_rgb: np.ndarray,
    elements: list[dict[str, Any]],
    thickness: int = 2,
) -> np.ndarray:
    """在截图上画出检测到的元素框和文字标注。

    不同类型的元素用不同颜色区分。
    """
    type_colors = {
        "button":      (0, 255, 0),    # 绿
        "text_label":  (200, 200, 200), # 灰
        "input_field": (0, 165, 255),   # 橙
        "link":        (255, 100, 100), # 蓝(偏粉)
        "checkbox":    (255, 255, 0),   # 黄
        "radio_button":(255, 255, 0),
        "dropdown":    (0, 200, 200),   # 青
        "slider":      (128, 128, 0),   # 橄榄
        "tab":         (200, 100, 255), # 紫
        "menu_item":   (0, 128, 128),   # 深青
        "icon":        (255, 180, 0),   # 橙黄
        "image":       (100, 200, 100), # 浅绿
        "progressbar": (50, 200, 50),   # 亮绿
        "container":   (150, 150, 150), # 灰
        "scrollbar":   (100, 100, 100), # 暗灰
        "toggle":      (0, 200, 100),   # 绿青
        "unknown":     (200, 200, 200), # 灰
    }

    annotated = screenshot_rgb.copy()
    for el in elements:
        x, y, w, h = el["rect"]
        color = type_colors.get(el["type"], (200, 200, 200))
        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, thickness)
        # 标注类型缩写
        label = el["type"][:3]
        cv2.putText(annotated, label, (x + 2, y - 4 if y > 15 else y + h + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    return annotated
