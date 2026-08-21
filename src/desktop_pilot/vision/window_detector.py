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
def _classify_element(
    x: int, y: int, w: int, h: int,
    text: str,
    avg_color: tuple[int, int, int],
    aspect_ratio: float,
    rel_y: float,
) -> UIElementType:
    """根据形状、文字、颜色、位置推断元素类型。"""
    area = w * h

    # 正方形或接近正方形的小元素 → 可能是 checkbox / radio / icon
    if 0.8 < aspect_ratio < 1.2 and area < 2500:
        # checkbox/radio 通常很小且居中偏左
        if area > 200:
            return UIElementType.CHECKBOX
        return UIElementType.ICON

    # 椭圆/圆形 → toggle 或 radio
    if aspect_ratio > 1.8 and area < 1500:
        return UIElementType.TOGGLE

    # 下拉箭头区域（宽 < 30, 高 > 20）→ dropdown
    if w < 30 and 20 < h < 60:
        return UIElementType.DROPDOWN

    # 窄长水平条 → slider 或 scrollbar
    if aspect_ratio > 6 and h < 15:
        return UIElementType.SLIDER
    if h < 12 and w > 50:
        return UIElementType.SCROLLBAR

    # 进度条（宽高比 4:1~10:1, 中等面积）
    if 3 < aspect_ratio < 12 and 20 < h < 40 and w > 100:
        return UIElementType.PROGRESSBAR

    # 按钮特征：矩形 + 有文字 + 面积中等 + 在合理位置
    if text and 800 < area < 100000 and 1.2 < aspect_ratio < 6:
        # 如果颜色偏灰/白/蓝 → 按钮
        r, g, b = avg_color
        if (b > 100 or r > 100) and 30 < h < 120:
            return UIElementType.BUTTON

    # 链接特征：蓝色文字（文字检测由调用方完成，这里主要看颜色）
    r, g, b = avg_color
    if b > 150 and g < 100 and r < 100 and text:
        return UIElementType.LINK

    # 文字标签：有文字但面积小、没有明显边框
    if text and area < 5000:
        return UIElementType.TEXT_LABEL

    # 下拉框/输入框：矩形 + 边框 + 中等面积
    if 1.5 < aspect_ratio < 5 and 20 < h < 60 and area > 1000:
        # 检查是否有明显边框（四边灰度值差异）
        return UIElementType.INPUT_FIELD

    # Tab：窄条状 + 文字
    if text and 30 < h < 80 and aspect_ratio > 1.5 and aspect_ratio < 4:
        return UIElementType.TAB

    # 菜单项：宽条 + 窄高
    if text and h < 50 and w > 100:
        return UIElementType.MENU_ITEM

    # 图片：面积较大、宽高比接近1、没有文字
    if not text and area > 10000:
        return UIElementType.IMAGE

    # 大矩形无文字 → 容器
    if not text and area > 50000:
        return UIElementType.CONTAINER

    return UIElementType.UNKNOWN


def detect_elements_in_region(
    screenshot_rgb: np.ndarray,
    region: tuple[int, int, int, int] | None = None,
    min_element_area: int = 200,
    max_element_area: int = 500000,
    text_ocr: Any = None,
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

        # OCR 识别文字
        text = ""
        if text_ocr is not None and w > 20 and h > 10:
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
