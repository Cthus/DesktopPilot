"""视觉层检测器测试。"""
from __future__ import annotations

import numpy as np
import cv2
import pytest
from desktop_pilot.vision.window_detector import (
    detect_windows_from_screenshot,
    detect_elements_in_region,
    annotate_windows_on_screenshot,
    annotate_elements_on_screenshot,
    UIElementType,
)


# --------------------------------------------------------------------------- #
# 窗口级检测
# --------------------------------------------------------------------------- #
def test_detect_single_window():
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (350, 250), (255, 255, 255), -1)
    windows = detect_windows_from_screenshot(img, min_area=1000)
    assert len(windows) >= 1


def test_detect_multiple_windows():
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (200, 150), (255, 255, 255), -1)
    cv2.rectangle(img, (250, 50), (500, 300), (255, 255, 255), -1)
    windows = detect_windows_from_screenshot(img, min_area=1000)
    assert len(windows) >= 2


def test_annotate_returns_correct_shape():
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (350, 250), (255, 255, 255), -1)
    windows = detect_windows_from_screenshot(img, min_area=1000)
    annotated = annotate_windows_on_screenshot(img, windows)
    assert annotated.shape == img.shape


# --------------------------------------------------------------------------- #
# 元素级检测
# --------------------------------------------------------------------------- #
def test_detect_button_in_region():
    """模拟一个按钮区域：浅蓝背景矩形。"""
    img = np.zeros((200, 400, 3), dtype=np.uint8)
    # 模拟按钮（浅蓝色背景 + 白色边框）
    cv2.rectangle(img, (100, 80), (250, 120), (180, 120, 80), -1)
    cv2.rectangle(img, (100, 80), (250, 120), (255, 255, 255), 2)

    elements = detect_elements_in_region(img, min_element_area=500)
    # 应该能找到这个矩形元素
    types = [e["type"] for e in elements]
    assert len(types) >= 1


def test_detect_text_label():
    """纯文字区域（无边框的灰色矩形）。"""
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    # 模拟标签文字区域
    cv2.putText(img, "Label", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)

    elements = detect_elements_in_region(img, min_element_area=100)
    assert len(elements) >= 1


def test_region_offset():
    """区域裁切时坐标应偏移。"""
    img = np.zeros((200, 400, 3), dtype=np.uint8)
    cv2.rectangle(img, (60, 60), (140, 100), (200, 200, 200), -1)

    # 检测整个图
    all_els = detect_elements_in_region(img, min_element_area=200)
    # 检测右半区域
    region_els = detect_elements_in_region(img, region=(200, 0, 200, 200), min_element_area=200)
    # 左半的元素在右半区域里应该不存在
    for el in all_els:
        rx, ry, rw, rh = el["rect"]
        if rx < 200:  # 左半
            for rel in region_els:
                assert rel["rect"][0] >= 200, "区域偏移后的坐标应在区域内"


def test_annotate_elements_on_screenshot():
    """标注后图像应和原图同尺寸。"""
    img = np.zeros((200, 400, 3), dtype=np.uint8)
    cv2.rectangle(img, (100, 80), (250, 120), (200, 200, 200), -1)
    elements = detect_elements_in_region(img, min_element_area=200)
    annotated = annotate_elements_on_screenshot(img, elements)
    assert annotated.shape == img.shape
