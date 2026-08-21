@echo off
chcp 65001 >nul
echo ============================================
echo  DesktopPilot - B站搜索"玩机器" 演示
echo ============================================
echo.
"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" "D:\codeshit\DesktopPilot\examples\bilibili_search.py"
echo.
echo ============================================
echo  脚本结束. 截图保存在 examples\output\
pause
